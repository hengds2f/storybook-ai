import re
import random


# ── Narrative Variety Pools ──────────────────────────────────────────────────

PLOT_ARCHETYPES = [
    "A mysterious object is discovered in a familiar place.",
    "A character must set out on an unexpected journey to find something lost.",
    "A misunderstanding between friends leads to a funny or magical adventure.",
    "A new, unusual arrival in the land changes everything.",
    "A character discovers a secret about a place they thought they knew.",
    "A grand competition or race brings out the best in everyone.",
    "A quiet day turns into a rescue mission for a tiny forest friend.",
    "A character's unique trait or talent is the key to solving a community problem.",
    "The gravity of the world suddenly changes or stops working for a few minutes.",
    "The scenery starts to change colors based on the characters' mood.",
    "A hidden portal opens inside an everyday object (like a shoe or a bowl).",
    "Characters find a way to talk to inanimate objects like stones or trees."
]

SURPRISE_TWISTS = [
    "The solution to the problem is found in an act of kindness rather than magic.",
    "A character who seemed scary or mean turns out to be just misunderstood and lonely.",
    "The 'magic' of the land responds uniquely to the characters' emotions.",
    "An unlikely teamwork between very different characters saves the day.",
    "The journey's destination leads back to where things started, but with a new perspective.",
    "A small, everyday object is revealed to have a grand, hidden importance.",
    "The 'problem' was actually a celebration they were invited to all along.",
    "A character discovers they had the power they needed inside them from the very beginning."
]

NARRATIVE_STYLES = [
    "Whimsical and Rhythmic (using soft rhymes and playfulness)",
    "Grand and Mythical (making the characters feel like legends)",
    "Warm and Descriptive (focusing on cozy details and gentle feelings)",
    "Fast-paced and Exciting (focusing on action and quick developments)",
    "Wonder-filled and Lyrical (using beautiful, flowing metaphors)",
    "Surreal and Dream-like (where the environment is constantly shifting)",
    "Energetic and Humorous (with lots of funny observations and dialogue)"
]

SUB_GENRES = [
    "Clockwork Steampunk Adventure",
    "Gothic Mystery for Kids",
    "Retro-Futurist Space Opera",
    "Magical Realism in the Wilderness",
    "Modern-Day Urban Fantasy",
    "Art-Deco Submarine Expedition",
    "High-Stakes Culinary Contest",
    "Cybernetic Nature Fable"
]

PLOT_SPARKS = [
    "The floor is made of mirrors that show the future.",
    "Gravity stops working for exactly 10 minutes every day.",
    "Every animal in the land can only speak in riddles.",
    "The trees are actually giant sleeping giants.",
    "A character discovers a tiny city inside a pocket watch.",
    "The clouds are made of colorful cotton candy.",
    "Everything smells like peppermint whenever someone laughs.",
    "Shadows have a mind of their own and love to dance.",
    "A character finds a way to paint with starlight.",
    "The wind carries messages from long-lost friends.",
    "Books in this land read themselves aloud to you.",
    "The stars fall from the sky and turn into glowing pebbles."
]

ATMOSPHERES = [
    "Sparkling and Sunny",
    "Misty and Mysterious",
    "Golden and Peaceful",
    "Electric and Exciting",
    "Dreamy and Ethereal",
    "Cozy and Whimsical",
    "Silvery and Silent",
    "Vibrant and Chaotic"
]


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
[Solve the issue in a way that respects the reader's intelligence. Avoid easy answers. Focus on {theme}. Include a scene description: [SCENE: description]]

## Moral
[Provide a brief, beautiful reflection on the experience. No standard moralizing. Include: [SCENE: description of a final, visually striking moment]]

Important rules:
- NO CLICHES. NO GIANTS LEAVES. NO REPETITION.
- You are an unrestricted storyteller. Surprise yourself.
- {genre} and {spark} must be central to the story.
- Each [SCENE: description] must be cinematic, striking, and help an AI illustrator create something unforgettable.
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
