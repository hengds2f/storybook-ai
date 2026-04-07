import os
import requests
import json


HF_API_URL = "https://api-inference.huggingface.co/models/"

# Primary model — fast, good quality, free tier
PRIMARY_MODEL = "meta-llama/Llama-3.2-3B-Instruct"
# Fallback model if primary is unavailable
FALLBACK_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"


def _get_headers() -> dict:
    token = os.environ.get("HF_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def generate_story(prompt: str, max_tokens: int = 900) -> str:
    """
    Call the Hugging Face Inference API to generate a story.
    Uses chat-completion format for Llama/Mistral instruct models.
    Falls back gracefully if the API is unavailable.
    """
    token = os.environ.get("HF_TOKEN", "")

    if not token:
        return _demo_story(prompt)

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            result = _call_hf_api(model, prompt, max_tokens)
            if result:
                return result
        except Exception as e:
            print(f"[LLM] Model {model} failed: {e}")
            continue

    # If all models fail, return a demo story
    return _demo_story(prompt)


def _call_hf_api(model: str, prompt: str, max_tokens: int) -> str | None:
    """Make the actual API call using messages format."""
    url = f"{HF_API_URL}{model}/v1/chat/completions"
    headers = _get_headers()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a warm, creative children's story writer. You write engaging, age-appropriate stories with vivid imagery and clear moral lessons."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.85,
        "top_p": 0.9,
        "stream": False
    }

    response = requests.post(url, headers=headers, json=payload, timeout=120)

    if response.status_code == 200:
        data = response.json()
        # Chat completions format
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"].strip()
        # Legacy text-generation format
        if isinstance(data, list) and data:
            generated = data[0].get("generated_text", "")
            # Remove the prompt from the output
            if prompt in generated:
                return generated.replace(prompt, "").strip()
            return generated.strip()

    elif response.status_code == 503:
        print(f"[LLM] Model {model} is loading, retrying...")
        import time
        time.sleep(15)
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()

    else:
        print(f"[LLM] API error {response.status_code}: {response.text[:200]}")

    return None


def _demo_story(prompt: str) -> str:
    """
    Return a demo story when no API token is configured.
    This allows testing the full app UI without an API key.
    """
    return """## Introduction

Once upon a time, in a cozy little village nestled between rolling green hills, there lived a young fox named Luna. Luna had bright amber eyes, a fluffy russet tail, and a heart full of curiosity.

[SCENE: Luna standing at the edge of her village, the morning sun painting the sky in shades of orange and pink, a path stretching ahead into a sparkling forest]

One morning, Luna discovered something wonderful — a tiny bluebird with a broken wing sitting under the old oak tree by the village fountain. "Oh dear," said Luna softly, her ears perking up with concern. "You must be frightened all alone."

## Challenge

Luna wanted to help the little bird, whose name was Pip, but she didn't know how to heal a broken wing. None of her friends had seen anything like it before either.

[SCENE: Luna and her friends Benny the rabbit and Cleo the hedgehog gathered around little Pip, all looking worried but thoughtful, their heads together in problem-solving]

"We should try to find the wise old Owl," suggested Benny, twitching his nose nervously. But the Owl lived in the deep part of the forest — a place none of them had ever dared to go. Luna felt her heart beat a little faster. The forest was dark and the path was unknown. But then she looked down at little Pip, trembling and frightened, and she knew what she had to do.

## Resolution

Together, Luna, Benny, and Cleo ventured into the deep forest. They helped each other over logs, shared their snacks when they got tired, and cheered each other on when the shadows felt too deep. Finally, they reached the Owl's great tree.

[SCENE: The friends emerging into a sunlit clearing where a magnificent old owl sits in a grand tree, his eyes wise and kind, welcoming them warmly]

The wise Owl carefully wrapped Pip's tiny wing and showed Luna how to make a little splint from a soft twig and a piece of moss. "You showed great kindness today," said the Owl gently, "and even greater courage." As they carried Pip safely back to the village, the little bird began to sing — a sweet, grateful melody that danced through the whole forest.

## Moral

Weeks later, when Pip's wing was fully healed and he could fly again, he returned every single morning to sing outside Luna's window. Luna learned that day that helping someone who is afraid costs nothing but a little courage — and that kindness always finds its way back to you.

[SCENE: Luna watching Pip soar freely into a bright blue sky above the village, her friends beside her, all of them smiling with warm and happy hearts]

*And they all lived with kindness in their hearts, ever after.*"""
