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
    """
    Generate a story illustration using a resilient pool of AI models.
    Automatically transitions to fallback models if the primary is busy or fails.
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

    # Attempt generation with the Paint Pool
    for model in PAINT_POOL:
        try:
            url = f"{HF_API_URL}{model}"
            headers = get_hf_headers()
            
            # Simple payload for Inference API
            payload = {"inputs": full_prompt}

            print(f"[IMAGE] Painting with {model}...")
            response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
            
            print(f"[IMAGE] {model} status: {response.status_code}")

            image_data = None
            if response.status_code == 200:
                image_data = response.content
            
            elif response.status_code == 503:
                # Model is loading — wait briefly and try once more before falling back
                print(f"[IMAGE] {model} is loading, retrying once...")
                import time
                time.sleep(RETRY_WAIT_TIME)
                response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
                
                if response.status_code == 200:
                    image_data = response.content
                else:
                    print(f"[IMAGE] {model} still busy, falling back to next model...")
                    continue
            else:
                print(f"[IMAGE] {model} failed ({response.status_code}), falling back...")
                continue

            # If we successfully got image data, process and save it
            if image_data:
                # Generate a unique filename
                filename = f"story_{uuid.uuid4().hex[:8]}.webp"
                filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

                # Process and save the image
                image = Image.open(io.BytesIO(image_data))
                # Resize if the image is too large for web serving
                if image.width > 1200:
                    image.thumbnail((1200, 1200))
                
                image.save(filepath, "WEBP", quality=85)

                print(f"[IMAGE] Success! Saved to {filepath}")
                # Return the relative path for the frontend
                return f"generated_images/{filename}"

        except Exception as e:
            print(f"[IMAGE] Model {model} error: {e}")
            continue

    print("[IMAGE] All models in the Paint Pool failed. Chapter will use fallback icon.")
    return None
