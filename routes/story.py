import os
import config
from flask import Blueprint, request, jsonify, session, render_template
from services.llm_service import generate_story, generate_story_8act, count_words
from services.story_builder import build_prompt, parse_story, get_age_config
from services.storage import (
    save_story, get_stories_for_profile, get_story_by_id,
    delete_story, get_profile_by_id
)
from services.image_service import generate_image, generate_image_with_audit

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

    # Build and send prompt (8-Act Narrative Engine for 1000+ words)
    raw_text = generate_story_8act(params)

    # Parse the structured output
    content = parse_story(raw_text, params)
    title = content["title"]

    # Check word count - ensure story is more than 500 words
    total_words = sum(count_words(section["content"]) for section in content.get("sections", []))
    retries = 0
    max_retries = 3
    while total_words < 500 and retries < max_retries:
        print(f"[STORY] Story too short ({total_words} words), regenerating... (attempt {retries+1}/{max_retries})")
        raw_text = generate_story_8act(params)
        content = parse_story(raw_text, params)
        total_words = sum(count_words(section["content"]) for section in content.get("sections", []))
        retries += 1

    if total_words < 500:
        print(f"[STORY] Failed to generate story >500 words after {max_retries} attempts. Proceeding with {total_words} words.")

    # Generate illustrations for each section
    for section in content.get("sections", []):
        scene_desc = section.get("scene_description")
        if scene_desc:
            print(f"[STORY] Attempting illustration for: {scene_desc[:60]}...")
            url = generate_image(scene_desc, params)
            if url:
                print(f"[STORY] Illustration success: {url}")
                section["image_url"] = url
            else:
                print(f"[STORY] Illustration failed (check image_service logs)")

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
    session_user = None
    if "user_id" in session:
        session_user = {"user_id": session["user_id"], "username": session["username"]}
    return render_template("story.html", story_id=story_id, session_user=session_user)


import io
from flask import send_file
from services.pdf_service import generate_story_pdf


@story_bp.route("/api/story/<story_id>/pdf")
def download_pdf(story_id):
    """Generate and download a PDF version of the story."""
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    story = get_story_by_id(story_id)
    if not story:
        return jsonify({"error": "Story not found"}), 404
        
    try:
        # Generate the PDF bytes
        pdf_bytes = generate_story_pdf(story)
        
        # Safe filename
        safe_title = "".join([c for c in story.get('title', 'story') if c.isalnum() or c==' ']).rstrip()
        filename = f"{safe_title}.pdf"
        
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"[PDF] Error generating PDF: {e}")
        return jsonify({"error": "Could not generate PDF"}), 500





@story_bp.route("/api/test-paint")
def test_paint():
    """Hidden diagnostic endpoint to test a single image generation with full error reporting."""
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    prompt = request.args.get("prompt", "a magical golden castle in the clouds, whimsical children's book style")
    print(f"[DIAGNOSTIC] Starting audit-paint for: {prompt}")
    
    # We mock params for the test
    test_params = {"setting": "magical world", "age_group": "6-8"}
    
    image_url, audit_log = generate_image_with_audit(prompt, test_params)
    
    if image_url:
        return jsonify({
            "success": True, 
            "image_url": image_url, 
            "full_path": f"/static/{image_url}",
            "message": "Illustration successful!",
            "audit_log": audit_log
        }), 200
    else:
        return jsonify({
            "success": False, 
            "message": "Illustration failed across all models in pool.",
            "audit_log": audit_log,
            "hint": "Check the audit_log for specific status codes (e.g. 403, 503)."
        }), 500


@story_bp.route("/api/ai-status")
def ai_status():
    """Diagnostic endpoint to check AI configuration."""
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data_dir = os.path.join("static", "generated_images")
    
    status = {
        "gemini_key_present": bool(config.GEMINI_API_KEY),
        "openai_key_present": bool(config.OPENAI_API_KEY),
        "data_dir_exists": os.path.exists(data_dir),
        "data_dir_writable": os.access(data_dir, os.W_OK) if os.path.exists(data_dir) else False,
        "primary_engine": f"{config.TEXT_GEN_ENGINE} ({config.GEMINI_MODEL_STANDARD} + PRO finale)",
        "image_engine": f"{config.IMAGE_GEN_ENGINE} ({config.OPENAI_IMAGE_MODEL})",
        "narrative_uniqueness": "Active (Entropy Seeds + Persistent Taboos)"
    }
    
    return jsonify(status), 200
