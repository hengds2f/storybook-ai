import threading
from flask import Flask
from services.storage import get_story_task, update_story_task, save_story
from services.llm_service import generate_story_8act, count_words
from services.story_builder import parse_story
from services.image_service import generate_image

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

            update_story_task(task_id, status="generating", status_message="Starting narrative engine...", progress_pct=5)

            # 1. Narrative Generation (Passing task_id for live updates)
            raw_text = generate_story_8act(params, task_id=task_id)
            if not raw_text:
                update_story_task(task_id, status="failed", status_message="Narrative engine failed.")
                return

            update_story_task(task_id, status_message="Parsing story structure...", progress_pct=85)
            content = parse_story(raw_text, params)
            title = content.get("title", "Untitled Story")

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

            update_story_task(task_id, status="finished", status_message="Complete!", progress_pct=100, result_story_id=story["id"])
            print(f"[BG_TASK] Story generation successful: {story['id']}")

        except Exception as e:
            print(f"[BG_TASK] Fatal error: {e}")
            update_story_task(task_id, status="failed", status_message=f"Error: {str(e)}")
