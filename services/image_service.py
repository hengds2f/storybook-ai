import os
import uuid
import requests
from PIL import Image
import io
import config
from openai import OpenAI

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


def _generate_with_openai(description: str, story_params: dict, audit_logs: list) -> str | None:
    """Internal helper for OpenAI DALL-E 3 image generation."""
    from openai import OpenAI
    
    api_key = config.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY is missing."
        audit_logs.append({"model": "System", "status": "ERROR", "message": msg})
        return None

    client = OpenAI(api_key=api_key)
    setting = story_params.get("setting", "a magical place")
    style = "vibrant children's storybook illustration, digital art, highly detailed, whimsical style"
    full_prompt = f"{description}, {setting}, {style}. Ensure all characters are visible and the scene is enchanting."

    log_entry = {"model": config.OPENAI_IMAGE_MODEL, "status": "PENDING", "message": ""}
    try:
        print(f"[IMAGE] OpenAI painting with {config.OPENAI_IMAGE_MODEL}...")
        response = client.images.generate(
            model=config.OPENAI_IMAGE_MODEL,
            prompt=full_prompt,
            size=config.IMAGE_SIZE,
            quality=config.IMAGE_QUALITY,
            n=1,
        )
        
        if response.data and response.data[0].url:
            img_response = requests.get(response.data[0].url, timeout=30)
            if img_response.status_code == 200:
                image = Image.open(io.BytesIO(img_response.content))
                os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
                filename = f"story_{uuid.uuid4().hex[:8]}.webp"
                filepath = os.path.join(GENERATED_IMAGE_DIR, filename)
                if image.width > 1200:
                    image.thumbnail((1200, 1200))
                image.save(filepath, "WEBP", quality=85)
                log_entry["status"] = 200
                log_entry["message"] = "SUCCESS"
                audit_logs.append(log_entry)
                return f"generated_images/{filename}"

    except Exception as e:
        log_entry["status"] = "OPENAI_EXCEPTION"
        log_entry["message"] = str(e)
        audit_logs.append(log_entry)
        print(f"[IMAGE] OpenAI failed: {e}")
        
    return None


def generate_image_with_audit(description: str, story_params: dict) -> tuple[str | None, list]:
    """
    Generate a story illustration using the preferred engine (Hugging Face or OpenAI).
    """
    audit_logs = []
    
    if config.IMAGE_GEN_ENGINE == "huggingface":
        url = _generate_with_hf(description, story_params, audit_logs)
    else:
        url = _generate_with_openai(description, story_params, audit_logs)
        
    return url, audit_logs
