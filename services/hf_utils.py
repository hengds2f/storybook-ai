import os
from dotenv import load_dotenv

# Base URL for Hugging Face Inference API
HF_API_URL = "https://api-inference.huggingface.co/models/"

# Standard timeout for all AI service requests
DEFAULT_TIMEOUT = 120

# Standard wait time for 503 Service Unavailable (model loading)
RETRY_WAIT_TIME = 15

def get_hf_token() -> str:
    """
    Retrieve the Hugging Face API token from environment variables.
    Works with both local .env files and Hugging Face Space Secrets.
    """
    # Only load_dotenv if we're not in an environment where it's already set (like HF Spaces)
    # but calling it multiple times is harmless.
    load_dotenv()
    return os.environ.get("HF_TOKEN", "")

def get_hf_headers(content_type: str = "application/json") -> dict:
    """
    Generate standard headers for Hugging Face API requests.
    """
    token = get_hf_token()
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    return headers
