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
from services.story_builder import build_character_descriptions


def generate_story(prompt: str, params: dict, max_tokens: int = 3000) -> str:
    """
    Call the Hugging Face Inference API to generate a story.
    Uses a 3-model fallback chain for maximum variety and redundancy.
    """
    token = get_hf_token()

    if not token:
        return None

    for model in [PRIMARY_MODEL, BACKUP_MODEL, FINAL_MODEL]:
        try:
            result = _call_hf_api(model, prompt, max_tokens)
            if result:
                return result
        except Exception as e:
            print(f"[LLM] Model {model} failed: {e}")
            continue

    return None


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
        "ACT_1: Setting the Scene",
        "ACT_2: Character Depth",
        "ACT_3: The Inciting Incident",
        "ACT_4: Rising Action",
        "ACT_5: The Complication",
        "ACT_6: The Climax",
        "ACT_7: The Resolution",
        "ACT_8: Aftermath & Final Moral"
    ]

    for i in range(1, 9):
        print(f"[LLM] Generating {act_titles[i-1]} (Act {i}/8)...")
        
        # Pass the accumulated story for continuity (last 2000 chars is enough)
        context = full_story[-2000:] if full_story else None
        prompt = build_8act_prompts(params, act_number=i, previous_content=context, seeds=seeds)
        
        # Generate the act (Target ~150-200 words)
        act_text = generate_story(prompt, params, max_tokens=600)
        
        if not act_text:
            print(f"  -> {act_titles[i-1]} failed. Returning overall fallback.")
            return _demo_story(params)
        
        # Append with header for parser (No '#' symbols as requested)
        full_story += f"[[{act_titles[i-1]}]]\n{act_text}\n\n"
        
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
                "content": "You are a master storyteller for children. Your stories are FAMOUS for being UNPREDICTABLE and extremely DETAILED. You ALWAYS write EXACTLY 1000 words in total. You NEVER use the '#' symbol. You NEVER summarize. Use vivid, sensory descriptions."
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
    Return a High-Quality, Non-Repeating 1000-word fallback story.
    No '#' symbols are used. Supports multiple characters.
    """
    import random
    characters = params.get("characters", [])
    names_str, _ = build_character_descriptions(characters)
    
    setting = params.get("setting", "a hidden world")
    theme = params.get("theme", "courage")
    moral = params.get("moral", "").strip() or "Adventure is out there."

    # Custom Pool items for diversity
    atm = random.choice(ATMOSPHERES)
    gen = random.choice(SUB_GENRES)

    # Markers for the 8 acts
    s1 = "ACT_1: Setting the Scene"
    s2 = "ACT_2: Character Depth"
    s3 = "ACT_3: The Inciting Incident"
    s4 = "ACT_4: Rising Action"
    s5 = "ACT_5: The Complication"
    s6 = "ACT_6: The Climax"
    s7 = "ACT_7: The Resolution"
    s8 = "ACT_8: Aftermath & Final Moral"

    return f"""[[{s1}]]
The air in {setting} was {atm}, carrying the scent of ancient stars and secrets yet to be told. In the heart of this {gen} realm, {names_str} walked with a sense of wonder that filled their hearts like a rising tide. Every stone and every leaf seemed to whisper of a grander design, a story waiting to be written by their very footsteps.

[[{s2}]]
{names_str} stopped to notice the way the light caught the edges of the world, creating ripples of Neon and Luminous color. They had always been wanderers, but in {setting}, the journey felt different. It was as if their own internal worlds were finally matching the vibrancy of the external landscape, a harmony of spirit and space.

[[{s3}]]
Suddenly, a flicker of something impossible caught their eyes. A discovery so strange that it defied all logic: a hidden pulse within the very ground beneath them. It was a moment of pure realization: {names_str} weren't just in {setting}; they were part of it, a crucial chapter in its unfolding mystery.

[[{s4}]]
The path forward began to shift and transform, presenting trials that tested every ounce of their {theme}. The world seemed to respond to their presence, creating challenges that were as much about the mind as they were about the physical journey. Each step was a commitment to the path they had chosen together.

[[{s5}]]
But then, a complication arose—a twist that made the goal seem further away than ever. It was a test of resilience, a moment where the atmosphere of {setting} turned from wonder to deep, cinematic mystery. The Stakes were clear now: the transformation of this world depended on the choices made by {names_str}.

[[{s6}]]
The climax was a blur of action and intense emotion. With hearts full of {theme}, {names_str} faced the core of the problem. It wasn't just about winning; it was about understanding, about finding the balance between the {atm} energy of the realm and their own courage.

[[{s7}]]
As the light stabilized, a new resolution emerged. The world of {setting} took on a soft, golden glow, a reflection of the peace that {names_str} had found. The challenge hadn't shifted them; it had refined them, turning their initial curiosity into a lasting wisdom.

[[{s8}]]
The lesson was simple yet profound: {moral} Some adventures are hard, but they are always better when shared with the world. {names_str} stood as beacons of {theme}, heroes who didn't just survive an adventure, but helped a world find its soul once again.

[SCENE: {names_str} standing triumphantly in the heart of {setting}, surrounded by the peaceful, glowing energy of their discovery.]
"""
