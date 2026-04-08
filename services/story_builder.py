import re
import random


from services.story_pools import (
    PLOT_ARCHETYPES, SURPRISE_TWISTS, NARRATIVE_STYLES, 
    SUB_GENRES, PLOT_SPARKS, ATMOSPHERES, TABOO_ITEMS
)


# ── Age configuration ─────────────────────────────────────────────────────────

AGE_CONFIG = {
    "3-5": {
        "label": "Ages 3–5",
        "vocabulary": "very simple words, short sentences, lots of repetition",
        "length": "1000 words",
        "complexity": "simple and magical, with clear cause-and-effect",
        "max_tokens": 2000
    },
    "6-8": {
        "label": "Ages 6–8",
        "vocabulary": "simple but varied vocabulary, moderate sentence length",
        "length": "1000 words",
        "complexity": "engaging with a clear problem to solve",
        "max_tokens": 2000
    },
    "9-12": {
        "label": "Ages 9–12",
        "vocabulary": "richer vocabulary with descriptive language",
        "length": "1000 words",
        "complexity": "more nuanced with character development and descriptive scenes",
        "max_tokens": 2000
    }
}


def set_seeds(params: dict) -> dict:
    """Select and persist randomized narrative seeds for iterative generation."""
    return {
        "archetype": random.choice(PLOT_ARCHETYPES),
        "twist": random.choice(SURPRISE_TWISTS),
        "style": random.choice(NARRATIVE_STYLES),
        "genre": random.choice(SUB_GENRES),
        "spark": random.choice(PLOT_SPARKS),
        "atm": random.choice(ATMOSPHERES)
    }


def build_prompt(params: dict, seeds: dict = None) -> str:
    """
    Assemble a structured story generation prompt for a single-shot 1000-word story.
    ULTRA-STRENGTHENED for maximum length and descriptive richness.
    """
    age_group = params.get("age_group", "6-8")
    cfg = AGE_CONFIG.get(age_group, AGE_CONFIG["6-8"])

    characters = params.get("characters", [])
    char_list = []
    for i, c in enumerate(characters, 1):
        name = c.get("name", "").strip()
        traits = ", ".join(c.get("traits", []))
        if name:
            char_list.append(f"{i}. {name}: {traits}" if traits else f"{i}. {name}")
    
    characters_text = "\n".join(char_list) if char_list else "1. A brave young child"
    char_count = len(char_list) if char_list else 1

    setting = params.get("setting", "a magical world")
    theme = params.get("theme", "friendship")
    moral = params.get("moral", "").strip() or "The unexpected path is often the best one."

    # Use provided seeds or pick randomized ones
    s = seeds if seeds else set_seeds(params)

    prompt = f"""You are a master children's story writer. Your task is to write a complete, one-of-a-kind original story.
    
    CRITICAL REQUIREMENT: The story MUST be EXACTLY 1000 words long. 
    Use extreme descriptive detail, sensory world-building (smell, sound, texture), and deep internal monologues to reach the 1000-word goal. 
    Do NOT summarize any part of the story.

    NARRATIVE SPECIFICATIONS:
    - Age Group: {cfg['label']}
    - Target Length: 1000 words (MANDATORY)
    - Sub-Genre: {s['genre']}
    - Atmosphere: {s['atm']}
    - Tone & Style: {s['style']}
    - Plot Spark: {s['spark']}
    - Ending: Must be UNPREDICTABLE with a genuine SURPRISE EFFECT.
    
    CHARACTERS:
    {characters_text}
    
    SETTING: {setting}
    
    THEME: {theme}
    
    STORY STRUCTURE — You MUST include these four sections with header tags:
    
    ## Introduction
    [Dive deep into the world and characters. Set the scene with rich, immersive descriptions.]
    
    ## Challenge
    [Escalate the situation using the Plot Archetype: {s['archetype']}. Introduce the Plot Spark: {s['spark']} and the Surprise Turn: {s['twist']}.]
    
    ## Resolution
    [The shocking and unpredictable climax and resolution. Absolutely NO puzzle-solving ending.]
    
    ## Moral
    [A beautiful, non-standard reflection on the experience.]
    
    Important rules:
    - {s['genre']} and {s['spark']} must be central to the story.
    - Each [SCENE: description] must be cinematic and striking for an AI illustrator.
    - Do NOT include any meta-commentary.
    
    Begin the 1000-word story now:"""

    return prompt


def build_act_prompt(params: dict, act_number: int, act1_content: str = None, seeds: dict = None) -> str:
    """
    Assemble a focused prompt for a specific Act (Introduction/Challenge or Resolution/Moral).
    Enforces extreme length (~500 words per Act) to reach 1000 total.
    """
    age_group = params.get("age_group", "6-8")
    cfg = AGE_CONFIG.get(age_group, AGE_CONFIG["6-8"])
    
    characters = params.get("characters", [])
    characters_text = ", ".join([c.get("name", "Hero") for c in characters])
    setting = params.get("setting", "a magical world")
    theme = params.get("theme", "friendship")
    
    s = seeds
    
    if act_number == 1:
        prompt = f"""You are a master storyteller. We are writing PART ONE (the first 500 words) of a 1000-word story.
        
        CONTEXT:
        - Sub-Genre: {s['genre']}
        - Atmosphere: {s['atm']}
        - Narrative Style: {s['style']}
        - Characters: {characters_text}
        - Setting: {setting}
        
        TASK: Write ONLY the '## Introduction' and '## Challenge' sections.
        
        MANDATORY RULES:
        - You MUST write at least 500 words total for this part.
        - Dive deep into every sensory detail. Describe the air, the colors, the sounds, and the character's internal thoughts at great length.
        - Do NOT summarize any action. Expand every moment.
        - Include the Plot Archetype: {s['archetype']} and the Plot Spark: {s['spark']}.
        - Format with '## Introduction' and '## Challenge' headers.
        
        Begin PART ONE of the 1000-word story now:"""
    else:
        prompt = f"""You are a master storyteller. We are writing PART TWO (the final 500 words) of a 1000-word story.
        
        CONTEXT:
        - Part One was already written (see below).
        - Characters: {characters_text}
        - Theme: {theme}
        
        TASK: Write ONLY the '## Resolution' and '## Moral' sections.
        
        MANDATORY RULES:
        - You MUST write at least 500 words total for this part.
        - Use extreme detail to expand the climax. Describe every breath and every shifting shadow.
        - Ensure an UNPREDICTABLE and SHOCKING Resolution (No puzzles!).
        - Include a Surprise Turn: {s['twist']}.
        - Format with '## Resolution' and '## Moral' headers.
        
        HERE IS PART ONE FOR CONTINUITY:
        {act1_content}
        
        Begin PART TWO (the final 500 words) now:"""
        
    return prompt


def parse_story(raw_text: str, params: dict) -> dict:
    """
    Parse the LLM output into structured story sections.
    Returns a dict with title, sections (list of dicts), and metadata.
    """
    # Clean up the text
    text = raw_text.strip()

    # Extract sections using headers
    sections_data = {}
    section_names = ["Introduction", "Challenge", "Resolution", "Moral"]

    for i, section_name in enumerate(section_names):
        # Find this section
        pattern = rf"##\s*{section_name}\s*\n(.*?)(?=##\s*(?:{'|'.join(section_names[i+1:])})|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            content = match.group(1).strip()
        else:
            # Fallback: try to split by paragraphs
            content = _extract_fallback_section(text, i, len(section_names))

        # Extract scene description
        scene_match = re.search(r'\[SCENE:\s*(.*?)\]', content, re.DOTALL)
        scene_description = scene_match.group(1).strip() if scene_match else _generate_default_scene(section_name, params)

        # Remove scene tags from main content
        clean_content = re.sub(r'\[SCENE:.*?\]', '', content, flags=re.DOTALL).strip()

        sections_data[section_name.lower()] = {
            "title": section_name,
            "content": clean_content,
            "scene_description": scene_description
        }

    # Generate a story title from the first character and theme
    characters = params.get("characters", [])
    char_name = characters[0].get("name", "Hero") if characters else "Young Hero"
    theme = params.get("theme", "adventure")
    title = _generate_title(char_name, theme, params.get("setting", ""))

    return {
        "title": title,
        "sections": [
            sections_data.get("introduction", {"title": "Introduction", "content": "", "scene_description": ""}),
            sections_data.get("challenge", {"title": "Challenge", "content": "", "scene_description": ""}),
            sections_data.get("resolution", {"title": "Resolution", "content": "", "scene_description": ""}),
            sections_data.get("moral", {"title": "Moral", "content": "", "scene_description": ""})
        ],
        "age_group": params.get("age_group", "6-8"),
        "theme": params.get("theme", ""),
        "setting": params.get("setting", ""),
        "moral": params.get("moral", "")
    }


def _extract_fallback_section(text: str, index: int, total: int) -> str:
    """Fallback: split text into equal parts if headers not found."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunk_size = max(1, len(paragraphs) // total)
    start = index * chunk_size
    end = start + chunk_size if index < total - 1 else len(paragraphs)
    return "\n\n".join(paragraphs[start:end])


def _generate_default_scene(section_name: str, params: dict) -> str:
    """Generate a default scene description if not found in LLM output."""
    setting = params.get("setting", "a magical land")
    chars = params.get("characters", [])
    char_name = chars[0].get("name", "our hero") if chars else "our hero"
    scenes = {
        "Introduction": f"{char_name} standing in {setting}, eyes wide with wonder",
        "Challenge": f"{char_name} facing a difficult moment in {setting}, determined and brave",
        "Resolution": f"{char_name} smiling triumphantly in {setting}, having overcome the challenge",
        "Moral": f"{char_name} and friends together in {setting}, basking in a warm golden light"
    }
    return scenes.get(section_name, f"A beautiful scene in {setting}")


def _generate_title(char_name: str, theme: str, setting: str) -> str:
    """Generate a story title."""
    theme_titles = {
        "friendship": f"{char_name} and the Gift of Friendship",
        "courage": f"{char_name}'s Brave Adventure",
        "honesty": f"{char_name} and the Truth",
        "kindness": f"{char_name}'s Kind Heart",
        "perseverance": f"{char_name} Never Gives Up",
        "sharing": f"{char_name} Learns to Share",
        "teamwork": f"{char_name} and the Power of Together",
        "respect": f"{char_name} and the Lesson of Respect",
        "creativity": f"{char_name}'s Magical Imagination",
        "curiosity": f"{char_name} and the Great Discovery"
    }
    return theme_titles.get(theme.lower(), f"{char_name}'s Magical Story")


def get_age_config(age_group: str) -> dict:
    return AGE_CONFIG.get(age_group, AGE_CONFIG["6-8"])
