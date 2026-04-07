from flask import Blueprint, jsonify, session
from services.storage import get_stories_for_user, get_stats_for_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/dashboard", methods=["GET"])
def dashboard_data():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    stories = get_stories_for_user(session["user_id"])
    stats = get_stats_for_user(session["user_id"])

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
            "profile_name": s.get("profile_name", ""),
            "avatar_color": s.get("avatar_color", "#6366f1"),
            "created_at": s["created_at"],
            "theme": theme,
            "setting": setting,
            "age_group": age,
            "moral": params.get("moral", ""),
            "characters": params.get("characters", [])
        })

    return jsonify({
        "stats": {
            **stats,
            "theme_counts": theme_counts,
            "setting_counts": setting_counts,
            "age_counts": age_counts
        },
        "stories": story_summaries
    }), 200
