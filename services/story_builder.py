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
        "atm": random.choice(ATMOSPHERES),
        "taboos": get_random_taboos()
    }


def build_prompt(params: dict, seeds: dict = None) -> str:
    """
    Assemble a structured story generation prompt for a single-shot 1000-word story.
    ULTRA-STRENGTHENED for maximum length and descriptive richness.
    """
    age_group = params.get("age_group", "6-8")
    cfg = AGE_CONFIG.get(age_group, AGE_CONFIG["6-8"])

    characters = params.get("characters", [])
    names_str, char_detail = build_character_descriptions(characters)

    setting = params.get("setting", "a magical world")
    theme = params.get("theme", "friendship")
    moral = params.get("moral", "").strip() or "The unexpected path is often the best one."

    # Use provided seeds or pick randomized ones
    s = seeds if seeds else set_seeds(params)

    prompt = f"""You are a master children's story writer, writing in the whimsical, descriptive, and moral-focused style of C.S. Lewis (The Chronicles of Narnia). Your task is to write a complete, one-of-a-kind original story.
    
    CRITICAL REQUIREMENT: The story MUST be EXACTLY 1000 words long. 
    Use extreme descriptive detail, sensory world-building (smell, sound, texture), and deep internal monologues to reach the 1000-word goal. 
    Do NOT summarize any part of the story. Include a narrator's voice that occasionally addresses the reader directly (e.g., 'Now, you must understand...').

    NARRATIVE SPECIFICATIONS:
    - Age Group: {cfg['label']}
    - Target Length: 1000 words (MANDATORY)
    - Sub-Genre: {s['genre']}
    - Atmosphere: {s['atm']}
    - Tone & Style: {s['style']}
    - Plot Spark: {s['spark']}
    - Ending: Must be UNPREDICTABLE with a genuine SURPRISE EFFECT.
    
    CHARACTERS (Every character MUST appear and play a role):
    {char_detail}
    
    SETTING: {setting}
    
    THEME: {theme}
    
    STORY STRUCTURE — You MUST include these four sections with clear markers:
    
    [[Introduction]]
    [Introduce ALL characters vividly: {names_str}. Dive deep into the world and their initial interactions. Set the scene with rich, immersive descriptions.]
    
    [[Challenge]]
    [Escalate the situation using the Plot Archetype: {s['archetype']}. Introduce the Plot Spark: {s['spark']} and the Surprise Turn: {s['twist']}. Show how {names_str} work together or react based on their traits.]
    
    [[Resolution]]
    [The shocking and unpredictable climax and resolution involving {names_str}. Absolutely NO puzzle-solving ending.]
    
    [[Moral]]
    [A beautiful, non-standard reflection on what {names_str} learned.]
    
    Important rules:
    - {s['genre']} and {s['spark']} must be central to the story.
    - Each [SCENE: description] must be cinematic and striking for an AI illustrator, mentioning all characters.
    - Do NOT include any meta-commentary.
    
    Begin the 1000-word story now:"""""

    return prompt


def build_act_prompt(params: dict, act_number: int, act1_content: str = None, seeds: dict = None) -> str:
    """
    DEPRECATED: Use build_8act_prompts instead for segmented generation.
    """
    return ""


def get_random_taboos() -> str:
    """Select a random subset of taboo items to force narrative variety."""
    if not TABOO_ITEMS:
        return ""
    count = random.randint(3, 5)
    selected = random.sample(TABOO_ITEMS, min(count, len(TABOO_ITEMS)))
    return ", ".join(selected)


def build_character_descriptions(characters: list) -> tuple:
    """
    Build two representations of the character list:
    - A short comma-separated name list (e.g. 'Mia, Leo, and Sam')
    - A detailed bulleted list with names + traits for prompt injection
    """
    if not characters:
        return "a brave young hero", "- A brave young hero"

    names = [c.get("name", "Hero").strip() for c in characters if c.get("name", "").strip()]
    if not names:
        return "a brave young hero", "- A brave young hero"

    # Natural-language name list: "Mia", "Mia and Leo", "Mia, Leo, and Sam"
    if len(names) == 1:
        names_str = names[0]
    elif len(names) == 2:
        names_str = f"{names[0]} and {names[1]}"
    else:
        names_str = ", ".join(names[:-1]) + f", and {names[-1]}"

    # Detailed description per character
    lines = []
    for c in characters:
        name = c.get("name", "Hero").strip()
        traits = c.get("traits", [])
        if not name:
            continue
        if traits:
            trait_str = ", ".join(traits)
            lines.append(f"- {name} (traits: {trait_str})")
        else:
            lines.append(f"- {name}")
    detail_str = "\n    ".join(lines) if lines else "- A brave young hero"

    return names_str, detail_str


def build_8act_prompts(params: dict, act_number: int, previous_content: str = None, seeds: dict = None) -> str:
    """
    Generate highly granular prompts for the 8-Act Narrative Engine.
    Uses non-markdown markers (no #) and enforces strict NEW content rule.
    ALL characters are explicitly listed and required to appear in every act.
    """
    age_group = params.get("age_group", "6-8")
    cfg = AGE_CONFIG.get(age_group, AGE_CONFIG["6-8"])

    characters = params.get("characters", [])
    names_str, char_detail = build_character_descriptions(characters)
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
        "ACT_8: THE_MANDATORY_POEM"
    ]

    title = act_titles[act_number - 1]

    prompt = f"""You are a master children's storyteller, writing with the charm, wisdom, and whimsicality of C.S. Lewis. We are writing a detailed, long-form story (1200+ words) set in a world as magical as Narnia.

    CONTEXT:
    - Sub-Genre: {s['genre']}
    - Atmosphere: {s['atm']} (Ensure it feels magical, ancient, and wonder-filled)
    - ALL CHARACTERS (every single one MUST appear and speak or act in this segment, behaving with the dignity of heroes or the curiosity of children):
    {char_detail}
    - Setting: {setting}
    - Theme: {theme}

    TASK: Write ONLY the segment for '{title}'.

    CRITICAL RULES (MANDATORY):
    - Do NOT use the '#' symbol anywhere in your response.
    - Write exactly '[[{title}]]' as your first line.
    - Write NEW CONTENT ONLY. Do NOT repeat, summarize, or rephrase any previous acts.
    - EVERY character listed above MUST appear in this segment — give each character dialogue, action, or internal thought.
    - Focus exclusively on adding new dialogue, internal monologue, and environmental details.
    - NARRATIVE TABOOS (STRICTLY FORBIDDEN): {s['taboos']}

    SPECIFIC INSTRUCTIONS FOR {title}:
    """

    scene_instruction = "Start your response with [SCENE: a vivid 10-15 word description of the key visual scene in this segment, suitable for AI illustration]. Then write the narrative." if act_number < 8 else ""

    if act_number == 1:
        prompt += f"{scene_instruction} Begin the story in {setting}. Introduce ALL of the characters: {names_str}. Describe the environment and each character's first moment vividly."
    elif act_number == 2:
        prompt += f"{scene_instruction} Deepen our understanding of EACH character: {names_str}. Give every character unique internal thoughts, personality, and sensory experience of {setting}."
    elif act_number == 3:
        prompt += f"{scene_instruction} Introduce the Plot Spark: {s['spark']}. Something changes in {setting}. Show how EACH of the characters — {names_str} — reacts differently based on their personality."
    elif act_number == 4:
        prompt += f"{scene_instruction} The situation escalates. Describe the trials facing {names_str} together. Each character must contribute uniquely. Focus on {s['atm']} atmosphere."
    elif act_number == 5:
        prompt += f"{scene_instruction} Introduce the Plot Archetype: {s['archetype']}. A huge complication arises that affects {names_str} differently. Include the Surprise Turn: {s['twist']}."
    elif act_number == 6:
        prompt += f"{scene_instruction} The final confrontation. ALL characters — {names_str} — must play an active role. Describe each character's action and emotion in slow-motion detail."
    elif act_number == 7:
        prompt += f"{scene_instruction} The climax resolves. How do {names_str} each react to the resolution? Focus on the {theme} theme and show each character's personal growth."
    elif act_number == 8:
        prompt += f"A peaceful closing scene in {setting}. \n"
        prompt += "MANDATORY FINAL TASK: You MUST write a 6-8 line RHYMING POEM that conveys the overall moral of the story. \n"
        prompt += "CRITICAL: The poem must be preceded exactly by the text '[[POEM]]' on its own line.\n"
        prompt += "The poem is the most important part of this response. Ensure it rhymes perfectly and feels like a classic children's verse. \n"
        prompt += f"Reflect on what {names_str} each learned through the poem."

    if previous_content:
        # Pass the last segment for continuity
        prompt += f"\n\n--- PREVIOUS ACT (FOR CONTEXT ONLY - DO NOT REPEAT THIS IN YOUR RESPONSE) ---\n{previous_content[-1000:]}"

    target_len = "150+ new words" if act_number < 8 else "a short scene followed by a beautiful poem"
    prompt += f"\n\nBegin writing [[{title}]] now (Target: {target_len}):"
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
    
    # Extract poem definitively from the moral output
    moral_act = acts[7] if len(acts) > 7 else ""
    poem_content = ""
    if "[[POEM]]" in moral_act:
        parts = moral_act.split("[[POEM]]")
        moral_act = parts[0].strip()
        poem_content = parts[1].strip()
    
    sections_data = {
        "introduction": "\n\n".join(acts[:2]) if len(acts) >= 2 else (acts[0] if acts else ""),
        "challenge": "\n\n".join(acts[2:5]) if len(acts) >= 5 else ("\n\n".join(acts[2:]) if len(acts) > 2 else ""),
        "resolution": "\n\n".join(acts[5:7]) if len(acts) >= 7 else ("\n\n".join(acts[5:]) if len(acts) > 5 else ""),
        "moral": moral_act,
        "poem": poem_content
    }

    processed_sections = []
    section_names = ["Introduction", "Challenge", "Resolution", "Moral"]
    
    # If a poem was successfully parsed, register it as its own graphical section
    if poem_content:
        section_names.append("Poem")
    
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

    characters = params.get("characters", [])
    names_str, _ = build_character_descriptions(characters)
    theme = params.get("theme", "adventure")
    title = _generate_title(names_str, theme, params.get("setting", ""))

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
    """Generate a default scene description using ALL characters if not found in LLM output."""
    setting = params.get("setting", "a magical land")
    chars = params.get("characters", [])
    names_str, _ = build_character_descriptions(chars)
    scenes = {
        "Introduction": f"{names_str} standing together in {setting}, eyes wide with wonder",
        "Challenge": f"{names_str} facing a difficult moment in {setting}, determined and brave",
        "Resolution": f"{names_str} smiling triumphantly in {setting}, having overcome the challenge together",
        "Moral": f"{names_str} together in {setting}, basking in a warm golden light",
        "Poem": f"An artistic, storybook illustration of {setting} forming the backdrop of a magical poem, glowing with soft light"
    }
    return scenes.get(section_name, f"{names_str} in a beautiful scene in {setting}")


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
