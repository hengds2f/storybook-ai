import os
import requests
import json
from services.hf_utils import (
    HF_API_URL, get_hf_token, get_hf_headers, 
    DEFAULT_TIMEOUT, RETRY_WAIT_TIME
)

# Primary model — fast, good quality, free tier
PRIMARY_MODEL = "meta-llama/Llama-3.2-3B-Instruct"
# Fallback model if primary is unavailable
FALLBACK_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"


def generate_story(prompt: str, params: dict, max_tokens: int = 900) -> str:
    """
    Call the Hugging Face Inference API to generate a story.
    Uses chat-completion format for Llama/Mistral instruct models.
    Falls back gracefully if the API is unavailable.
    """
    token = get_hf_token()

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
    headers = get_hf_headers()

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
        "temperature": 0.95,
        "top_p": 0.95,
        "stream": False
    }

    response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)

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
        time.sleep(RETRY_WAIT_TIME)
        response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()

    else:
        print(f"[LLM] API error {response.status_code}: {response.text[:200]}")

    return None


def _demo_story(params: dict) -> str:
    """
    Return a dynamic, randomized fallback story.
    COMPLETELY REMOVED the 'giant leaf' repetition. 
    This engine ensures variety even when the AI is busy.
    """
    import random
    characters = params.get("characters", [])
    if not characters:
        characters = [{"name": "Luna", "traits": ["brave", "curious"]}]
    
    main_char = characters[0].get("name", "Luna")
    all_names = ", ".join([c.get("name") for c in characters if c.get("name")])
    setting = params.get("setting", "a magical world")
    theme = params.get("theme", "friendship")
    moral = params.get("moral", "").strip() or "Together, anything is possible."

    # Multi-Plot Fallback Templates
    TEMPLATES = [
        # Template 1: Space Adventure
        {
            "intro": f"High above {setting}, among the twinkling stars, {main_char} and their friends {all_names} were piloting a shimmering star-scooter. They were on a mission to deliver a bucket of moonlight to the sleepy moon-fishes.",
            "scene1": f"{main_char} and {all_names} soaring through space with a bucket of glowing moonlight",
            "challenge": f"Suddenly, a friendly space-whale accidentally sneezed a giant bubble of stardust that blocked their path. The star-scooter began to spin! They needed to find a way to navigate through the sticky, sparkly stardust before the moon-fishes woke up.",
            "scene2": f"The star-scooter caught in a giant, shimmering bubble of pink and gold stardust",
            "res": f"Using the power of {theme}, they all hummed a harmony that vibrated the stardust bubble away. The space-whale realized its mistake and gave them a gentle push with its fin, helping them reach the moon just in time.",
            "scene3": f"{all_names} laughing and waving to a giant, friendly space-whale as they land on the moon"
        },
        # Template 2: Underwater Mystery
        {
            "intro": f"Deep beneath the waves of {setting}, {main_char} and {all_names} were swimming through the coral gardens. They were wearing magical bubble-helmets that let them talk to the singing seahorses.",
            "scene1": f"{main_char} and {all_names} in bubble-helmets swimming through a forest of rainbow coral",
            "challenge": f"The seahorses had lost their singing voices! A mischievous current had carried their songs away into the dark, silent trenches of the deep. {all_names} had to find the 'Echo Cave' to get the music back.",
            "scene2": f"{all_names} looking brave as they swim towards a glowing cave at the bottom of the sea",
            "res": f"In the Echo Cave, they discovered that if they all shared their favorite memories of {theme}, the music would grow back. Their voices combined into a beautiful melody that returned the seahorses' songs to the whole reef.",
            "scene3": f"The seahorses dancing and singing around {all_names} in a swirl of bubbles and notes"
        },
        # Template 3: Toy World
        {
            "intro": f"In the center of {setting}, there was a secret door that led to the Land of Lost Toys. {main_char} and {all_names} stepped inside and discovered they were now the same size as the building blocks!",
            "scene1": f"{main_char} and {all_names} looking tiny as they stand next to giant colorful building blocks",
            "challenge": f"The great Clockwork Train had stopped running because one of its golden cogs had gone missing. Without the train, all the toys in the land were stuck! They had to climb the tallest mountain of stuffed bears to find it.",
            "scene2": f"{all_names} climbing up a soft, fuzzy mountain made of teddy bears of all colors",
            "res": f"Working together with {theme}, they found the golden cog hidden in a bear's pocket. They slid down the mountain and placed the cog back, making the train let out a happy whistle and start its wheels again.",
            "scene3": f"A giant colorful clockwork train chugging through a land of toys with {all_names} waving from the window"
        }
    ]

    t = random.choice(TEMPLATES)

    return f"""## Introduction

{t['intro']}

[SCENE: {t['scene1']}]

## Challenge

{t['challenge']}

[SCENE: {t['scene2']}]

## Resolution

{t['res']}

[SCENE: All the characters celebrating together, showing the true power of {theme}]

## Moral

{t['res'].split('.')[0]}. {main_char} and their friends {all_names} realized that no challenge is too big when you have {theme} on your side.

[SCENE: {t['scene3']}]

{moral}

*And they all lived with {theme} in their hearts, ever after.*"""
