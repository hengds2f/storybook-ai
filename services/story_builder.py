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
        "length": "very short (about 300–400 words)",
        "complexity": "simple and magical, with clear cause-and-effect",
        "max_tokens": 600
    },
    "6-8": {
        "label": "Ages 6–8",
        "vocabulary": "simple but varied vocabulary, moderate sentence length",
        "length": "medium length (about 500–700 words)",
        "complexity": "engaging with a clear problem to solve",
        "max_tokens": 900
    },
    "9-12": {
        "label": "Ages 9–12",
        "vocabulary": "richer vocabulary with descriptive language",
        "length": "longer (about 800–1000 words)",
        "complexity": "more nuanced with character development and descriptive scenes",
        "max_tokens": 1300
    }
}


def build_prompt(params: dict) -> str:
    """
    Assemble a structured story generation prompt from user parameters.
    ULTRA-STRENGTHENED for maximum variety and uniqueness.
    """
    age_group = params.get("age_group", "6-8")
    cfg = AGE_CONFIG.get(age_group, AGE_CONFIG["6-8"])

    characters = params.get("characters", [])
    char_list = []
    # Use numbered list to ensure LLM tracks every character
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

    # Select randomized narrative seeds
    archetype = random.choice(PLOT_ARCHETYPES)
    twist = random.choice(SURPRISE_TWISTS)
    style = random.choice(NARRATIVE_STYLES)
    genre = random.choice(SUB_GENRES)
    spark = random.choice(PLOT_SPARKS)
    atm = random.choice(ATMOSPHERES)

    prompt = f"""You are a master children's story writer known for UNRESTRICTED, SHOCKINGLY CREATIVE, and AVANT-GARDE narratives. Write a complete, one-of-a-kind original story.

NARRATIVE SPECIFICATIONS:
- Age Group: {cfg['label']}
- Sub-Genre: {genre}
- Atmosphere: {atm}
- Tone & Style: {style}
- Plot Spark (MANDATORY): {spark}
- Creative Directive: BREAK ALL CLICHES. Start in the middle of the action. Avoid "Once upon a time."

CHARACTERS (Exactly {char_count} characters):
{characters_text}

SETTING: {setting}

THEME: {theme}

MORAL LESSON (OPTIONAL): {moral}

STORY STRUCTURE — You MUST include ALL four sections with EXACTLY these headers:

## Introduction
[Write a high-stakes opening that hooks the reader immediately. Dive straight into a unique situation. Include a scene description: [SCENE: description]]

## Challenge
[Escalate the situation in a completely unexpected way. Use the plot archetype: {archetype}. Include the Plot Spark: {spark}. Include the surprise turn: {twist}. Include a scene description: [SCENE: description]]

## Resolution
[Solve the issue in a way that respects the reader's intelligence. Focus on {theme}. Include a scene description: [SCENE: description]]

## Moral
[Provide a brief, beautiful reflection on the experience. No standard moralizing. Include: [SCENE: description of a final, visually striking moment]]

STRICT CONSTRAINTS (MANDATORY):
- TABOO LIST: NEVER use these overused items: {', '.join(TABOO_ITEMS)}.
- NO REPEATS: Never repeat a plot, a theme, or a combination of items from any previous story.
- NO CLICHES: No giant leaves, no lost baby animals, no repetition of any known story tropes.

Important rules:
- You are an unrestricted storyteller. Surprise yourself. Every story must be a 'First of its kind' experiment.
- {genre} and {spark} must be central to the story.
- Each [SCENE: description] must be cinematic and striking for an AI illustrator.
- Do NOT include any meta-commentary.

Begin the story now:"""

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
