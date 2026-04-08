import os
import requests
import json
from services.hf_utils import (
    HF_API_URL, get_hf_token, get_hf_headers, 
    DEFAULT_TIMEOUT, RETRY_WAIT_TIME
)

# Model Chain
# 1. Mistral (Most Creative)
# 2. Zephyr (Fast & Reliable)
# 3. Llama (Last Resort)
PRIMARY_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
BACKUP_MODEL = "HuggingFaceH4/zephyr-7b-beta"
FINAL_MODEL = "meta-llama/Llama-3.2-3B-Instruct"

from services.story_pools import (
    PLOT_ARCHETYPES, SURPRISE_TWISTS, NARRATIVE_STYLES, 
    SUB_GENRES, PLOT_SPARKS, ATMOSPHERES
)


def generate_story(prompt: str, params: dict, max_tokens: int = 900) -> str:
    """
    Call the Hugging Face Inference API to generate a story.
    Uses a 3-model fallback chain for maximum variety and redundancy.
    """
    token = get_hf_token()

    if not token:
        return _demo_story(params)

    for model in [PRIMARY_MODEL, BACKUP_MODEL, FINAL_MODEL]:
        try:
            result = _call_hf_api(model, prompt, max_tokens)
            if result:
                return result
        except Exception as e:
            print(f"[LLM] Model {model} failed: {e}")
            continue

    # If all models fail, return a dynamic fallback story
    return _demo_story(params)


def generate_story_iterative(params: dict, age_cfg: dict) -> str:
    """
    Generate a long-form story iteratively, section by section.
    This guarantees high word counts (1000+) for older age groups.
    """
    from services.story_builder import build_section_prompt, set_seeds
    
    seeds = set_seeds(params)
    sections = ["Introduction", "Challenge", "Resolution", "Moral"]
    full_story = ""
    
    for section_name in sections:
        # Increase max_tokens per section call for 9-12 age group
        # (approx 400-500 tokens per section)
        sec_max_tokens = 600
        
        prompt = build_section_prompt(params, section_name, full_story, seeds)
        print(f"[LLM] Generating {section_name} iteratively...")
        
        # Use existing fallback chain for each section
        section_text = generate_story(prompt, params, max_tokens=sec_max_tokens)
        
        # Format the assembled story with headers
        full_story += f"## {section_name}\n{section_text}\n\n"
        
    return full_story


def _call_hf_api(model: str, prompt: str, max_tokens: int) -> str | None:
    """Make the actual API call using messages format."""
    url = f"{HF_API_URL}{model}/v1/chat/completions"
    headers = get_hf_headers()

    # System instruction reinforces the 'Taboo' and 'No Repeats' rules
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a master storyteller for children. Your stories are FAMOUS for being UNPREDICTABLE and having a SHOCKING SURPRISE EFFECT. You ALWAYS write long, detailed, and descriptive stories that meet the requested word count. You NEVER use 'puzzle-solving' as a resolution. You NEVER repeat a plot. You NEVER use 'Clockwork Trains' or 'Golden Cogs'. Your stories are vibrant, creative, and completely original."
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
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"].strip()
        elif response.status_code == 503:
            # Model loading, wait and retry once
            import time
            time.sleep(RETRY_WAIT_TIME)
            response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[LLM] Error calling model {model}: {e}")

    return None


def _demo_story(params: dict) -> str:
    """
    Return a Dynamic Fallback Story.
    Unlike the previous static templates, this builds a unique story structure locally
    using random pools to ensure no two backups are ever the same.
    """
    import random
    characters = params.get("characters", [])
    if not characters:
        characters = [{"name": "Luna", "traits": ["brave", "curious"]}]
    
    main_char = characters[0].get("name", "Luna")
    friends = [c.get("name") for c in characters[1:] if c.get("name")]
    friend_text = ", ".join(friends) if friends else "their shadow-pal"
    
    setting = params.get("setting", "a hidden world")
    theme = params.get("theme", "teamwork")
    moral = params.get("moral", "").strip() or "The secret to success is believing in each other."

    # Pick dynamic variety seeds locally
    arch = random.choice(PLOT_ARCHETYPES)
    twist = random.choice(SURPRISE_TWISTS)
    style = random.choice(NARRATIVE_STYLES)
    spark = random.choice(PLOT_SPARKS)
    atm = random.choice(ATMOSPHERES)
    gen = random.choice(SUB_GENRES)

    return f"""## Introduction

The air in {setting} was {atm}. In the middle of this {gen} world, {main_char} and {friend_text} were suddenly faced with a strange discovery: {spark} It was a moment they would never forget.

[SCENE: {main_char} and {friend_text} looking amazed at {spark} in the {atm} light of {setting}]

## Challenge

But things grew even more complicated. {arch} Every way they turned, {twist} The world of {setting} seemed to be reacting to their very thoughts, creating a scenario that no one could have predicted.

[SCENE: {main_char} and {friend_text} in the middle of a surreal, shifting landscape where {spark} is changing everything]

## Resolution

Finally, instead of a predictable solution, a moment of pure {style} transformed the situation. By embracing the {atm} energy of {setting}, they didn't just solve the problem—they redefined it. It was a {twist} that left even the stars of {setting} blinking in surprise.

[SCENE: A spectacular transformation of {setting}, where {main_char} and {friend_text} are surrounded by the {gen} magic of their discovery]

## Moral

{main_char} looked at {friend_text} and realized that {moral} Some adventures are hard, but they are always better when shared.

[SCENE: A beautiful, final moment showing {main_char} and their friends in a peaceful {setting}]

{moral}

*And they all lived with {theme} in their hearts, ever after.*"""
