import os
import requests
from dotenv import load_dotenv

# Base URL for Hugging Face Inference API
# New Hugging Face Inference Router (Legacy Inference API is decommissioned)
HF_API_URL = "https://router.huggingface.co/"

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

def check_token_status() -> dict:
    """
    Verify if the current HF_TOKEN is valid by calling the HF whoami-v2 endpoint.
    Returns status info for diagnostics.
    """
    token = get_hf_token()
    if not token:
        return {"valid": False, "reason": "Missing token"}
    
    try:
        # Check token validity by calling /whoami-v2
        url = "https://huggingface.co/api/whoami-v2"
        headers = get_hf_headers()
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "valid": True, 
                "username": data.get("name", "Unknown"),
                "auth_type": data.get("type", "Unknown"),
                "can_inference": True # Successfully authenticated tokens are usually ready for inference
            }
        else:
            return {
                "valid": False, 
                "status_code": response.status_code,
                "reason": response.json().get("error", response.text[:100]) if response.status_code != 404 else "Invalid endpoint"
            }
    except Exception as e:
        return {"valid": False, "reason": str(e)}
