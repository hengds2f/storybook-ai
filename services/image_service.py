import os
import uuid
import io
from PIL import Image
import config

# Absolute path for storing generated images to avoid CWD issues
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_IMAGE_DIR = os.path.join(BASE_DIR, "static", "generated_images")


def generate_image(description: str, story_params: dict) -> str | None:
    """Standard wrapper for image generation."""
    image_url, _ = generate_image_with_audit(description, story_params)
    return image_url


def _generate_with_hf(description: str, story_params: dict, audit_logs: list) -> str | None:
    """Internal helper for Hugging Face Inference API image generation."""
    from huggingface_hub import InferenceClient
    
    # Robust API key retrieval
    api_key = config.HF_API_KEY
    if not api_key:
        msg = "Hugging Face Token is missing (check HF_TOKEN or HUGGING_FACE_HUB_TOKEN)."
        print(f"[IMAGE] CRITICAL ERROR: {msg}")
        audit_logs.append({"model": "System", "status": "ERROR", "message": msg})
        return None

    client = InferenceClient(token=api_key)
    
    # Build a descriptive prompt
    setting = story_params.get("setting", "a magical place")
    style = "vibrant children's storybook illustration, digital art, highly detailed, whimsical style"
    full_prompt = f"{description}, {setting}, {style}. Ensure all characters are visible and the scene is enchanting."

    log_entry = {"model": config.HF_IMAGE_MODEL, "status": "PENDING", "message": ""}
    try:
        print(f"[IMAGE] HF painting with {config.HF_IMAGE_MODEL}...")
        image = client.text_to_image(full_prompt, model=config.HF_IMAGE_MODEL)
        
        # Ensure the directory exists
        os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
        
        filename = f"story_{uuid.uuid4().hex[:8]}.webp"
        filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

        if image.width > 1200:
            image.thumbnail((1200, 1200))
        image.save(filepath, "WEBP", quality=85)
        
        log_entry["status"] = 200
        log_entry["message"] = "SUCCESS"
        audit_logs.append(log_entry)
        print(f"[IMAGE] Success with Hugging Face")
        return f"generated_images/{filename}"
        
    except Exception as e:
        log_entry["status"] = "HF_EXCEPTION"
        log_entry["message"] = str(e)
        audit_logs.append(log_entry)
        print(f"[IMAGE] Hugging Face failed: {e}")
        return None


def generate_image_with_audit(description: str, story_params: dict) -> tuple[str | None, list]:
    """
    Generate a story illustration using Hugging Face engine.
    """
    audit_logs = []
    url = _generate_with_hf(description, story_params, audit_logs)
    return url, audit_logs
