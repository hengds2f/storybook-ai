import os
from dotenv import load_dotenv

# Load environment variables using absolute path to ensure accuracy
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=dotenv_path)

# --- AI Engine Selection ---
# Set the primary engine for story narrative generation
TEXT_GEN_ENGINE = os.environ.get("TEXT_GEN_ENGINE", "google-gemini")

# Set the primary engine for image generation
IMAGE_GEN_ENGINE = os.environ.get("IMAGE_GEN_ENGINE", "openai-dalle")

# --- Google Gemini Configuration ---
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL_STANDARD = "gemini-1.5-flash"
GEMINI_MODEL_PRO = "gemini-1.5-pro"

# --- OpenAI Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_IMAGE_MODEL = "dall-e-3"
IMAGE_SIZE = "1024x1024"
IMAGE_QUALITY = "standard"

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
