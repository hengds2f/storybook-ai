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
    """Standard wrapper for image generation using OpenAI DALL-E 3."""
    image_url, _ = generate_image_with_audit(description, story_params)
    return image_url


def generate_image_with_audit(description: str, story_params: dict) -> tuple[str | None, list]:
    """
    Generate a story illustration using OpenAI DALL-E 3.
    Provides a detailed audit log.
    """
    audit_logs = []
    
    # Robust API key retrieval
    api_key = config.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        msg = "OPENAI_API_KEY is missing (checked config and os.environ)."
        print(f"[IMAGE] CRITICAL ERROR: {msg}")
        audit_logs.append({"model": "System", "status": "ERROR", "message": msg})
        return None, audit_logs
    
    # Masked log for debugging
    masked_key = f"{api_key[:5]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    print(f"[IMAGE] Initializing OpenAI with key: {masked_key}")

    # Initialize OpenAI Client
    client = OpenAI(api_key=api_key)

    # Ensure the directory exists and is writable
    try:
        os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
    except Exception as e:
        msg = f"Directory {GENERATED_IMAGE_DIR} not writable: {e}"
        audit_logs.append({"model": "System", "status": "FILE_ERROR", "message": msg})
        return None, audit_logs

    # Build a descriptive prompt
    setting = story_params.get("setting", "a magical place")
    style = "vibrant children's storybook illustration, digital art, highly detailed, soft lighting, whimsical style"
    full_prompt = f"{description}, {setting}, {style}. Ensure all characters are visible and the scene is enchanting."

    log_entry = {"model": config.OPENAI_IMAGE_MODEL, "status": "PENDING", "message": ""}
    try:
        print(f"[IMAGE] OpenAI painting with {config.OPENAI_IMAGE_MODEL}...")
        
        # Generation call
        response = client.images.generate(
            model=config.OPENAI_IMAGE_MODEL,
            prompt=full_prompt,
            size=config.IMAGE_SIZE,
            quality=config.IMAGE_QUALITY,
            n=1,
        )
        
        if response.data and response.data[0].url:
            image_url = response.data[0].url
            
            # Download the image with timeout
            img_response = requests.get(image_url, timeout=30)
            if img_response.status_code == 200:
                image = Image.open(io.BytesIO(img_response.content))
                
                filename = f"story_{uuid.uuid4().hex[:8]}.webp"
                filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

                if image.width > 1200:
                    image.thumbnail((1200, 1200))
                image.save(filepath, "WEBP", quality=85)
                
                log_entry["status"] = 200
                log_entry["message"] = "SUCCESS"
                audit_logs.append(log_entry)
                print(f"[IMAGE] Success with OpenAI DALL-E 3")
                return f"generated_images/{filename}", audit_logs

        log_entry["status"] = "INVALID_RESPONSE"
        log_entry["message"] = "OpenAI returned no valid image URL."
        audit_logs.append(log_entry)

    except Exception as e:
        log_entry["status"] = "OPENAI_EXCEPTION"
        log_entry["message"] = str(e)
        audit_logs.append(log_entry)
        print(f"[IMAGE] OpenAI DALL-E 3 failed: {e}")

    return None, audit_logs
