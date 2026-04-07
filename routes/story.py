from flask import Blueprint, request, jsonify, session, render_template
from services.llm_service import generate_story
from services.story_builder import build_prompt, parse_story, get_age_config
from services.storage import (
    save_story, get_stories_for_profile, get_story_by_id,
    delete_story, get_profile_by_id
)

story_bp = Blueprint("story", __name__)


@story_bp.route("/api/generate", methods=["POST"])
def generate():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json()

    # Validate required fields
    profile_id = data.get("profile_id", "").strip()
    if not profile_id:
        return jsonify({"error": "Profile ID is required"}), 400

    profile = get_profile_by_id(profile_id)
    if not profile or profile["user_id"] != session["user_id"]:
        return jsonify({"error": "Profile not found"}), 404

    # Build parameters dict
    params = {
        "profile_id": profile_id,
        "age_group": data.get("age_group", profile.get("age_group", "6-8")),
        "characters": data.get("characters", []),
        "setting": data.get("setting", "an enchanted forest"),
        "theme": data.get("theme", "friendship"),
        "moral": data.get("moral", ""),
    }

    # Ensure at least one character
    if not params["characters"] or not params["characters"][0].get("name"):
        params["characters"] = [{"name": "Alex", "traits": ["brave", "curious"]}]

    # Get age config for token budget
    age_cfg = get_age_config(params["age_group"])

    # Build and send prompt
    prompt = build_prompt(params)
    raw_text = generate_story(prompt, max_tokens=age_cfg["max_tokens"])

    # Parse the structured output
    content = parse_story(raw_text, params)
    title = content["title"]

    # Save to database
    story = save_story(
        profile_id=profile_id,
        user_id=session["user_id"],
        title=title,
        parameters=params,
        content=content
    )

    return jsonify({
        "success": True,
        "story_id": story["id"],
        "title": title,
        "content": content
    }), 201


@story_bp.route("/api/stories/<profile_id>", methods=["GET"])
def list_stories(profile_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    profile = get_profile_by_id(profile_id)
    if not profile or profile["user_id"] != session["user_id"]:
        return jsonify({"error": "Profile not found"}), 404

    stories = get_stories_for_profile(profile_id)
    # Return summary (no full content for list performance)
    summaries = []
    for s in stories:
        summaries.append({
            "id": s["id"],
            "title": s["title"],
            "created_at": s["created_at"],
            "theme": s["parameters"].get("theme", ""),
            "setting": s["parameters"].get("setting", ""),
            "age_group": s["parameters"].get("age_group", ""),
            "moral": s["parameters"].get("moral", ""),
            "characters": s["parameters"].get("characters", [])
        })

    return jsonify({"stories": summaries}), 200


@story_bp.route("/api/stories/detail/<story_id>", methods=["GET"])
def story_detail(story_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    story = get_story_by_id(story_id)
    if not story or story["user_id"] != session["user_id"]:
        return jsonify({"error": "Story not found"}), 404

    return jsonify({"story": story}), 200


@story_bp.route("/api/stories/delete/<story_id>", methods=["DELETE"])
def delete_story_route(story_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    success = delete_story(story_id, session["user_id"])
    if not success:
        return jsonify({"error": "Story not found"}), 404

    return jsonify({"success": True}), 200


@story_bp.route("/story/<story_id>")
def story_page(story_id):
    return render_template("story.html", story_id=story_id)
