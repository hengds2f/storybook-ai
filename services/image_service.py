import os
import uuid
import requests
from PIL import Image
import io

# Absolute path for storing generated images to avoid CWD issues
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_IMAGE_DIR = os.path.join(BASE_DIR, "static", "generated_images")


def generate_image(description: str, story_params: dict) -> str | None:
    """Standard wrapper for image generation."""
    image_url, _ = generate_image_with_audit(description, story_params)
    return image_url


def generate_image_with_audit(description: str, story_params: dict) -> tuple[str | None, list]:
    """
    Generate a story illustration using Hugging Face Inference API.
    """
    audit_logs = []
    
    # Setup Hugging Face Inference API
    hf_token = os.environ.get("HF_TOKEN")
    # Masked log for debugging
    masked_key = f"{hf_token[:5]}...{hf_token[-4:]}" if hf_token and len(hf_token) > 10 else "***"
    print(f"[IMAGE] Using HF Token: {masked_key}")

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

    log_entry = {"model": "FLUX.1-schnell", "status": "PENDING", "message": ""}
    try:
        print(f"[IMAGE] Painting with Hugging Face Inference API...")
        
        API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
        headers = {}
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
            
        payload = {"inputs": full_prompt}
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            image_bytes = response.content
            image = Image.open(io.BytesIO(image_bytes))
            
            filename = f"story_{uuid.uuid4().hex[:8]}.webp"
            filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

            if image.width > 1200:
                image.thumbnail((1200, 1200))
            image.save(filepath, "WEBP", quality=85)
            
            log_entry["status"] = 200
            log_entry["message"] = "SUCCESS"
            audit_logs.append(log_entry)
            print(f"[IMAGE] Success with Hugging Face API")
            return f"generated_images/{filename}", audit_logs
        else:
            log_entry["status"] = response.status_code
            log_entry["message"] = f"HF API Error: {response.text}"
            audit_logs.append(log_entry)
            print(f"[IMAGE] HF API returned error {response.status_code}: {response.text}")

    except Exception as e:
        log_entry["status"] = "EXCEPTION"
        log_entry["message"] = str(e)
        audit_logs.append(log_entry)
        print(f"[IMAGE] Image generation failed: {e}")

    return None, audit_logs
