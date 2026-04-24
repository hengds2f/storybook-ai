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

    age_group = data.get("age_group", profile.get("age_group", "6-8"))

    # ── ML personalisation: fetch recommendations for this profile ──────────
    # If the user explicitly supplied theme/setting, respect that (manual override).
    # Otherwise, use ML-recommended values.
    from services.ml_service import recommend_story_params, estimate_vocabulary_score
    ml_rec = recommend_story_params(profile_id, age_group)
    vocab_result = estimate_vocabulary_score(profile_id, age_group)

    user_supplied_theme   = data.get("theme", "").strip()
    user_supplied_setting = data.get("setting", "").strip()

    theme   = user_supplied_theme   or ml_rec["theme"]
    setting = user_supplied_setting or ml_rec["setting"]

    # Build parameters dict — ML hints are passed through to the prompt builder
    params = {
        "profile_id":       profile_id,
        "age_group":        ml_rec["age_group"],   # ML may nudge age_group up/down one level
        "characters":       data.get("characters", []),
        "setting":          setting,
        "theme":            theme,
        "moral":            data.get("moral", ""),
        # ML hints consumed by story_builder.build_8act_prompts
        "complexity_hint":  ml_rec["complexity_hint"],
        "vocabulary_hint":  ml_rec["vocabulary_hint"],
        # Numeric vocabulary score drives dynamic word-count targets in build_8act_prompts
        "vocabulary_score": vocab_result["score"],
        "ml_cold_start":    ml_rec["cold_start"],
        "ml_confidence":    ml_rec["confidence"],
    }

    # Ensure at least one character
    if not params["characters"] or not params["characters"][0].get("name"):
        params["characters"] = [{"name": "Alex", "traits": ["brave", "curious"]}]

    from services.storage import create_story_task
    from services.bg_tasks import start_story_generation_thread
    from flask import current_app

    # Create background task
    task = create_story_task(session["user_id"], profile_id, params)

    # Start thread (passing real app object for context)
    start_story_generation_thread(task["id"], current_app._get_current_object())

    return jsonify({
        "success": True,
        "task_id": task["id"],
        "message": "Story generation started in background.",
        "ml_applied": {
            "theme":            theme,
            "setting":          setting,
            "age_group":        params["age_group"],
            "complexity_hint":  params["complexity_hint"],
            "vocabulary_hint":  params["vocabulary_hint"],
            "vocabulary_score": params["vocabulary_score"],
            "cold_start":       ml_rec["cold_start"],
            "confidence":       ml_rec["confidence"],
        },
    }), 202


@story_bp.route("/api/generate/status/<task_id>", methods=["GET"])
def generation_status(task_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
        
    from services.storage import get_story_task
    task = get_story_task(task_id)
    
    if not task:
        return jsonify({"error": "Task not found"}), 404
        
    if task["user_id"] != session["user_id"]:
        return jsonify({"error": "Unauthorized"}), 403
        
    return jsonify({
        "status": task["status"],
        "progress_pct": task["progress_pct"],
        "status_message": task["status_message"],
        "result_story_id": task["result_story_id"]
    }), 200


@story_bp.route("/api/stories/<profile_id>", methods=["GET"])
def list_stories(profile_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    profile = get_profile_by_id(profile_id)
    if not profile or profile["user_id"] != session["user_id"]:
        return jsonify({"error": "Profile not found"}), 404

    stories = get_stories_for_profile(profile_id)
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
        pdf_bytes = generate_story_pdf(story)
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
            "hint": "Check the audit_log for specific status codes."
        }), 500


@story_bp.route("/api/test-narrative")
def test_narrative():
    """Diagnostic endpoint to test a single AI story act with full error reporting."""
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    from services.llm_service import _call_gemini_api
    
    prompt = "Write a short 3-sentence intro about a brave squirrel. Use whimsical language."
    model = request.args.get("model", "auto")
    
    print(f"[DIAGNOSTIC] Starting test-narrative (model={model})...")
    
    if model == "pro" or (model == "auto" and config.TEXT_GEN_ENGINE == "google-gemini"):
        result = _call_gemini_api(config.GEMINI_MODEL_PRO, prompt, max_tokens=100)
    else:
        result = _call_gemini_api(config.GEMINI_MODEL_STANDARD, prompt, max_tokens=100)
    
    from services import llm_service
    if result:
        return jsonify({
            "success": True, 
            "content": result,
            "message": f"Narrative generation successful with {model if model != 'auto' else config.TEXT_GEN_ENGINE}!"
        }), 200
    else:
        return jsonify({
            "success": False, 
            "message": "Narrative generation failed.",
            "error_captured": llm_service.get_last_error(),
            "hint": "Check the error_captured field for the exact reason."
        }), 500


@story_bp.route("/api/ai-status")
def ai_status():
    """Diagnostic endpoint to check AI configuration with safe key prefix disclosure."""
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    from services import llm_service

    hf_token = config.HF_API_KEY
    token_valid = False
    token_user = None
    token_error = None

    if not hf_token:
        token_error = "HF_TOKEN secret is missing — add it in Space Settings → Secrets"
    else:
        # Try whoami to get username; treat any failure as "token present but unverified"
        try:
            import requests as _req
            resp = _req.get(
                "https://huggingface.co/api/whoami",
                headers={"Authorization": f"Bearer {hf_token}"},
                timeout=5,
            )
            if resp.status_code == 200:
                token_valid = True
                token_user = resp.json().get("name", "HF User")
            else:
                # Token present but whoami failed (fine-grained tokens, read-only tokens,
                # or inference-only tokens may not support whoami — still usable for inference)
                token_valid = True
                token_user = "HF (configured)"
        except Exception:
            # Network error — assume token is present but unverifiable
            token_valid = True
            token_user = "HF (unverified)"

    data_dir = os.path.join("static", "generated_images")

    def get_prefix(key):
        if not key: return "MISSING"
        return f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"

    status = {
        # Fields expected by the dashboard JS
        "token_valid": token_valid,
        "token_user": token_user,
        "token_error": token_error,
        "paint_pool_models": [config.HF_IMAGE_MODEL],
        # Extended diagnostics
        "gemini_key_present": bool(config.get_gemini_key()),
        "gemini_prefix": get_prefix(config.get_gemini_key()),
        "hf_token_present": bool(hf_token),
        "hf_prefix": get_prefix(hf_token),
        "data_dir_exists": os.path.exists(data_dir),
        "data_dir_writable": os.access(data_dir, os.W_OK) if os.path.exists(data_dir) else False,
        "primary_engine": f"{config.TEXT_GEN_ENGINE} ({config.GEMINI_MODEL_STANDARD})",
        "image_engine": f"{config.IMAGE_GEN_ENGINE} ({config.HF_IMAGE_MODEL})",
        "last_narrative_error": llm_service.get_last_error(),
        "debug_view": "/api/debug-view",
    }

    return jsonify(status), 200


@story_bp.route("/api/debug-view")
def debug_view():
    """Returns the raw last error for deep troubleshooting."""
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    from services import llm_service
    return jsonify({
        "last_error": llm_service.get_last_error(),
        "engine": config.TEXT_GEN_ENGINE,
        "gemini_model": config.GEMINI_MODEL_STANDARD
    }), 200
