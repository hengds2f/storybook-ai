import os
import requests
import uuid
import base64
from PIL import Image
import io
from services.hf_utils import (
    HF_API_URL, get_hf_token, get_hf_headers, 
    DEFAULT_TIMEOUT, RETRY_WAIT_TIME
)

DEFAULT_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"

# Directory for storing generated images
GENERATED_IMAGE_DIR = os.path.join("static", "generated_images")


def generate_image(description: str, story_params: dict) -> str | None:
    """
    Generate a story illustration using Hugging Face's Image Inference API.
    Returns the path to the saved image relative to the static directory.
    """
    token = get_hf_token()
    if not token:
        print("[IMAGE] HF_TOKEN is not set, skipping image generation.")
        return None

    # Ensure the directory exists
    os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)

    # Build a descriptive prompt from the scene description and story context
    setting = story_params.get("setting", "a magical place")
    age_group = story_params.get("age_group", "6-8")
    
    # Adjust style based on age group
    style = "vibrant, colorful, children's storybook illustration style, high-quality, friendly"
    if age_group == "3-5":
        style = "simple, bold, very colorful, soft edges, cute children's book art"
    elif age_group == "9-12":
        style = "detailed, painterly, whimsical children's fantasy illustration, rich colors"

    full_prompt = f"{description}, {setting}, {style}, digital art, highly detailed"

    try:
        url = f"{HF_API_URL}{DEFAULT_IMAGE_MODEL}"
        headers = get_hf_headers()
        
        # Standard payload for HF Inference API
        payload = {"inputs": full_prompt}

        response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
        
        print(f"[IMAGE] Model response status: {response.status_code}")

        if response.status_code == 200:
            # The API returns binary image data
            image_data = response.content
            
            # Generate a unique filename
            filename = f"story_{uuid.uuid4().hex[:8]}.webp"
            filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

            # Process and save the image
            image = Image.open(io.BytesIO(image_data))
            # Optional: Resize/compress if needed
            image.save(filepath, "WEBP", quality=85)

            # Return the relative path for the frontend (e.g. /static/generated_images/story_...)
            # Flask serves from /static, so we return generated_images/story_...
            return f"generated_images/{filename}"

        elif response.status_code == 503:
            # Avoid infinite recursion with a depth limit if needed, 
            # but for now let's just log and return None after one retry
            print(f"[IMAGE] Model {DEFAULT_IMAGE_MODEL} is loading, retrying once...")
            import time
            time.sleep(RETRY_WAIT_TIME)
            # Second attempt
            response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                image_data = response.content
            else:
                print(f"[IMAGE] Model still loading or failed on retry: {response.status_code}")
                return None
        else:
            print(f"[IMAGE] API Error {response.status_code}: {response.text[:200]}")
            return None

        # Process and save the image if we have data
        if 'image_data' in locals():
            # Generate a unique filename
            filename = f"story_{uuid.uuid4().hex[:8]}.webp"
            filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

            # Process and save the image
            image = Image.open(io.BytesIO(image_data))
            # Optional: Resize/compress if needed
            image.save(filepath, "WEBP", quality=85)

            # Return the relative path for the frontend (e.g. /static/generated_images/story_...)
            return f"generated_images/{filename}"

    except Exception as e:
        print(f"[IMAGE] Generation failed: {e}")

    return None
