import os
import requests
import uuid
import base64
from PIL import Image
import io


HF_IMAGE_API_URL = "https://api-inference.huggingface.co/models/"
DEFAULT_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"

# Directory for storing generated images
GENERATED_IMAGE_DIR = os.path.join("static", "generated_images")


def generate_image(description: str, story_params: dict) -> str | None:
    """
    Generate a story illustration using Hugging Face's Image Inference API.
    Returns the path to the saved image relative to the static directory.
    """
    token = os.environ.get("HF_TOKEN", "")
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
        url = f"{HF_IMAGE_API_URL}{DEFAULT_IMAGE_MODEL}"
        headers = {"Authorization": f"Bearer {token}"}
        
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "num_inference_steps": 4,
                "guidance_scale": 0.0
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)

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
            print(f"[IMAGE] Model {DEFAULT_IMAGE_MODEL} is loading, retrying...")
            import time
            time.sleep(10)
            return generate_image(description, story_params)
        else:
            print(f"[IMAGE] API Error {response.status_code}: {response.text[:200]}")

    except Exception as e:
        print(f"[IMAGE] Generation failed: {e}")

    return None
