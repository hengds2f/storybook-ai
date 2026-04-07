import os
import requests
import uuid
import base64
from PIL import Image
import io
from services.hf_utils import (
    HF_API_URL, get_hf_headers, 
    DEFAULT_TIMEOUT, RETRY_WAIT_TIME, get_hf_token
)

# AI Painter Pool — Prioritized by quality, but fallback to speed/reliability
PAINT_POOL = [
    "black-forest-labs/FLUX.1-schnell",           # Best Quality (Fast FLUX)
    "stabilityai/stable-diffusion-xl-base-1.0",    # Superior SD (SD-XL)
    "stabilityai/stable-diffusion-2-1",            # High Reliability (SD-2.1)
    "runwayml/stable-diffusion-v1-5"               # Maximum Availability (Fastest)
]

# Directory for storing generated images
GENERATED_IMAGE_DIR = os.path.join("static", "generated_images")


def generate_image(description: str, story_params: dict) -> str | None:
    """Standard wrapper for image generation."""
    image_url, _ = generate_image_with_audit(description, story_params)
    return image_url


def generate_image_with_audit(description: str, story_params: dict) -> tuple[str | None, list]:
    """
    Generate a story illustration with a detailed audit log of every attempt.
    Returns (image_url, audit_logs).
    """
    audit_logs = []
    
    token = get_hf_token()
    if not token:
        msg = "HF_TOKEN is not set in environment."
        print(f"[IMAGE] {msg}")
        audit_logs.append({"model": "System", "status": "ERROR", "message": msg})
        return None, audit_logs

    # Ensure the directory exists and is writable
    try:
        os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
        test_file = os.path.join(GENERATED_IMAGE_DIR, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        msg = f"Directory {GENERATED_IMAGE_DIR} is NOT WRITABLE: {e}"
        print(f"[IMAGE][CRITICAL] {msg}")
        audit_logs.append({"model": "System", "status": "FILE_ERROR", "message": msg})
        return None, audit_logs

    # Build a descriptive prompt
    setting = story_params.get("setting", "a magical place")
    age_group = story_params.get("age_group", "6-8")
    style = "vibrant children's storybook illustration, friendly"
    full_prompt = f"{description}, {setting}, {style}, digital art, highly detailed"

    # Attempt generation with the Paint Pool
    for model in PAINT_POOL:
        log_entry = {"model": model, "status": "PENDING", "message": ""}
        try:
            url = f"{HF_API_URL}{model}"
            headers = get_hf_headers()
            payload = {
                "inputs": full_prompt,
                "options": {"wait_for_model": True, "use_cache": False}
            }

            print(f"[IMAGE] Auditing {model}...")
            response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
            
            log_entry["status"] = response.status_code
            
            if response.status_code == 200:
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    error_data = response.json()
                    log_entry["message"] = f"JSON returned instead of image: {error_data}"
                    audit_logs.append(log_entry)
                    continue
                
                # Success!
                image_data = response.content
                filename = f"story_{uuid.uuid4().hex[:8]}.webp"
                filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

                image = Image.open(io.BytesIO(image_data))
                if image.width > 1200:
                    image.thumbnail((1200, 1200))
                image.save(filepath, "WEBP", quality=85)
                
                log_entry["message"] = "SUCCESS"
                audit_logs.append(log_entry)
                return f"generated_images/{filename}", audit_logs
            
            else:
                # Try to parse error message
                try:
                    error_detail = response.json()
                    log_entry["message"] = str(error_detail)
                except:
                    log_entry["message"] = response.text[:150]
                
                audit_logs.append(log_entry)
                continue

        except Exception as e:
            log_entry["status"] = "EXCEPTION"
            log_entry["message"] = str(e)
            audit_logs.append(log_entry)
            continue

    print("[IMAGE] All models in the Paint Pool failed. Chapter will use fallback icon.")
    return None, audit_logs
