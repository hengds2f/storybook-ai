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

# Primary model — high quality
PRIMARY_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
# Fallback model — high reliability
FALLBACK_IMAGE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"

# Directory for storing generated images
GENERATED_IMAGE_DIR = os.path.join("static", "generated_images")


def generate_image(description: str, story_params: dict) -> str | None:
    """
    Generate a story illustration using Hugging Face's Image Inference API.
    Attempts multiple models if the primary one is unavailable.
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

    # Attempt generation with a list of prioritized models
    for model in [PRIMARY_IMAGE_MODEL, FALLBACK_IMAGE_MODEL]:
        try:
            url = f"{HF_API_URL}{model}"
            headers = get_hf_headers()
            
            # Standard payload for HF Inference API
            payload = {"inputs": full_prompt}

            print(f"[IMAGE] Attempting illustration with {model}...")
            response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
            
            print(f"[IMAGE] Model {model} responded with status: {response.status_code}")

            image_data = None
            if response.status_code == 200:
                image_data = response.content
            
            elif response.status_code == 503:
                # Model is loading — wait and try this model one more time
                print(f"[IMAGE] Model {model} is loading, retrying once in {RETRY_WAIT_TIME}s...")
                import time
                time.sleep(RETRY_WAIT_TIME)
                response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
                
                if response.status_code == 200:
                    image_data = response.content
                else:
                    print(f"[IMAGE] Model {model} still loading or failed on retry ({response.status_code}), moving to next...")
                    continue
            else:
                # Other errors — move to next model
                print(f"[IMAGE] Model {model} failed with status {response.status_code}, moving to next...")
                continue

            # If we successfully got image data, process and save it
            if image_data:
                # Generate a unique filename
                filename = f"story_{uuid.uuid4().hex[:8]}.webp"
                filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

                # Process and save the image
                image = Image.open(io.BytesIO(image_data))
                # Optional: Resize/compress if needed
                image.save(filepath, "WEBP", quality=85)

                # Return the relative path for the frontend
                return f"generated_images/{filename}"

        except Exception as e:
            print(f"[IMAGE] Generation failed for model {model}: {e}")
            continue

    return None
