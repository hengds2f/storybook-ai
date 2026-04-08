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
    
    STORY STRUCTURE — You MUST include these four sections with clear markers:
    
    [[Introduction]]
    [Dive deep into the world and characters. Set the scene with rich, immersive descriptions.]
    
    [[Challenge]]
    [Escalate the situation using the Plot Archetype: {s['archetype']}. Introduce the Plot Spark: {s['spark']} and the Surprise Turn: {s['twist']}.]
    
    [[Resolution]]
    [The shocking and unpredictable climax and resolution. Absolutely NO puzzle-solving ending.]
    
    [[Moral]]
    [A beautiful, non-standard reflection on the experience.]
    
    Important rules:
    - {s['genre']} and {s['spark']} must be central to the story.
    - Each [SCENE: description] must be cinematic and striking for an AI illustrator.
    - Do NOT include any meta-commentary.
    
    Begin the 1000-word story now:"""

    return prompt


def build_act_prompt(params: dict, act_number: int, act1_content: str = None, seeds: dict = None) -> str:
    """
    DEPRECATED: Use build_8act_prompts instead for segmented generation.
    """
    return ""


def build_8act_prompts(params: dict, act_number: int, previous_content: str = None, seeds: dict = None) -> str:
    """
    Generate highly granular prompts for the 8-Act Narrative Engine.
    Uses non-markdown markers (no #) and enforces strict NEW content rule.
    """
    age_group = params.get("age_group", "6-8")
    cfg = AGE_CONFIG.get(age_group, AGE_CONFIG["6-8"])
    
    characters = params.get("characters", [])
    characters_text = ", ".join([c.get("name", "Hero") for c in characters])
    setting = params.get("setting", "a magical world")
    theme = params.get("theme", "friendship")
    
    s = seeds
    
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
    
    title = act_titles[act_number - 1]
    
    prompt = f"""You are a master children's storyteller. We are writing a detailed, long-form story (1200+ words).
    
    CONTEXT:
    - Sub-Genre: {s['genre']}
    - Atmosphere: {s['atm']}
    - Characters: {characters_text}
    - Setting: {setting}
    
    TASK: Write ONLY the segment for '{title}'.
    
    CRITICAL RULES (MANDATORY):
    - Do NOT use the '#' symbol anywhere in your response.
    - Write exactly '[[{title}]]' as your first line.
    - Write NEW CONTENT ONLY. Do NOT repeat, summarize, or rephrase any previous acts.
    - Write at least 150 words of rich, descriptive prose for this specific act.
    - Focus exclusively on adding new dialogue, internal monologue, and environmental details.
    
    SPECIFIC INSTRUCTIONS FOR {title}:
    """
    
    if act_number == 1:
        prompt += f"Begin the story in {setting}. Deeply describe the environment and the first moment we see {characters_text}."
    elif act_number == 2:
        prompt += f"Deepen our understanding of {characters_text}. Describe their internal thoughts and sensory experience of {setting}."
    elif act_number == 3:
        prompt += f"Introduce the Plot Spark: {s['spark']}. Something changes in {setting}. How does {characters_text} react?"
    elif act_number == 4:
        prompt += f"The situation escalates. Describe the first trials facing {characters_text}. Focus on {s['atm']} atmosphere."
    elif act_number == 5:
        prompt += f"Introduce the Plot Archetype: {s['archetype']}. A huge complication arises. Include the Surprise Turn: {s['twist']}."
    elif act_number == 6:
        prompt += f"The final confrontation. The stakes are at their highest. Describe the action and emotion in slow-motion detail."
    elif act_number == 7:
        prompt += f"The climax resolves. How does the world of {setting} change? Focus on {theme} theme."
    elif act_number == 8:
        prompt += f"A peaceful closing scene. What lesson did {characters_text} learn? End with a final striking visual moment."
        
    if previous_content:
        # Pass the last segment for continuity
        prompt += f"\n\n--- PREVIOUS ACT (FOR CONTEXT ONLY - DO NOT REPEAT THIS IN YOUR RESPONSE) ---\n{previous_content[-1000:]}"
        
    prompt += f"\n\nBegin writing [[{title}]] now (Target: 150+ new words):"
    return prompt


def parse_story(raw_text: str, params: dict) -> dict:
    """
    Parse the segmented 8-Act engine output into the 4 UI-facing sections.
    """
    # Split by Acts using the new bracketed marker
    acts = re.split(r'\[\[ACT_\d:.*?\]\]', raw_text, flags=re.IGNORECASE)
    # Remove empty first element
    acts = [a.strip() for a in acts if a.strip()]
    
    # Re-group 8 acts into 4 sections for UI consistency:
    # 1. Introduction (Acts 1 & 2)
    # 2. Challenge (Acts 3, 4, & 5)
    # 3. Resolution (Acts 6 & 7)
    # 4. Moral (Act 8)
    
    sections_data = {
        "introduction": "\n\n".join(acts[:2]) if len(acts) >= 2 else (acts[0] if acts else ""),
        "challenge": "\n\n".join(acts[2:5]) if len(acts) >= 5 else ("\n\n".join(acts[2:]) if len(acts) > 2 else ""),
        "resolution": "\n\n".join(acts[5:7]) if len(acts) >= 7 else ("\n\n".join(acts[5:]) if len(acts) > 5 else ""),
        "moral": acts[7] if len(acts) > 7 else ""
    }

    processed_sections = []
    section_names = ["Introduction", "Challenge", "Resolution", "Moral"]
    
    for name in section_names:
        key = name.lower()
        content = sections_data.get(key, "").strip()
        
        # Extract or generate scene description
        scene_match = re.search(r'\[SCENE:\s*(.*?)\]', content, re.DOTALL)
        scene_description = scene_match.group(1).strip() if scene_match else _generate_default_scene(name, params)
        
        # Clean content
        clean_content = re.sub(r'\[SCENE:.*?\]', '', content, flags=re.DOTALL).strip()
        # Ensure no residual markers exist
        clean_content = re.sub(r'\[\[ACT_\d:.*?\]\]', '', clean_content, flags=re.IGNORECASE).strip()
        
        processed_sections.append({
            "title": name,
            "content": clean_content,
            "scene_description": scene_description
        })

    # Generate a story title
    characters = params.get("characters", [])
    char_name = characters[0].get("name", "Hero") if characters else "Young Hero"
    theme = params.get("theme", "adventure")
    title = _generate_title(char_name, theme, params.get("setting", ""))

    return {
        "title": title,
        "sections": processed_sections,
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
