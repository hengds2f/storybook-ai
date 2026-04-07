import os
import uuid
from PIL import Image
import io
from huggingface_hub import InferenceClient
from services.hf_utils import (
    get_hf_token, DEFAULT_TIMEOUT
)

# AI Painter Pool — Prioritized by quality, but fallback to speed/reliability
# InferenceClient handles the new router.huggingface.co automatically
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
    Generate a story illustration using Hugging Face InferenceClient.
    Provides a detailed audit log of every model attempt.
    """
    audit_logs = []
    
    token = get_hf_token()
    if not token:
        msg = "HF_TOKEN is not set."
        audit_logs.append({"model": "System", "status": "ERROR", "message": msg})
        return None, audit_logs

    # Initialize client
    client = InferenceClient(token=token)

    # Ensure the directory exists and is writable
    try:
        os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
    except Exception as e:
        msg = f"Directory {GENERATED_IMAGE_DIR} not writable: {e}"
        audit_logs.append({"model": "System", "status": "FILE_ERROR", "message": msg})
        return None, audit_logs

    # Build a descriptive prompt
    setting = story_params.get("setting", "a magical place")
    style = "vibrant children's storybook illustration, digital art, highly detailed"
    full_prompt = f"{description}, {setting}, {style}"

    # Attempt generation with the Paint Pool
    for model in PAINT_POOL:
        log_entry = {"model": model, "status": "PENDING", "message": ""}
        try:
            print(f"[IMAGE] Client painting with {model}...")
            
            # Using client.text_to_image is the high-level way to call these models
            # It automatically handles the new routing internals
            image = client.text_to_image(
                full_prompt,
                model=model,
                # wait_for_model=True is handled via headers or params in SDK
            )
            
            # If we got a PIL image back, success!
            if isinstance(image, Image.Image):
                filename = f"story_{uuid.uuid4().hex[:8]}.webp"
                filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

                if image.width > 1200:
                    image.thumbnail((1200, 1200))
                image.save(filepath, "WEBP", quality=85)
                
                log_entry["status"] = 200
                log_entry["message"] = "SUCCESS"
                audit_logs.append(log_entry)
                print(f"[IMAGE] Success with {model}")
                return f"generated_images/{filename}", audit_logs
            else:
                log_entry["status"] = "INVALID_RESPONSE"
                log_entry["message"] = "Expected Image, got something else."
                audit_logs.append(log_entry)

        except Exception as e:
            log_entry["status"] = "SDK_EXCEPTION"
            log_entry["message"] = str(e)
            audit_logs.append(log_entry)
            print(f"[IMAGE] {model} failed: {e}")
            continue

    return None, audit_logs
