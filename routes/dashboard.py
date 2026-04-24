from flask import Blueprint, jsonify, session
from services.storage import get_stories_for_user, get_stats_for_user, get_profiles_for_user
from services.storage import get_db
import json as _json

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/dashboard", methods=["GET"])
def dashboard_data():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    stories = get_stories_for_user(session["user_id"])
    stats = get_stats_for_user(session["user_id"])
    profiles = get_profiles_for_user(session["user_id"])

    # Compute theme distribution
    theme_counts = {}
    setting_counts = {}
    age_counts = {"3-5": 0, "6-8": 0, "9-12": 0}
    complexity_counts = {"simple": 0, "moderate": 0, "rich": 0}
    vocab_hint_counts = {"introductory": 0, "grade_level": 0, "stretch": 0}

    story_summaries = []
    for s in stories:
        params = s.get("parameters", {})
        theme = params.get("theme", "unknown")
        setting = params.get("setting", "unknown")
        age = params.get("age_group", "6-8")
        complexity = params.get("complexity_hint", "")
        vocab_hint = params.get("vocabulary_hint", "")
        vocab_score = params.get("vocabulary_score")

        theme_counts[theme] = theme_counts.get(theme, 0) + 1
        setting_counts[setting] = setting_counts.get(setting, 0) + 1
        age_counts[age] = age_counts.get(age, 0) + 1
        if complexity in complexity_counts:
            complexity_counts[complexity] += 1
        if vocab_hint in vocab_hint_counts:
            vocab_hint_counts[vocab_hint] += 1

        story_summaries.append({
            "id": s["id"],
            "title": s["title"],
            "profile_id": s.get("profile_id", ""),
            "profile_name": s.get("profile_name", ""),
            "avatar_color": s.get("avatar_color", "#6366f1"),
            "created_at": s["created_at"],
            "theme": theme,
            "setting": setting,
            "age_group": age,
            "moral": params.get("moral", ""),
            "characters": params.get("characters", []),
            "complexity_hint": complexity,
            "vocabulary_hint": vocab_hint,
            "vocabulary_score": vocab_score,
        })

    # ── Per-profile ML / vocabulary data ─────────────────────────────────
    from services.ml_service import (
        estimate_vocabulary_score, estimate_reading_level, predict_engagement
    )
    from services.event_tracker import get_ml_state

    profiles_ml = []
    total_events_all = 0
    total_questions_answered = 0

    for profile in profiles:
        pid = profile["id"]
        age_group = profile.get("age_group", "6-8")

        vocab      = estimate_vocabulary_score(pid, age_group)
        reading    = estimate_reading_level(pid, age_group)
        engagement = predict_engagement(pid, age_group)
        ml_state   = get_ml_state(pid) or {}

        total_events_all += ml_state.get("total_events", 0)

        # Fetch question-answered count for this profile
        conn = get_db()
        qa_count = conn.execute(
            "SELECT COUNT(*) FROM reading_events WHERE profile_id=? AND event_type='question_answered'",
            (pid,),
        ).fetchone()[0]
        total_questions_answered += qa_count

        # Build vocabulary progression from this profile's stories (oldest → newest)
        profile_stories = sorted(
            [s for s in stories if s.get("profile_id") == pid],
            key=lambda s: s.get("created_at", ""),
        )

        # Pre-fetch vocab quiz accuracy per story for this profile
        vocab_rows = conn.execute(
            """SELECT ql.story_id,
                      COUNT(*) AS total,
                      SUM(CASE WHEN json_extract(re.payload, '$.is_correct') = 1 THEN 1 ELSE 0 END) AS correct
               FROM reading_events re
               JOIN question_log ql
                 ON json_extract(re.payload, '$.question_id') = ql.question_id
               WHERE re.profile_id = ?
                 AND re.event_type  = 'question_answered'
                 AND ql.question_type = 'vocabulary'
               GROUP BY ql.story_id""",
            (pid,),
        ).fetchall()
        conn.close()

        vocab_quiz_by_story = {
            row["story_id"]: round(row["correct"] / row["total"], 4) if row["total"] > 0 else None
            for row in vocab_rows
        }

        vocab_progression = []
        for s in profile_stories[-12:]:  # last 12 stories
            sparams = s.get("parameters", {})
            story_id = s["id"]
            # Map vocabulary_hint to a numeric score for trend charting
            hint = sparams.get("vocabulary_hint", "")
            hint_score = {"introductory": 2.5, "grade_level": 5.5, "stretch": 8.5}.get(hint)
            # Prefer stored numeric vocab_score if available
            stored_score = sparams.get("vocabulary_score")
            trend_score = stored_score if stored_score is not None else hint_score

            vocab_progression.append({
                "story_id":          story_id,
                "title":             s["title"],
                "vocabulary_hint":   hint,
                "complexity_hint":   sparams.get("complexity_hint", ""),
                "vocabulary_score":  trend_score,      # numeric 1–10 or None
                "vocab_quiz_score":  vocab_quiz_by_story.get(story_id),
                "created_at":        s["created_at"],
            })

        # Reading speed in words per minute
        atpw = ml_state.get("avg_time_per_word_ms", 0.0)
        reading_speed_wpm = round(60000.0 / atpw, 0) if atpw > 0 else None

        profiles_ml.append({
            "profile_id":              pid,
            "profile_name":            profile["name"],
            "avatar_color":            profile.get("avatar_color", "#6366f1"),
            "age_group":               age_group,
            # Vocabulary
            "vocabulary_score":        vocab["score"],
            "vocabulary_label":        vocab["label"],
            "vocabulary_hint":         vocab["hint"],
            # Reading level
            "reading_level_score":     reading["score"],
            "reading_level_label":     reading["label"],
            "reading_level_tier":      reading["tier"],
            # Engagement
            "engagement_score":        engagement["score"],
            "engagement_label":        engagement["label"],
            "engagement_tier":         engagement["tier"],
            # Behavioural metrics
            "question_accuracy":       round(ml_state.get("question_accuracy", 0.0), 3),
            "completion_rate":         round(ml_state.get("completion_rate", 0.0), 3),
            "reading_speed_wpm":       reading_speed_wpm,
            "total_events":            ml_state.get("total_events", 0),
            "total_questions_answered": qa_count,
            "total_stories_completed": ml_state.get("total_stories_completed", 0),
            "is_cold_start":           ml_state.get("total_stories_completed", 0) < 3,
            "vocab_progression":       vocab_progression,
        })

    # ── Aggregate ML intelligence stats across all profiles ───────────────
    num_profiles = len(profiles_ml)
    ml_overview = {
        "total_learning_events":      total_events_all,
        "total_questions_answered":   total_questions_answered,
        "avg_vocabulary_score":
            round(sum(p["vocabulary_score"] for p in profiles_ml) / max(num_profiles, 1), 2),
        "avg_reading_level_score":
            round(sum(p["reading_level_score"] for p in profiles_ml) / max(num_profiles, 1), 2),
        "avg_engagement_score":
            round(sum(p["engagement_score"] for p in profiles_ml) / max(num_profiles, 1), 3),
        "avg_question_accuracy":
            round(sum(p["question_accuracy"] for p in profiles_ml) / max(num_profiles, 1), 3),
        # Stories with ML-adjusted complexity
        "stories_ml_adjusted":        sum(1 for s in story_summaries if s.get("complexity_hint")),
        "complexity_counts":          complexity_counts,
        "vocab_hint_counts":          vocab_hint_counts,
        # How many profiles have graduated from cold-start
        "profiles_personalised":      sum(1 for p in profiles_ml if not p["is_cold_start"]),
        "profiles_total":             num_profiles,
    }

    return jsonify({
        "stats": {
            **stats,
            "theme_counts": theme_counts,
            "setting_counts": setting_counts,
            "age_counts": age_counts
        },
        "stories": story_summaries,
        "profiles_ml": profiles_ml,
        "ml_overview": ml_overview,
    }), 200
