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


def generate_story(prompt: str, params: dict, max_tokens: int = 900) -> str:
    """
    Call the Hugging Face Inference API to generate a story.
    Uses chat-completion format for Llama/Mistral instruct models.
    Falls back gracefully if the API is unavailable.
    """
    token = os.environ.get("HF_TOKEN", "")

    if not token:
        return _demo_story(params)

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            result = _call_hf_api(model, prompt, max_tokens)
            if result:
                return result
        except Exception as e:
            print(f"[LLM] Model {model} failed: {e}")
            continue

    # If all models fail, return a demo story
    return _demo_story(params)


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


def _demo_story(params: dict) -> str:
    """
    Return a dynamic demo story based on user parameters.
    This provides a fallback when no API token is configured.
    """
    characters = params.get("characters", [])
    main_char = characters[0].get("name", "Luna") if characters else "Luna"
    traits = ", ".join(characters[0].get("traits", ["brave", "curious"])) if characters else "brave and curious"
    setting = params.get("setting", "an enchanted forest")
    theme = params.get("theme", "kindness")
    moral = params.get("moral", "Kindness always finds its way back to you.")

    # Second character if available
    friend = characters[1].get("name", "Benny") if len(characters) > 1 else "Benny"
    friend_traits = ", ".join(characters[1].get("traits", ["kind", "fast"])) if len(characters) > 1 else "kind and loyal"

    return f"""## Introduction

Once upon a time, in the heart of {setting}, there lived a young hero named {main_char}. {main_char} was known by everyone for being {traits}, and they loved exploring every corner of their magical home.

[SCENE: {main_char} standing at the edge of the woods in {setting}, the morning sun painting the sky in beautiful colors, ready for a new adventure]

One morning, {main_char} discovered something very unusual. Resting under a giant leaf was a tiny creature that looked lost. "Oh dear," said {main_char} softly. "Don't be afraid. I'm here to help you find your way."

## Challenge

But soon {main_char} realized the task was harder than they thought. The path back to the creature's home was blocked by a fast-flowing river they had never seen before. None of the usual shortcuts seemed to work, and the sun was starting to set.

[SCENE: {main_char} and {friend} standing by a sparkling, rushing river in {setting}, looking determined as they try to figure out a safe way to cross]

"{main_char}, we should try to build a bridge!" suggested {friend}, who had just arrived to help. But the logs were too heavy and the current was too strong. {main_char} felt a little nervous. The forest was getting darker and they didn't want the little creature to be scared. But then {main_char} remembered the importance of {theme}, and they knew they couldn't give up.

## Resolution

Together, {main_char} and {friend} decided to ask the other animals for help. By working as a team and showing everyone how important {theme} is, they managed to gather enough branches and vines to weave a strong, safe bridge.

[SCENE: All the forest animals working together under the guidance of {main_char} and {friend}, successfully finishing a beautiful woven bridge over the river]

They carefully helped the little creature across. As they reached the other side, the creature let out a happy whistle and scurried safely back to its family. {main_char} felt a warmth in their heart that were brighter than any sun. They had shown that even small acts of {theme} can solve the biggest problems.

## Moral

As the stars began to twinkle over {setting}, {main_char} and {friend} walked back home, feeling proud of what they had accomplished. {main_char} learned that day that no challenge is too big when you have a heart full of {theme}.

[SCENE: {main_char} and {friend} sitting together under a clear starry sky in {setting}, smiling with happy and peaceful hearts]

{moral}

*And they all lived with {theme} in their hearts, ever after.*"""
