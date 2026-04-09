import os
from dotenv import load_dotenv

# Load environment variables using absolute path to ensure accuracy
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=dotenv_path)

# --- AI Engine Selection ---
# Set the primary engine for story narrative generation
TEXT_GEN_ENGINE = "google-gemini"

# Set the primary engine for image generation
IMAGE_GEN_ENGINE = "huggingface"

# --- Google Gemini Configuration ---
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL_STANDARD = "gemini-flash-latest"
GEMINI_MODEL_PRO = "gemini-pro-latest"

# --- Hugging Face Configuration ---
HF_API_KEY = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
HF_IMAGE_MODEL = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
HF_TEXT_MODEL = os.environ.get("HF_TEXT_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

def get_gemini_key():
    return os.environ.get("GOOGLE_API_KEY") or GEMINI_API_KEY

# --- Narrative Engine Settings ---
# Seed for narrative variety
STORY_SEED_LENGTH = 8
ACT_COUNT = 8

# Sections mapping for UI
UI_SECTIONS = {
    "introduction": [1, 2],
    "challenge": [3, 4, 5],
    "resolution": [6, 7],
    "moral": [8]
}
