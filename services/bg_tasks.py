import threading
import uuid
from flask import Flask
from services.storage import get_story_task, update_story_task, save_story
from services.llm_service import generate_story_8act, count_words
from services.story_builder import parse_story
from services.image_service import generate_image

# Section titles that trigger interactive questions and their question types
# Maps section title → (question_type, act_number_for_db)
_SECTION_QUESTION_MAP = {
    "Introduction": ("comprehension", 2),  # comprehension after setup
    "Challenge":    ("prediction",    5),  # predict what comes next
    "Moral":        ("reflection",    8),  # reflect on the lesson
}

def start_story_generation_thread(task_id: str, app: Flask):
    """Spawn a background thread to generate a story."""
    thread = threading.Thread(target=process_story_generation, args=(task_id, app))
    thread.daemon = True
    thread.start()

def process_story_generation(task_id: str, app: Flask):
    """
    Background worker that runs the full story generation pipeline.
    Uses app_context to interact with database and configurations safely.
    """
    with app.app_context():
        try:
            task = get_story_task(task_id)
            if not task:
                print(f"[BG_TASK] Task {task_id} not found.")
                return

            params = task["params"]
            user_id = task["user_id"]
            profile_id = task["profile_id"]
            session_id = str(uuid.uuid4())  # one ML session per generation run

            update_story_task(task_id, status="generating", status_message="Starting narrative engine...", progress_pct=5)

            # ── ML event: story_started ────────────────────────────────────
            _fire_event(profile_id, session_id, "story_started", {
                "word_count":  _word_count_for_age(params.get("age_group", "6-8")),
                "age_group":   params.get("age_group", "6-8"),
                "theme":       params.get("theme", ""),
                "setting":     params.get("setting", ""),
            })

            # 1. Narrative Generation (Passing task_id for live updates)
            import time
            t_start = time.monotonic()
            raw_text = generate_story_8act(params, task_id=task_id)
            elapsed_ms = int((time.monotonic() - t_start) * 1000)

            if not raw_text:
                _fire_event(profile_id, session_id, "story_abandoned", {
                    "time_spent_ms": elapsed_ms, "words_read_estimate": 0, "last_act": 0
                })
                update_story_task(task_id, status="failed", status_message="Narrative engine failed.")
                return

            update_story_task(task_id, status_message="Parsing story structure...", progress_pct=85)
            content = parse_story(raw_text, params)
            title = content.get("title", "Untitled Story")

            # Count actual words in the generated story
            word_count = count_words(raw_text)

            # 2. Illustration Generation
            sections = content.get("sections", [])
            total_sections = len(sections)
            for idx, section in enumerate(sections):
                if section.get("title") == "Poem":
                    continue # Do not generate illustrations for poems as AI text rendering is illegible
                scene_desc = section.get("scene_description")
                if scene_desc:
                    progress = 85 + int((idx / total_sections) * 10)
                    update_story_task(task_id, status_message=f"Illustrating section {idx+1}/{total_sections}...", progress_pct=progress)
                    url = generate_image(scene_desc, params)
                    if url:
                        section["image_url"] = url

            # 3. Final Save
            update_story_task(task_id, status="completing", status_message="Saving story to library...", progress_pct=98)
            story = save_story(
                profile_id=profile_id,
                user_id=user_id,
                title=title,
                parameters=params,
                content=content
            )
            story_id = story["id"]

            # ── ML event: story_completed ──────────────────────────────────
            _fire_event(profile_id, session_id, "story_completed", {
                "time_spent_ms": elapsed_ms,
                "word_count":    word_count,
                "age_group":     params.get("age_group", "6-8"),
                "theme":         params.get("theme", ""),
                "setting":       params.get("setting", ""),
            }, story_id=story_id)

            # ── ML: pre-generate questions for acts 3, 5, 8 ───────────────
            _generate_act_questions(profile_id, story_id, sections, params)

            # Persist question_ids (embedded by _generate_act_questions into sections
            # in-place) back into the stored story content in the DB.
            try:
                from services.storage import update_story_content
                update_story_content(story_id, content)
                print(f"[BG_TASK] Story content updated with question_ids: {story_id}")
            except Exception as e:
                print(f"[BG_TASK] Failed to persist question_ids to story: {e}")

            # ── ML event: session_ended ────────────────────────────────────
            _fire_event(profile_id, session_id, "session_ended", {
                "total_time_ms":       elapsed_ms,
                "stories_started":     1,
                "stories_completed":   1,
            }, story_id=story_id)

            update_story_task(task_id, status="finished", status_message="Complete!", progress_pct=100, result_story_id=story_id)
            print(f"[BG_TASK] Story generation successful: {story_id}")

        except Exception as e:
            print(f"[BG_TASK] Fatal error: {e}")
            update_story_task(task_id, status="failed", status_message=f"Error: {str(e)}")


# ── Internal ML helpers ────────────────────────────────────────────────────────

def _fire_event(profile_id: str, session_id: str, event_type: str, payload: dict, story_id: str = None):
    """Fire a reading event silently — never raises, never blocks generation."""
    try:
        from services.event_tracker import record_event
        record_event(
            profile_id=profile_id,
            session_id=session_id,
            event_type=event_type,
            payload=payload,
            story_id=story_id,
        )
    except Exception as e:
        print(f"[BG_TASK] ML event '{event_type}' failed (non-fatal): {e}")


def _word_count_for_age(age_group: str) -> int:
    """Return the midpoint word count for an age group's story range."""
    return {"3-5": 75, "6-8": 300, "9-12": 750}.get(age_group, 300)


def _generate_act_questions(profile_id: str, story_id: str, sections: list, params: dict):
    """
    Pre-generate questions for Introduction, Challenge, and Moral sections and
    attach question_id to each section so the reader can show it.
    Each section is handled independently — a failure for one does not block others.
    """
    from services.ml_service import generate_question
    age_group = params.get("age_group", "6-8")

    for section in sections:
        title = section.get("title", "")
        if title not in _SECTION_QUESTION_MAP:
            continue
        question_type, act_number = _SECTION_QUESTION_MAP[title]
        act_text = section.get("content", "") or section.get("text", "")
        if not act_text or len(act_text) < 50:
            continue
        try:
            q = generate_question(
                profile_id=profile_id,
                story_id=story_id,
                act_number=act_number,
                act_text=act_text,
                age_group=age_group,
                question_type=question_type,
                use_llm=True,
            )
            # Attach question_id to the section so the reader can show it
            section["question_id"] = q["question_id"]
            section["question_type"] = q["question_type"]
            print(f"[BG_TASK] Question generated for section '{title}' (act {act_number}): {q['question_id']}")
        except Exception as e:
            print(f"[BG_TASK] Question generation failed for section '{title}' (non-fatal): {e}")
