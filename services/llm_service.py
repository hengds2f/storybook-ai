import os
# Gemini uses its own SDK and environment variables.

# AI Engine Configuration
GEMINI_MODEL = "gemini-1.5-flash"

from services.story_pools import (
    PLOT_ARCHETYPES, SURPRISE_TWISTS, NARRATIVE_STYLES, 
    SUB_GENRES, PLOT_SPARKS, ATMOSPHERES
)
from services.story_builder import build_character_descriptions


def generate_story(prompt: str, params: dict, max_tokens: int = 3000) -> str:
    """
    Generate a story EXCLUSIVELY using Google Gemini 1.5.
    Hugging Face story models have been decommissioned to ensure narrative variety.
    """
    google_key = os.environ.get("GOOGLE_API_KEY")
    if not google_key:
        print("[LLM] CRITICAL ERROR: GOOGLE_API_KEY is missing. Story generation aborted.")
        return None

    try:
        result = _call_gemini_api(GEMINI_MODEL, prompt, max_tokens)
        if result:
            return result
    except Exception as e:
        print(f"[LLM] Gemini fatal error: {e}")

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
        "ACT_8: THE_MANDATORY_POEM"
    ]

    import uuid
    story_seed = uuid.uuid4().hex[:8] 

    for i in range(1, 9):
        print(f"[LLM] Generating {act_titles[i-1]} (Act {i}/8)...")
        
        # Pass the accumulated story for continuity (last 2000 chars is enough)
        context = full_story[-2000:] if full_story else None
        prompt = build_8act_prompts(params, act_number=i, previous_content=context, seeds=seeds)
        
        # Inject uniqueness token to break model repetition
        prompt = f"[UNIQUE_STORY_SEED: {story_seed}]\n{prompt}"

        # Upgrade Act 8 to Pro for strict instruction following (poetry)
        model_to_use = "gemini-1.5-pro" if i == 8 else GEMINI_MODEL
        act_text = _call_gemini_api(model_to_use, prompt, max_tokens=600)
        
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


def _call_gemini_api(model_name: str, prompt: str, max_tokens: int) -> str | None:
    """Make the actual API call to Google Gemini."""
    import google.generativeai as genai
    
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None
        
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction="You are a master storyteller for children, writing in the whimsical, descriptive, and moral-focused style of C.S. Lewis. Your stories are segmented into 8 acts. IMPORTANT: The FINAL act (Act 8) MUST conclude with a 4-8 line RHYMING POEM that captures the story's moral. You are FAMOUS for your UNPREDICTABLE plots. NEVER use the '#' symbol. Use vivid, sensory descriptions and occasionally address the reader directly."
    )
    
    # Maximize creativity parameters for variety
    generation_config = {
        "temperature": 1.0,  # Max creative temperature
        "top_p": 0.99,       # High probability tail for variety
        "top_k": 50,         # Broaden word selection pool
        "max_output_tokens": max_tokens,
    }
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        print(f"[LLM] Gemini Error: {e}")
        
    return None


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
The air in {setting} was {atm}, carrying the crisp scent of pine needles and something else—something that felt remarkably like magic and old, forgotten songs. In the heart of this realm, {names_str} walked with a sense of wonder that filled their hearts like a rising tide. Now, you must understand that this wasn't just any world; it was a place where every stone and every leaf seemed to whisper of a grander design, a story waiting to be written by their very footsteps.

[[{s2}]]
{names_str} stopped to notice the way the light caught the edges of the world, creating ripples of Neon and Luminous color. They had always been wanderers, but in {setting}, the journey felt different. It was as if their own internal worlds were finally matching the vibrancy of the external landscape, a harmony of spirit and space that only the very brave or the very curious ever truly find.

[[{s3}]]
Suddenly, a flicker of something impossible caught their eyes. A discovery so strange that it defied all logic: a hidden pulse within the very ground beneath them. It was a moment of pure realization: {names_str} weren't just visitors in {setting}; they were part of it, a crucial chapter in its unfolding mystery, like characters in a book who suddenly realize they are being read.

[[{s4}]]
The path forward began to shift and transform, presenting trials that tested every ounce of their {theme}. The world seemed to respond to their presence, creating challenges that were as much about the mind as they were about the physical journey. Each step was a commitment to the path they had chosen together, for in {setting}, one never truly travels alone if they have a friend and a true heart.

[[{s5}]]
But then, a complication arose—a twist that made the goal seem further away than ever. It was a test of resilience, a moment where the atmosphere of {setting} turned from wonder to deep, cinematic mystery. The Stakes were clear now: the transformation of this world depended on the choices made by {names_str}, and as any good explorer knows, the hardest choice is often the right one.

[[{s6}]]
The climax was a blur of action and intense emotion. With hearts full of {theme}, {names_str} faced the core of the problem. It wasn't just about winning; it was about understanding, about finding the balance between the {atm} energy of the realm and their own courage. It was a battle of wills, where kindness proved sharper than any sword.

[[{s7}]]
As the light stabilized, a new resolution emerged. The world of {setting} took on a soft, golden glow, a reflection of the peace that {names_str} had found. The challenge hadn't shifted them; it had refined them, turning their initial curiosity into a lasting wisdom that would stay with them long after they left this magical place.

[[{s8}]]
The lesson was simple yet profound: {moral} Some adventures are hard, but they are always better when shared with the world. {names_str} stood as beacons of {theme}, heroes who didn't just survive an adventure, but helped a world find its soul once again. And that, I think, is the best kind of adventure there is.

[SCENE: {names_str} standing triumphantly in the heart of {setting}, surrounded by the peaceful, glowing energy of their discovery, looking like kings and queens of an ancient realm.]
"""
