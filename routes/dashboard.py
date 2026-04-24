from flask import Blueprint, jsonify, session
from services.storage import get_stories_for_user, get_stats_for_user, get_profiles_for_user
from services.storage import get_db

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

    story_summaries = []
    for s in stories:
        params = s.get("parameters", {})
        theme = params.get("theme", "unknown")
        setting = params.get("setting", "unknown")
        age = params.get("age_group", "6-8")

        theme_counts[theme] = theme_counts.get(theme, 0) + 1
        setting_counts[setting] = setting_counts.get(setting, 0) + 1
        age_counts[age] = age_counts.get(age, 0) + 1

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
            "characters": params.get("characters", [])
        })

    # ── Per-profile ML / vocabulary data ─────────────────────────────────
    from services.ml_service import estimate_vocabulary_score, estimate_reading_level
    from services.event_tracker import get_ml_state

    profiles_ml = []
    for profile in profiles:
        pid = profile["id"]
        age_group = profile.get("age_group", "6-8")

        vocab   = estimate_vocabulary_score(pid, age_group)
        reading = estimate_reading_level(pid, age_group)
        ml_state = get_ml_state(pid) or {}

        # Build vocabulary progression from this profile's stories (oldest → newest)
        # Include per-story vocab quiz score: how many vocabulary questions answered correctly
        profile_stories = sorted(
            [s for s in stories if s.get("profile_id") == pid],
            key=lambda s: s.get("created_at", ""),
        )

        # Pre-fetch vocab quiz accuracy per story for this profile
        import json as _json
        conn = get_db()
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
            params = s.get("parameters", {})
            story_id = s["id"]
            vocab_progression.append({
                "story_id":          story_id,
                "title":             s["title"],
                "vocabulary_hint":   params.get("vocabulary_hint", ""),
                "complexity_hint":   params.get("complexity_hint", ""),
                "vocab_quiz_score":  vocab_quiz_by_story.get(story_id),  # float 0–1 or None
                "created_at":        s["created_at"],
            })

        profiles_ml.append({
            "profile_id":            pid,
            "profile_name":          profile["name"],
            "avatar_color":          profile.get("avatar_color", "#6366f1"),
            "age_group":             age_group,
            "vocabulary_score":      vocab["score"],
            "vocabulary_label":      vocab["label"],
            "vocabulary_hint":       vocab["hint"],
            "reading_level_score":   reading["score"],
            "reading_level_label":   reading["label"],
            "question_accuracy":     round(ml_state.get("question_accuracy", 0.0), 3),
            "total_stories_completed": ml_state.get("total_stories_completed", 0),
            "is_cold_start":         ml_state.get("total_stories_completed", 0) < 3,
            "vocab_progression":     vocab_progression,
        })

    return jsonify({
        "stats": {
            **stats,
            "theme_counts": theme_counts,
            "setting_counts": setting_counts,
            "age_counts": age_counts
        },
        "stories": story_summaries,
        "profiles_ml": profiles_ml,
    }), 200
