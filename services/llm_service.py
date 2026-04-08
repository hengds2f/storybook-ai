import os
import requests
import json
from services.hf_utils import (
    HF_API_URL, get_hf_token, get_hf_headers, 
    DEFAULT_TIMEOUT, RETRY_WAIT_TIME
)

# Model Chain
# 1. Qwen 72B (Extreme Instruction Following & Verbosity)
# 2. Llama 3.1 70B (High Quality & Reliability)
# 3. Llama 3.2 3B (Fast Backup)
PRIMARY_MODEL = "Qwen/Qwen2.5-72B-Instruct"
BACKUP_MODEL = "meta-llama/Llama-3.1-70B-Instruct"
FINAL_MODEL = "meta-llama/Llama-3.2-3B-Instruct"

from services.story_pools import (
    PLOT_ARCHETYPES, SURPRISE_TWISTS, NARRATIVE_STYLES, 
    SUB_GENRES, PLOT_SPARKS, ATMOSPHERES
)


def generate_story(prompt: str, params: dict, max_tokens: int = 3000) -> str:
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


def count_words(text: str) -> int:
    """Accurately count words in a story string."""
    if not text:
        return 0
    import re
    # Remove headers and scene tags to count only narrative words
    clean_text = re.sub(r'##\s*.*?\n|\[SCENE:.*?\]', '', text, flags=re.DOTALL)
    return len(clean_text.split())


def generate_story_8act(params: dict) -> str:
    """
    The 8-Act Narrative Engine.
    Performs 8 sequential API calls (~150 words each) to guarantee 1200+ words.
    Bypasses the Hugging Face Inference API response token limits.
    """
    from services.story_builder import build_8act_prompts, set_seeds
    
    seeds = set_seeds(params)
    full_story = ""
    
    act_titles = [
        "ACT 1: Setting the Scene",
        "ACT 2: Character Depth",
        "ACT 3: The Inciting Incident",
        "ACT 4: Rising Action",
        "ACT 5: The Complication",
        "ACT 6: The Climax",
        "ACT 7: The Resolution",
        "ACT 8: Aftermath & Final Moral"
    ]

    for i in range(1, 9):
        print(f"[LLM] Generating {act_titles[i-1]} (Act {i}/8)...")
        
        # Pass the accumulated story for continuity (last 2000 chars is enough)
        context = full_story[-2000:] if full_story else None
        prompt = build_8act_prompts(params, act_number=i, previous_content=context, seeds=seeds)
        
        # Generate the act (Target ~150-200 words)
        act_text = generate_story(prompt, params, max_tokens=600)
        
        # Append with header for parser
        full_story += f"\n\n## {act_titles[i-1]}\n{act_text}\n"
        
        print(f"  -> {act_titles[i-1]} completed. Current total: {len(full_story.split())} words.")

    return full_story


def expand_content(text: str, params: dict, section_type: str, seeds: dict) -> str:
    """Instruct the AI to lengthen existing content with sensory detail."""
    current_count = count_words(text)
    print(f"[EXPAND] Expanding {section_type} (Current: {current_count} words)...")
    
    expansion_prompt = f"""You are a master of DESCRIPTIVE EXPANSION.
    The following {section_type} of our story is only {current_count} words long. I need it shortened? NO. I need it LONGER.
    
    TASK: Rewrite the following text but make it TWICE AS LONG (at least 500 words).
    
    RULES:
    - Include 3 new paragraphs of SENSORY details (smell, feel, sound).
    - Add deep INTERNAL MONOLOGUE for the characters.
    - Describe the atmosphere and environment in exquisite detail.
    - KEEP THE PLOT THE SAME. Just ELABORATE.
    - Maintain headers (##) and scene tags ([SCENE:]).
    
    ORIGINAL TEXT:
    {text}
    
    Begin rewriting and expanding now (Target: 500+ words):"""
    
    expanded_text = generate_story(expansion_prompt, params, max_tokens=1500)
    return expanded_text if count_words(expanded_text) > current_count else text


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
                "content": "You are a master storyteller for children. Your stories are FAMOUS for being UNPREDICTABLE, SHOCKINGLY ORIGINAL, and extremely DETAILED. You ALWAYS write EXACTLY 1000 words. You NEVER summarize; instead, you use vivid, sensory descriptions and deep world-building to reach the word count. You NEVER use 'puzzle-solving' as a resolution. You NEVER repeat a plot. Your stories are vibrant and completely original."
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
