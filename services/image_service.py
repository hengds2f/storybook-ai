import os
import uuid
from PIL import Image
import io
import google.generativeai as genai

# Directory for storing generated images
GENERATED_IMAGE_DIR = os.path.join("static", "generated_images")


def generate_image(description: str, story_params: dict) -> str | None:
    """Standard wrapper for image generation using Google Gemini (Imagen)."""
    image_url, _ = generate_image_with_audit(description, story_params)
    return image_url


def generate_image_with_audit(description: str, story_params: dict) -> tuple[str | None, list]:
    """
    Generate a story illustration using Google Gemini Imagen 3.
    Provides a detailed audit log.
    """
    audit_logs = []
    
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        msg = "GOOGLE_API_KEY is not set."
        audit_logs.append({"model": "System", "status": "ERROR", "message": msg})
        return None, audit_logs

    # Initialize Gemini
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        audit_logs.append({"model": "System", "status": "AUTH_ERROR", "message": str(e)})
        return None, audit_logs

    # Ensure the directory exists and is writable
    try:
        os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
    except Exception as e:
        msg = f"Directory {GENERATED_IMAGE_DIR} not writable: {e}"
        audit_logs.append({"model": "System", "status": "FILE_ERROR", "message": msg})
        return None, audit_logs

    # Build a descriptive prompt
    setting = story_params.get("setting", "a magical place")
    style = "vibrant children's storybook illustration, digital art, high resolution, soft lighting"
    full_prompt = f"{description}, {setting}, {style}"

    log_entry = {"model": "imagen-3.0-generate-001", "status": "PENDING", "message": ""}
    try:
        print(f"[IMAGE] Gemini painting with Imagen 3...")
        
        # Access Imagen 3 model
        # Note: This requires the specific Imagen model ID in Gemini AI Studio
        model = genai.GenerativeModel("imagen-3.0-generate-001")
        
        # Generation call
        response = model.generate_content(full_prompt)
        
        # In the Generative AI SDK, image results are usually in the candidates bit as bytes/PIL
        # However, for Imagen 3 via AI Studio SDK, it might be in different response formats.
        # Assuming the standard 'generate_content' returns a response with image data if it's the Imagen model.
        if response and hasattr(response, 'candidates') and response.candidates:
            # Extract image from response (Imagen usually returns one or more image parts)
            # This is a generic extraction as exactly how the SDK handles Imagen bytes can vary
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') or hasattr(part, 'data'):
                    img_data = part.inline_data.data if hasattr(part, 'inline_data') else part.data
                    image = Image.open(io.BytesIO(img_data))
                    
                    filename = f"story_{uuid.uuid4().hex[:8]}.webp"
                    filepath = os.path.join(GENERATED_IMAGE_DIR, filename)

                    if image.width > 1200:
                        image.thumbnail((1200, 1200))
                    image.save(filepath, "WEBP", quality=85)
                    
                    log_entry["status"] = 200
                    log_entry["message"] = "SUCCESS"
                    audit_logs.append(log_entry)
                    print(f"[IMAGE] Success with Gemini Imagen")
                    return f"generated_images/{filename}", audit_logs

        log_entry["status"] = "INVALID_RESPONSE"
        log_entry["message"] = "Gemini Imagen returned no valid image data."
        audit_logs.append(log_entry)

    except Exception as e:
        log_entry["status"] = "GEMINI_EXCEPTION"
        log_entry["message"] = str(e)
        audit_logs.append(log_entry)
        print(f"[IMAGE] Gemini Imagen failed: {e}")

    return None, audit_logs
