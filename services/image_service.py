import os
import uuid
import requests
from PIL import Image
import io
from openai import OpenAI

# Directory for storing generated images
GENERATED_IMAGE_DIR = os.path.join("static", "generated_images")


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
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY is not set."
        audit_logs.append({"model": "System", "status": "ERROR", "message": msg})
        return None, audit_logs

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

    log_entry = {"model": "dall-e-3", "status": "PENDING", "message": ""}
    try:
        print(f"[IMAGE] OpenAI painting with DALL-E 3...")
        
        # Generation call
        response = client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024",
            quality="standard",
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
