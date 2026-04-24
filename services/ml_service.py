"""
ML Service — StoryBook Personalization Module
==============================================
Provides three core inference functions:

  1. estimate_reading_level(profile_id, age_group) → float (1–10)
  2. predict_engagement(profile_id) → dict {score, label}
  3. recommend_story_params(profile_id, age_group) → dict
  4. advise_question_timing(act_number, avg_time_per_word_ms) → dict
  5. generate_question(act_number, act_text, age_group, question_type) → dict

Architecture:
  - MVP tier: rule-based heuristics only (no sklearn required)
  - V2 tier: sklearn models loaded from data/models/ if present; else falls back to rules
  - V3 tier: LLM question generation via Gemini Flash (same key used for story gen)

No cross-profile data sharing. All inference is per-profile.
"""

import json
import math
import os
import pickle
import random
import uuid
from datetime import datetime, timezone

from services.event_tracker import (
    get_ml_state,
    get_recent_story_params,
    recompute_profile_features,
    save_question,
)

# ── Constants ─────────────────────────────────────────────────────────────────

MODELS_DIR = os.path.join("data", "models")

# Base reading level by age group (scale 1–10)
AGE_GROUP_BASE_LEVEL = {"3-5": 2.0, "6-8": 5.0, "9-12": 8.0}

# Maximum reading level allowed per age group (safety cap — prevents over-escalation)
AGE_GROUP_MAX_LEVEL = {"3-5": 4.0, "6-8": 7.5, "9-12": 10.0}

# Complexity hint thresholds (maps reading_level_score → hint string)
COMPLEXITY_THRESHOLDS = [
    (3.5, "simple"),
    (6.5, "moderate"),
    (10.0, "rich"),
]

# Vocabulary hint thresholds
VOCAB_THRESHOLDS = [
    (3.0, "introductory"),
    (6.0, "grade_level"),
    (10.0, "stretch"),
]

# Default themes per age group for cold-start
AGE_DEFAULT_THEMES = {
    "3-5": ["friendship", "animals", "family"],
    "6-8": ["adventure", "magic", "friendship"],
    "9-12": ["courage", "discovery", "mystery"],
}

# Default settings per age group for cold-start
AGE_DEFAULT_SETTINGS = {
    "3-5": ["a cozy village", "a sunny meadow", "a magical forest"],
    "6-8": ["an enchanted forest", "a pirate ship", "a magical academy"],
    "9-12": ["a distant kingdom", "a hidden city", "an ancient temple"],
}

# Acts that trigger interactive questions
QUESTION_ACT_TRIGGERS = {
    3: "comprehension",   # After the inciting incident
    5: "prediction",      # After the complication
    8: "reflection",      # After the moral poem
}

# Rule-based question templates per type (no LLM needed for MVP)
QUESTION_TEMPLATES = {
    "comprehension": [
        "What happened in this part of the story?",
        "Who did {character} meet in this part?",
        "Why did {character} feel that way?",
    ],
    "prediction": [
        "What do you think will happen next?",
        "How do you think {character} will solve the problem?",
        "What would you do if you were {character}?",
    ],
    "reflection": [
        "What is the most important lesson from this story?",
        "How did {character} change by the end?",
        "Which part of the story was your favourite, and why?",
    ],
    "vocabulary": [
        "What do you think the word '{word}' means?",
        "Can you use '{word}' in a sentence?",
    ],
}

# Minimum events before switching from cold-start to preference-based recommendations
COLD_START_THRESHOLD = 3  # completed stories

# How many vocabulary questions to generate per story section
VOCAB_QUESTIONS_PER_SECTION = 5

# Rule-based fallback vocabulary by age group
# Each entry: (word, definition, [wrong_def_1, wrong_def_2, wrong_def_3])
_FALLBACK_VOCAB: dict[str, list] = {
    "3-5": [
        ("tiny",      "very small",                ["very big", "very loud", "very fast"]),
        ("brave",     "not afraid of hard things", ["very hungry", "very sleepy", "very silly"]),
        ("giggle",    "a small laugh",             ["a type of bird", "a kind of jump", "a big sneeze"]),
        ("glimmer",   "a soft, shining light",     ["a loud noise", "a dark shadow", "a cold wind"]),
        ("wander",    "to walk without a plan",    ["to swim quickly", "to eat slowly", "to sleep deeply"]),
        ("cozy",      "warm and comfortable",      ["wet and muddy", "tall and heavy", "sharp and pointy"]),
        ("sturdy",    "strong and solid",          ["soft and fluffy", "quick and light", "round and smooth"]),
        ("curious",   "wanting to know things",    ["feeling very tired", "feeling angry", "feeling hungry"]),
    ],
    "6-8": [
        ("gleaming",   "shining brightly",                       ["making loud sounds", "moving very quickly", "smelling sweet"]),
        ("ancient",    "very very old",                          ["brand new", "very tiny", "quite heavy"]),
        ("trembled",   "shook with fear or cold",                ["laughed loudly", "slept deeply", "ran swiftly"]),
        ("enchanted",  "put under a magic spell",                ["very cold", "made of wood", "very hungry"]),
        ("determined", "having a firm decision to do something", ["feeling very lost", "easily frightened", "quite sleepy"]),
        ("peculiar",   "strange or unusual",                     ["very ordinary", "quite beautiful", "extremely fast"]),
        ("whimpered",  "made a soft crying sound",               ["shouted loudly", "jumped high", "ate quickly"]),
        ("soared",     "flew high up in the air",                ["dug deep underground", "swam far away", "hid quietly"]),
        ("mischievous","playfully causing trouble",              ["very serious", "very sleepy", "very hungry"]),
        ("tranquil",   "calm and quiet",                         ["loud and busy", "cold and icy", "dark and scary"]),
    ],
    "9-12": [
        ("luminous",   "giving off a bright glow",               ["completely dark", "extremely heavy", "very noisy"]),
        ("tenacious",  "refusing to give up",                    ["easily discouraged", "very generous", "extremely forgetful"]),
        ("foreboding", "a feeling that something bad will happen",["a feeling of great joy", "a type of weather", "a kind of food"]),
        ("cryptic",    "mysterious and hard to understand",       ["very clear and simple", "extremely colourful", "quite warm"]),
        ("ethereal",   "delicate and heavenly",                   ["rough and heavy", "loud and sharp", "cold and bitter"]),
        ("labyrinth",  "a complicated maze",                      ["a straight road", "a calm lake", "a tall tower"]),
        ("resilient",  "able to recover quickly from difficulty", ["easily broken", "very heavy", "quite boring"]),
        ("ominous",    "suggesting something bad will happen",    ["cheerful and bright", "soft and gentle", "warm and cosy"]),
        ("elusive",    "hard to find or catch",                   ["very easy to see", "extremely heavy", "quite ordinary"]),
        ("forsaken",   "abandoned and alone",                     ["surrounded by friends", "full of treasure", "very busy"]),
    ],
}


# ── Public API ────────────────────────────────────────────────────────────────

def estimate_reading_level(profile_id: str, age_group: str) -> dict:
    """
    Estimate the child's reading level on a 1–10 scale.

    Returns:
        {
          "score": float,
          "label": str,   # e.g. "Grade 2–3"
          "tier": str,    # "rule_based" | "sklearn"
        }
    """
    state = _get_or_init_state(profile_id, age_group)

    # Try sklearn model first (V2+)
    model, scaler = _load_model("reading_level")
    if model is not None and state["total_stories_completed"] >= 5:
        score = _sklearn_reading_level(model, scaler, state, age_group)
        tier = "sklearn"
    else:
        score = _rule_based_reading_level(state, age_group)
        tier = "rule_based"

    # Safety cap: never exceed the maximum for this age group
    max_level = AGE_GROUP_MAX_LEVEL.get(age_group, 10.0)
    score = min(score, max_level)
    score = round(max(1.0, score), 2)

    return {
        "score": score,
        "label": _level_to_label(score),
        "tier": tier,
    }


def estimate_vocabulary_score(profile_id: str, age_group: str) -> dict:
    """
    Estimate the child's current vocabulary level on a 1–10 scale.

    Primary signal: the vocabulary_hint levels assigned to the child's recent stories
    (introductory → 2.5, grade_level → 5.5, stretch → 8.5), weighted toward recency.
    Supporting signals: question accuracy, completion rate, reading speed.

    Returns:
        {
          "score": float,   # 1–10
          "label": str,     # "Simple" | "Grade Level" | "Advanced"
          "hint":  str,     # "introductory" | "grade_level" | "stretch"
        }
    """
    state = get_ml_state(profile_id)

    # Use stored vocabulary_score from last recompute if available
    if state is not None:
        stored = state.get("vocabulary_score") or 0.0
        if stored > 0:
            max_level = AGE_GROUP_MAX_LEVEL.get(age_group, 10.0)
            score = round(min(stored, max_level), 2)
            return {
                "score": score,
                "label": _vocab_score_label(score),
                "hint": _score_to_vocab(score),
            }

    # Cold-start / no data: return age-group default
    base = {"3-5": 2.5, "6-8": 5.0, "9-12": 8.0}.get(age_group, 5.0)
    return {
        "score": base,
        "label": _vocab_score_label(base),
        "hint": _score_to_vocab(base),
    }


def predict_engagement(profile_id: str, age_group: str = "6-8") -> dict:
    """
    Predict the child's current engagement level.

    Returns:
        {
          "score": float (0–1),
          "label": str,  # "high" | "medium" | "low" | "at_risk"
          "tier": str,
        }
    """
    state = _get_or_init_state(profile_id, age_group)

    model, scaler = _load_model("engagement")
    if model is not None and state["total_events"] >= 20:
        score = _sklearn_engagement(model, scaler, state)
        tier = "sklearn"
    else:
        score = _rule_based_engagement(state)
        tier = "rule_based"

    score = round(max(0.0, min(1.0, score)), 4)
    label = _engagement_label(score)

    return {"score": score, "label": label, "tier": tier}


def recommend_story_params(profile_id: str, age_group: str) -> dict:
    """
    Recommend story generation parameters for the next story.

    Handles cold-start by returning age-group defaults when insufficient data.

    Returns:
        {
          "age_group": str,
          "theme": str,
          "setting": str,
          "complexity_hint": str,
          "vocabulary_hint": str,
          "confidence": float,
          "cold_start": bool,
          "model_tier": str,
        }
    """
    state = _get_or_init_state(profile_id, age_group)
    reading = estimate_reading_level(profile_id, age_group)
    reading_score = reading["score"]

    cold_start = state["total_stories_completed"] < COLD_START_THRESHOLD

    if cold_start:
        return _cold_start_recommendation(age_group, reading_score)

    # Preference-based recommendation
    preferred_themes = state.get("preferred_themes", [])
    preferred_settings = state.get("preferred_settings", [])

    # Enforce diversity: avoid last 3 themes/settings
    recent = get_recent_story_params(profile_id, n=3)
    recent_themes = [r.get("theme", "") for r in recent]
    recent_settings = [r.get("setting", "") for r in recent]

    theme = _pick_diverse(preferred_themes, recent_themes, AGE_DEFAULT_THEMES[age_group])
    setting = _pick_diverse(preferred_settings, recent_settings, AGE_DEFAULT_SETTINGS[age_group])
    complexity_hint = _score_to_complexity(reading_score)
    vocabulary_hint = _score_to_vocab(reading_score)

    # Adjust age_group for story generation if reading level diverges significantly
    recommended_age_group = _level_to_age_group(reading_score, age_group)

    confidence = _recommendation_confidence(state)

    return {
        "age_group": recommended_age_group,
        "theme": theme,
        "setting": setting,
        "complexity_hint": complexity_hint,
        "vocabulary_hint": vocabulary_hint,
        "confidence": round(confidence, 3),
        "cold_start": False,
        "model_tier": "rule_based",
    }


def advise_question_timing(
    act_number: int,
    avg_time_per_word_ms: float = 0.0,
) -> dict:
    """
    Decide whether to show a question after a given act, and what type.

    Returns:
        {
          "show_question": bool,
          "question_type": str | None,
          "delay_seconds": int,   # how long to wait after act ends before showing question
          "reason": str,
        }
    """
    if act_number not in QUESTION_ACT_TRIGGERS:
        return {"show_question": False, "question_type": None, "delay_seconds": 0, "reason": "not a trigger act"}

    question_type = QUESTION_ACT_TRIGGERS[act_number]

    # V2: if child reads very fast, give them a moment to process
    delay = 2
    if avg_time_per_word_ms > 0:
        words_per_minute = 60_000 / avg_time_per_word_ms
        if words_per_minute > 200:
            delay = 3  # fast reader — small pause
        elif words_per_minute < 80:
            delay = 5  # slow reader — longer pause before question

    return {
        "show_question": True,
        "question_type": question_type,
        "delay_seconds": delay,
        "reason": f"Act {act_number} is a designated {question_type} checkpoint",
    }


def generate_question(
    profile_id: str,
    story_id: str,
    act_number: int,
    act_text: str,
    age_group: str,
    question_type: str = "comprehension",
    use_llm: bool = True,
) -> dict:
    """
    Generate an interactive question for a story act.

    Tries LLM generation (V3) first when use_llm=True, falls back to rule-based templates.

    Returns the saved question dict including question_id.
    """
    character = _extract_first_character(act_text)

    if use_llm:
        llm_question = _llm_generate_question(act_text, age_group, question_type, character)
        if llm_question:
            llm_question.update({
                "question_id": str(uuid.uuid4()),
                "profile_id": profile_id,
                "story_id": story_id,
                "act_number": act_number,
                "generated_by": "llm",
            })
            save_question(llm_question)
            return llm_question

    # Rule-based fallback
    question = _rule_based_question(
        profile_id, story_id, act_number, question_type, character
    )
    save_question(question)
    return question


def generate_vocab_questions(
    profile_id: str,
    story_id: str,
    act_number: int,
    act_text: str,
    age_group: str,
    n: int = VOCAB_QUESTIONS_PER_SECTION,
    used_words: set | None = None,
    pre_selected_words: list[str] | None = None,
) -> list[dict]:
    """
    Generate vocabulary MCQ questions for one story section.

    Preferred path: pass ``pre_selected_words`` (a list of words already
    confirmed to appear verbatim in act_text, allocated by
    ``allocate_story_vocab_words``).  The LLM is then asked only to write
    MCQ definitions for those specific words, which is far more reliable than
    asking it to pick words itself.

    Legacy path (no pre_selected_words): ask LLM to find words then write MCQs.
    Kept for backward-compatibility / standalone callers.

    ``used_words`` is updated in-place so callers can track cross-chapter usage.
    """
    if used_words is None:
        used_words = set()

    if pre_selected_words:
        # ── Primary path: words pre-verified to be in the chapter text ──────
        llm_questions = _llm_questions_for_words(pre_selected_words, act_text, age_group)
        if llm_questions:
            saved = []
            for qdata in llm_questions:
                qdata.update({
                    "question_id": str(uuid.uuid4()),
                    "profile_id": profile_id,
                    "story_id": story_id,
                    "act_number": act_number,
                    "question_type": "vocabulary",
                    "generated_by": "llm",
                })
                save_question(qdata)
                saved.append(qdata)
                used_words.add(qdata.get("word", "").lower())
            return saved
        # LLM unavailable or failed — build simple questions from the given words
        return _simple_questions_for_words(
            pre_selected_words, profile_id, story_id, act_number, act_text, used_words
        )

    # ── Legacy path: LLM picks words and writes MCQs in one pass ────────────
    llm_questions = _llm_generate_vocab_questions(act_text, age_group, n, used_words)
    if llm_questions:
        saved = []
        for qdata in llm_questions[:n]:
            qdata.update({
                "question_id": str(uuid.uuid4()),
                "profile_id": profile_id,
                "story_id": story_id,
                "act_number": act_number,
                "question_type": "vocabulary",
                "generated_by": "llm",
            })
            save_question(qdata)
            saved.append(qdata)
            used_words.add(qdata.get("word", "").lower())
        return saved

    return _rule_based_vocab_questions(profile_id, story_id, act_number, act_text, age_group, n, used_words)


# Extended stop-word set used by allocate_story_vocab_words for word extraction.
# Covers function words, pronouns, basic verbs/adjectives unlikely to be teaching words.
_STOP_WORDS: frozenset[str] = frozenset({
    "about","above","after","again","against","ahead","along","already","also",
    "always","among","another","around","asked","away","became","because",
    "before","began","being","below","between","both","bring","brought",
    "called","came","cannot","child","children","close","could","doing",
    "done","down","during","each","ever","every","everyone","everything",
    "except","eyes","face","father","finally","first","found","friend",
    "friends","from","front","gave","going","gone","good","great","hands",
    "happy","having","heard","heart","hello","help","here","himself",
    "home","house","however","inside","into","itself","just","keep",
    "kept","knew","know","large","later","leave","left","light","like",
    "little","long","looked","made","make","many","maybe","might","more",
    "most","mother","much","must","myself","named","near","never","night",
    "nothing","often","once","only","other","others","ourselves","outside",
    "over","place","point","quite","reach","ready","really","replied",
    "right","round","said","same","second","seemed","shall","should",
    "since","small","smile","smiled","something","sometimes","soon",
    "spoke","start","still","story","taken","takes","their","there",
    "these","think","those","thought","three","through","times","today",
    "together","told","toward","tried","truly","turned","under","until",
    "upon","using","voice","walks","wants","watch","watched","where",
    "while","whose","will","within","without","words","world","would",
    "years","young","yours","yourself","began","close","whole","every",
    "asked","above","ahead","yours","shall","seven","eight","three",
    "found","makes","comes","taken","given","shown","carry","learn",
    "stand","stood","whole","bring","going","truly","reach","begin",
    "looks","small","early","heard","happy","great","yours","could",
    # Common everyday nouns / verbs a child already knows
    "animals","beautiful","behind","birds","black","blue","brown","climbed",
    "clouds","colors","colour","colors","colourful","colorful","dancing",
    "decided","flowers","forest","green","ground","jumped","laughed",
    "leaves","loved","loved","magic","mountains","moved","orange","picked",
    "played","pretty","purple","queen","quickly","river","rocks","running",
    "schools","smiled","sparkling","stones","sunlit","sunshine","swiftly",
    "talked","trees","walked","water","white","yellow","chased","clapped",
    "cried","danced","field","flowed","flying","glowing","grass","kingdom",
    "lived","loved","ocean","paths","people","plants","prince","raining",
    "riding","river","sailed","seeing","shined","shining","singing","sitting",
    "sleeping","smelled","snowed","stood","swimming","things","towns",
    "twinkled","valley","village","waving","winds","wishing","wondering",
    "wooden","working","wanted",
    # More basic nouns/verbs obvious to children
    "picture","pictures","window","garden","castle","dragon","button",
    "basket","bottle","bridge","candle","carpet","circle","corner",
    "cotton","desert","dinner","dollar","engine","finger","golden",
    "hammer","island","jacket","jungle","kitten","ladder","locket",
    "marble","market","mirror","monkey","mother","napkin","needle",
    "orange","parrot","pencil","pickle","pillow","pirate","pocket",
    "rabbit","ribbon","rocket","saddle","sailor","shadow","silver",
    "sister","spirit","spring","street","summer","sunset","supper",
    "tablet","temple","thread","throne","ticket","timber","tinker",
    "tongue","turtle","umbrella","velvet","viking","violet","visits",
    "wallet","winter","wizard","wonder","wander","wicked","whisper",
    # Common adjectives / adverbs children already know
    "perfect","always","anyone","better","bigger","bright","broken",
    "certain","change","clean","clever","closer","colder","coming",
    "common","different","enjoy","enter","faster","follow","funny",
    "gentle","getting","giving","harder","higher","honest","important",
    "larger","louder","lower","lucky","matter","middle","minute",
    "moment","morning","newer","older","patient","quiet","shorter",
    "simple","slower","softer","stronger","taller","tired","trying",
    "upper","useful","usual","warmer","weaker","wetter","wider","writing",
})

# ── Built-in vocabulary definitions ─────────────────────────────────────────
# Real definitions with 3 plausible-but-wrong alternatives.
# Used by _simple_questions_for_words BEFORE any LLM call so correct answers
# are always genuinely correct, regardless of LLM availability.
# Format: word -> (correct_definition, [wrong1, wrong2, wrong3])
_VOCAB_DEFINITIONS: dict[str, tuple[str, list[str]]] = {
    # ── Adjectives ───────────────────────────────────────────────────────────
    "ancient":      ("very old, from a long time ago",                   ["brand new and shiny", "very small and tiny", "extremely loud"]),
    "brave":        ("willing to face danger without fear",              ["very hungry", "easily scared", "feeling sleepy"]),
    "brilliant":    ("very clever, or giving off a very bright light",   ["quite dull and dim", "very noisy", "very heavy"]),
    "calm":         ("quiet and peaceful, not worried or excited",       ["very loud and busy", "cold and shivery", "quick and impatient"]),
    "cheerful":     ("feeling or showing happiness",                     ["sad and gloomy", "tired and bored", "angry and upset"]),
    "colossal":     ("enormous in size",                                 ["very tiny and delicate", "quite dull", "soft and gentle"]),
    "courageous":   ("very brave, able to face danger or difficulty",   ["easily frightened", "very lazy", "extremely noisy"]),
    "cryptic":      ("mysterious and hard to understand",               ["very clear and simple", "extremely colourful", "warm and pleasant"]),
    "curious":      ("eager to learn or find out about things",         ["feeling very tired", "feeling full after eating", "very bored"]),
    "dazzling":     ("extremely bright or impressive",                  ["very dark and gloomy", "quite ordinary", "very slow"]),
    "determined":   ("having a firm decision to succeed at something",  ["easily giving up", "very confused", "feeling sleepy"]),
    "enchanted":    ("placed under a magic spell",                      ["very cold and icy", "made of solid stone", "very hungry"]),
    "elusive":      ("difficult to find, catch, or understand",         ["very easy to see", "extremely heavy", "quite ordinary"]),
    "ethereal":     ("extremely delicate and light, almost magical",    ["rough and very heavy", "loud and sharp", "cold and bitter"]),
    "fearless":     ("having no fear at all, very brave",               ["always frightened", "very slow", "quite small"]),
    "fierce":       ("very strong, powerful, or aggressive",            ["gentle and calm", "slow and quiet", "dull and boring"]),
    "fragile":      ("easily broken or damaged",                        ["very strong and tough", "extremely loud", "very heavy"]),
    "gleaming":     ("shining brightly and cleanly",                    ["making loud sounds", "moving very quickly", "smelling unpleasant"]),
    "glimmering":   ("giving off a soft, faint, flickering light",      ["making a rumbling noise", "sinking very deeply", "tasting very sweet"]),
    "glorious":     ("very beautiful, magnificent, or worthy of praise", ["very dull and boring", "quite ordinary", "very ugly"]),
    "graceful":     ("moving smoothly and elegantly",                   ["very clumsy and awkward", "extremely loud", "quite heavy"]),
    "gloomy":       ("dark, dull, or feeling sad",                      ["very bright and cheerful", "soft and gentle", "warm and cosy"]),
    "joyful":       ("feeling or causing great happiness",              ["feeling sad and lonely", "very tired", "quite angry"]),
    "luminous":     ("giving off a bright glow of light",               ["completely dark", "extremely heavy", "very noisy"]),
    "majestic":     ("having impressive beauty and dignity",            ["very small and plain", "quite ordinary", "very rough"]),
    "magnificent":  ("extremely beautiful or impressively large",       ["very plain and dull", "quite small", "very rough"]),
    "mischievous":  ("playfully causing trouble or mischief",           ["very serious and solemn", "very sleepy", "very hungry"]),
    "mysterious":   ("strange and not easily understood or explained",  ["very ordinary", "quite boring", "very clear"]),
    "noble":        ("having high moral qualities, or of high rank",    ["dishonest and selfish", "very small", "quite ordinary"]),
    "ominous":      ("suggesting that something bad is about to happen", ["cheerful and bright", "soft and gentle", "warm and cosy"]),
    "peculiar":     ("strange or unusual in a noticeable way",          ["very ordinary", "quite beautiful", "extremely fast"]),
    "radiant":      ("sending out bright light or warmth and happiness", ["dark and cold", "dull and grey", "very noisy"]),
    "resilient":    ("able to recover quickly from difficulties",       ["easily broken or damaged", "very heavy", "quite boring"]),
    "serene":       ("calm, peaceful, and untroubled",                  ["very loud and noisy", "cold and rough", "dark and scary"]),
    "slender":      ("thin and graceful in shape",                      ["very wide and round", "extremely loud", "quite heavy"]),
    "splendid":     ("very impressive, excellent, or beautiful",        ["quite dull and boring", "very small", "quite rough"]),
    "sturdy":       ("strongly and solidly built",                      ["soft and easily broken", "very light", "quite thin"]),
    "swift":        ("moving or happening very quickly",                ["very slow", "quite heavy", "extremely loud"]),
    "tenacious":    ("refusing to give up, holding firmly on",         ["easily discouraged", "very generous", "extremely forgetful"]),
    "tranquil":     ("free from disturbance, calm and quiet",           ["loud and very busy", "cold and icy", "dark and scary"]),
    "trembling":    ("shaking slightly because of fear, cold, or excitement", ["laughing loudly", "jumping high", "sleeping deeply"]),
    "vibrant":      ("full of life and energy, bright and vivid",       ["dull and lifeless", "very slow", "quite heavy"]),
    "wandering":    ("walking or travelling without a fixed destination", ["sitting very still", "sleeping deeply", "eating quickly"]),
    "wondrous":     ("inspiring feelings of wonder and amazement",      ["very boring", "quite ordinary", "very dull"]),
    "forsaken":     ("abandoned and left completely alone",             ["surrounded by many friends", "full of treasure", "very busy"]),
    "foreboding":   ("a strong feeling that something bad is about to happen", ["a feeling of great happiness", "a kind of food", "a type of weather"]),
    # ── Nouns ────────────────────────────────────────────────────────────────
    "adventure":    ("an exciting, daring, or unusual experience",      ["a boring everyday routine", "a type of food", "a heavy object"]),
    "ancestor":     ("a person from your family who lived long ago",    ["someone you will meet in the future", "a type of food", "a large animal"]),
    "abyss":        ("a very deep, dark, bottomless hole or space",     ["a bright and sunny meadow", "a type of food", "a short path"]),
    "beacon":       ("a bright light used as a signal or guide",        ["a dark shadow", "a loud noise", "a heavy stone"]),
    "cavern":       ("a large underground cave",                         ["a tall tower", "a wide shallow river", "a flat open field"]),
    "chamber":      ("a room, especially one used for a special purpose", ["a type of food", "an outdoor field", "a kind of clothing"]),
    "champion":     ("a winner, or someone who stands up for a cause",  ["someone who always loses", "a type of food", "a broken object"]),
    "crystal":      ("a clear, sparkling, glass-like mineral or gem",   ["a type of food", "a piece of rope", "a dark shadow"]),
    "destiny":      ("the events that will happen to someone in the future", ["something forgotten from the past", "a type of food", "a boring habit"]),
    "dungeon":      ("a dark underground prison or cell",               ["a bright rooftop garden", "a sunny meadow", "a warm cosy kitchen"]),
    "echo":         ("a sound that bounces back after hitting a surface", ["a type of smell", "a bright colour", "a rough texture"]),
    "ember":        ("a small piece of glowing coal or wood from a dying fire", ["a cold block of ice", "a flat smooth stone", "a dry crispy leaf"]),
    "enchantment":  ("a magical spell, or a feeling of great delight",  ["a broken tool", "a noisy crowd", "a dull routine"]),
    "fable":        ("a short story with a moral lesson, often using animals", ["a very long history book", "a type of food", "a piece of clothing"]),
    "fortress":     ("a strong, well-defended building or castle",      ["a small flower garden", "a cosy bedroom", "a sandy beach"]),
    "horizon":      ("the distant line where the sky meets the land or sea", ["the centre of the earth", "the roof of a building", "the bottom of a river"]),
    "illusion":     ("something that tricks the eyes or the mind",      ["a solid and heavy object", "a very loud sound", "a type of food"]),
    "labyrinth":    ("a complicated maze with many twisting paths",     ["a straight open road", "a calm flat lake", "a tall solid tower"]),
    "legend":       ("an old story about heroic people or events passed down over time", ["a boring fact", "a type of food", "a piece of clothing"]),
    "mystery":      ("something strange that is hard to explain or understand", ["something very easy to understand", "a boring routine", "a heavy object"]),
    "omen":         ("a sign believed to show what will happen in the future", ["a memory from the past", "a type of food", "a piece of clothing"]),
    "portal":       ("a doorway or entrance, especially a magical one", ["a solid wall", "a heavy stone", "a flat floor"]),
    "prophecy":     ("a statement predicting what will happen in the future", ["a memory of the past", "a type of food", "a boring fact"]),
    "riddle":       ("a question or puzzle with a clever or surprising answer", ["a simple instruction", "a boring story", "a type of food"]),
    "ruins":        ("the broken-down remains of an old building or city", ["a brand new structure", "a type of food", "a living animal"]),
    "sorcerer":     ("a person who practises magic or wizardry",        ["a type of food", "a heavy stone", "an ordinary farmer"]),
    "summit":       ("the highest point of a mountain or hill",         ["the lowest point underground", "the middle of a flat field", "the bottom of a river"]),
    "treasure":     ("valuable things such as gold, jewels, or coins",  ["worthless rubbish", "a type of weather", "an empty box"]),
    "twilight":     ("the soft dim light just after sunset or before sunrise", ["the brightest part of midday", "a type of food", "a heavy rainstorm"]),
    "villain":      ("an evil or wicked character in a story",          ["a kind and heroic person", "a type of food", "a gentle animal"]),
    "voyage":       ("a long journey, especially by sea or through space", ["staying completely still in one place", "a short rest", "a type of food"]),
    "warrior":      ("a person trained and experienced in battle",      ["someone who never leaves home", "a type of food", "a gentle artist"]),
    "wisdom":       ("the ability to make good decisions from experience and knowledge", ["the ability to run very fast", "a type of food", "a heavy object"]),
    "creature":     ("any living animal or being",                      ["a type of stone", "a piece of wood", "a kind of food"]),
    "empire":       ("a large group of countries ruled by one powerful leader", ["a tiny quiet village", "a single house", "a short road"]),
    "silence":      ("a complete absence of any sound",                 ["a very loud noise", "a bright flash of light", "a strong smell"]),
    # ── Verbs ────────────────────────────────────────────────────────────────
    "beckoned":     ("gestured or called to someone to come closer",   ["pushed someone far away", "made a very loud noise", "ate a large meal"]),
    "crumbled":     ("broke apart or fell into small pieces",          ["grew very tall", "shone very brightly", "sang very loudly"]),
    "descended":    ("moved downward from a higher place",             ["climbed up very quickly", "floated sideways", "grew taller"]),
    "devoured":     ("ate something very quickly and completely",       ["left food untouched", "sang quietly to sleep", "slept for a long time"]),
    "emerged":      ("came out into view from somewhere hidden",       ["went deep inside", "stayed perfectly still", "fell fast asleep"]),
    "flickered":    ("shone with a small, unsteady, wavering light",   ["made a very loud noise", "sank to the bottom", "grew very tall"]),
    "galloped":     ("ran very fast, like a horse at full speed",      ["moved very slowly and carefully", "sank to the ground", "whispered quietly"]),
    "glimmered":    ("shone with a soft, faint, gentle light",        ["made a deep rumbling noise", "sank deeply below", "tasted very sweet"]),
    "hesitated":    ("paused before acting because of doubt or fear", ["moved forward confidently", "shouted very loudly", "slept immediately"]),
    "murmured":     ("spoke very quietly in a low, gentle voice",     ["shouted as loudly as possible", "jumped very high", "ran away quickly"]),
    "perched":      ("sat or rested on the edge or top of something", ["dug deep underground", "swam very quickly away", "grew very large"]),
    "pondered":     ("thought carefully and deeply about something",  ["acted without thinking at all", "ran away quickly", "shouted loudly"]),
    "proclaimed":   ("announced something to everyone, loudly and officially", ["whispered a secret", "hid away quietly", "slept peacefully"]),
    "quivered":     ("shook slightly with fear, cold, or excitement", ["stood perfectly and completely still", "laughed very loudly", "grew very tall"]),
    "roamed":       ("wandered freely over a wide area",              ["stayed in one tiny spot", "sank to the ground", "grew very tall"]),
    "shimmered":    ("shone with a soft, rippling, wavy light",       ["made a loud crashing sound", "sank very deeply", "grew very heavy"]),
    "soared":       ("flew or rose very high into the air",           ["dug deep underground", "swam far away", "hid very quietly"]),
    "stumbled":     ("tripped or walked unsteadily",                  ["ran very smoothly and fast", "flew very high", "sang perfectly"]),
    "summoned":     ("called or ordered someone to come",             ["sent someone far away", "ate a large meal", "slept for a long time"]),
    "thundered":    ("made or moved with a very loud deep rumbling noise", ["whispered very softly", "disappeared without a sound", "tiptoed carefully"]),
    "trembled":     ("shook with fear, cold, or strong emotion",      ["stood perfectly still", "laughed loudly", "slept very deeply"]),
    "vanished":     ("disappeared suddenly and completely",           ["appeared very clearly", "grew very tall", "moved very slowly"]),
    "whimpered":    ("made a soft, quiet, whining or crying sound",   ["shouted very loudly", "jumped very high", "ate very quickly"]),
    "yearned":      ("had a very strong desire or longing for something", ["did not care at all", "felt very tired", "ate a large meal"]),
    "lingered":     ("stayed somewhere longer than expected",         ["left immediately", "flew away quickly", "grew very tall"]),
    "shuddered":    ("shook suddenly from fear, cold, or disgust",    ["laughed out loud", "jumped for joy", "sang very sweetly"]),
    "staggered":    ("walked or moved unsteadily, nearly falling",    ["ran perfectly smoothly", "flew very high", "swam gracefully"]),
    "clambered":    ("climbed awkwardly using both hands and feet",   ["slid smoothly down", "floated gently", "dug deeper"]),
    "scattered":    ("spread or threw things in many directions",     ["gathered everything together", "built something up", "kept things neat"]),
    "drifted":      ("moved slowly and gently without direction",     ["rushed forward very fast", "sank straight down", "stood completely still"]),
    "beckoning":    ("signalling or calling someone to come closer",  ["pushing someone far away", "making a loud noise", "eating a large meal"]),
    # ── Adverbs ──────────────────────────────────────────────────────────────
    "silently":     ("without making any sound",                      ["with a very loud crash", "with great speed", "with bright colour"]),
    "gracefully":   ("in a smooth, elegant, and beautiful way",      ["in a clumsy and awkward way", "in a very loud way", "in a very slow way"]),
    "cautiously":   ("carefully, watching out for danger",           ["without any care at all", "very loudly", "very quickly"]),
    "desperately":  ("with great urgency or a very strong need",     ["without any concern", "very slowly", "very quietly"]),
    "eagerly":      ("with great excitement and enthusiasm",         ["with no interest at all", "very slowly", "very angrily"]),
    "fiercely":     ("with great strength, intensity, or passion",   ["very gently and softly", "very slowly", "very quietly"]),
    "solemnly":     ("in a serious and sincere way",                 ["in a funny and joking way", "very quickly", "very loudly"]),
    "wearily":      ("in a tired and exhausted way",                 ["with great energy", "very happily", "very angrily"]),
    "swiftly":      ("very quickly, at great speed",                  ["very slowly and carefully", "very quietly", "very loudly"]),
    "bravely":      ("in a way that shows courage and no fear",      ["in a very clumsy way", "in a very quiet way", "in a very slow way"]),
    "softly":       ("in a quiet, gentle way",                       ["very loudly", "very quickly", "very roughly"]),
    "slowly":       ("not quickly, taking a long time",              ["very fast", "very loudly", "in a clumsy way"]),
    "quickly":      ("at great speed, without taking long",          ["very slowly", "very quietly", "very gently"]),
    "suddenly":     ("happening all at once without warning",        ["very gradually over time", "with great care", "in a very slow way"]),
    # ── More adjectives ──────────────────────────────────────────────────
    "glowing":      ("giving off a warm, steady light",              ["making a deep rumbling sound", "sinking slowly down", "tasting very sweet"]),
    "shadowy":      ("dark and hard to see clearly, like a shadow",  ["extremely bright and clear", "loud and echoing", "warm and comfortable"]),
    "hollow":       ("empty inside, having nothing inside it",       ["completely solid and heavy", "bright and colourful", "smooth and flat"]),
    "twisted":      ("bent into an unusual shape, not straight",     ["perfectly straight and neat", "very warm and soft", "bright and shiny"]),
    "ancient":      ("very old, from a long time ago",               ["brand new and shiny", "very small and tiny", "extremely loud"]),
    "powerful":     ("having great strength or force",               ["very weak and fragile", "very quiet and small", "very slow"]),
    "magical":      ("having special power that seems impossible",   ["very ordinary and boring", "very heavy and solid", "quite dangerous"]),
    "hidden":       ("kept out of sight, not easy to find",         ["placed in clear view for all", "very loud and noisy", "very large"]),
    "withered":     ("dried up and shrunken, no longer fresh",      ["blooming and fully grown", "wet and dripping", "strong and solid"]),
    "swirling":     ("moving in circles or spinning patterns",      ["standing perfectly still", "sinking straight down", "frozen in place"]),
    "glittering":   ("sparkling with many small flashes of light",  ["making a very loud sound", "smelling strongly", "feeling very rough"]),
    "towering":     ("very tall and impressive, reaching high up",  ["small and low to the ground", "wide and flat", "soft and bendable"]),
    "jagged":       ("having sharp uneven points or edges",         ["completely smooth and flat", "soft and round", "warm and comfortable"]),
    "crumbling":    ("slowly falling apart into small pieces",      ["getting stronger and bigger", "becoming brighter", "growing taller"]),
    "daunting":     ("seeming very difficult, making you feel afraid to try", ["very simple and easy", "quite enjoyable", "very boring"]),
    "precious":     ("of great value, very important or loved",     ["worthless and unimportant", "heavy and dull", "broken and useless"]),
    "sacred":       ("holy and deserving great respect",            ["ordinary and everyday", "noisy and crowded", "old and broken"]),
    "perilous":     ("full of danger, very risky",                  ["completely safe and easy", "very boring and dull", "warm and comfortable"]),
    "treacherous":  ("very dangerous or likely to betray you",      ["completely safe and trustworthy", "very kind and helpful", "very slow"]),
    "desolate":     ("empty and without life, very lonely and bleak", ["full of people and noise", "warm and welcoming", "bright and cheerful"]),
    "withstanding": ("staying strong despite pressure or difficulty", ["giving up right away", "growing quickly", "moving far away"]),
    # ── More nouns ───────────────────────────────────────────────────────
    "shadow":       ("a dark shape made when something blocks light", ["a very loud sound", "a type of food", "a warm breeze"]),
    "quest":        ("a long search or journey towards an important goal", ["a short nap", "a type of food", "a boring task"]),
    "courage":      ("the strength to face something scary or difficult", ["the feeling of being very sleepy", "a type of food", "a short journey"]),
    "burden":       ("a heavy load or something difficult to carry or deal with", ["something very light and easy", "a type of food", "a fun game"]),
    "guardian":     ("someone who protects and watches over another", ["someone who ignores others", "a type of food", "a loud sound"]),
    "ancient":      ("something very old, from a long time ago",     ["something brand new", "a type of food", "something very small"]),
    "veil":         ("a thin covering that hides something",         ["a very loud noise", "a type of food", "a strong bright light"]),
    "realm":        ("a kingdom or an area under someone's rule",    ["a type of food", "a small path", "a loud sound"]),
    "gloom":        ("darkness and sadness, a feeling of low spirits", ["great happiness and light", "a type of food", "a warm summer day"]),
    "shrine":       ("a special place considered holy and important", ["a rubbish dump", "a noisy playground", "a type of food"]),
    "torment":      ("great physical or mental pain and suffering",   ["great happiness and comfort", "a type of food", "a quiet rest"]),
    "triumph":      ("a great victory or achievement",               ["a terrible defeat", "a type of food", "a type of clothing"]),
    "descent":      ("the act of going down from a higher place",   ["the act of climbing up quickly", "a type of food", "a wide open space"]),
    "cavern":       ("a large underground cave",                     ["a tall tower", "a wide shallow river", "a flat open field"]),
    # ── More verbs ───────────────────────────────────────────────────────
    "whispered":    ("spoke in a very soft, quiet voice",            ["shouted as loudly as possible", "jumped very high", "ran away quickly"]),
    "gathered":     ("came together or collected things in one place", ["spread far apart", "made a loud noise", "fell asleep"]),
    "revealed":     ("showed or uncovered something hidden",         ["hid something more deeply", "made a loud noise", "ate quickly"]),
    "crept":        ("moved slowly and quietly to avoid being noticed", ["ran loudly and quickly", "jumped very high", "flew away"]),
    "snarled":      ("made an angry growling sound showing teeth",   ["sang very sweetly", "slept quietly", "floated gently"]),
    "charged":      ("rushed forward very fast towards something",   ["backed away slowly", "sat down quietly", "floated gently"]),
    "paused":       ("stopped for a short time before continuing",   ["rushed forward very quickly", "grew taller", "flew away"]),
    "trembling":    ("shaking slightly with fear, cold, or excitement", ["laughing loudly", "jumping high", "sleeping deeply"]),
    "plunged":      ("jumped or fell quickly into something",        ["rose slowly upward", "crept quietly", "floated away"]),
    "unfolded":     ("opened out or developed gradually",            ["rolled up tightly", "disappeared suddenly", "shrank down"]),
    "crouched":     ("bent down low with knees bent, close to the ground", ["stretched up as tall as possible", "swam quickly", "flew away"]),
    "weaved":       ("moved in and out with twists and turns",       ["went in a straight line", "sank to the bottom", "stood still"]),
    "clutched":     ("held on tightly, gripping firmly",            ["threw far away", "let go gently", "ignored completely"]),
    "soaring":      ("flying or rising very high into the air",     ["sinking deep underground", "crawling very slowly", "hiding in a hole"]),
    "racing":       ("moving very fast, rushing ahead",             ["staying perfectly still", "moving very slowly", "sleeping deeply"]),
}


def allocate_story_vocab_words(
    sections: list[dict],
    n_per_section: int = VOCAB_QUESTIONS_PER_SECTION,
) -> dict[str, list[str]]:
    """
    Examine ALL story sections in one pass and return ``n_per_section`` unique
    teaching words for each section that needs vocabulary questions.

    Guarantees:
    - Every returned word appears verbatim (lowercase) in its section's text.
    - No word is assigned to more than one section.
    - Proper nouns (character/place names) are excluded.
    - Words are chosen by frequency within the section (most-used first),
      then by length (longer = more likely to be a good teaching word).

    Returns:
        {section_title: [word, word, ...], ...}
        Sections with fewer candidate words than n_per_section get what's available.
    """
    import re

    # Build per-section word frequency tables
    section_data: dict[str, tuple[str, dict[str, int], set[str]]] = {}
    for section in sections:
        title = section.get("title", "")
        text = section.get("content", "") or section.get("text", "")
        if not text:
            continue
        text_lower = text.lower()

        # Detect proper nouns: words that appear capitalised mid-sentence
        # (i.e. NOT immediately after a sentence-ending . ! ? or at start of text).
        # These are almost certainly character/place names.
        proper_nouns: set[str] = set()
        for m in re.finditer(r'(?<=[a-z,;:\-]\s)([A-Z][a-z]{3,})\b', text):
            proper_nouns.add(m.group(1).lower())
        # Also catch names that appear at the very start of a quoted/dialogue line
        for m in re.finditer(r'(?:"\s*|\u2018\s*|\u201c\s*)([A-Z][a-z]{3,})\b', text):
            proper_nouns.add(m.group(1).lower())

        # Extract all purely alphabetic tokens of 5+ chars
        tokens = re.findall(r'\b[a-z]{5,}\b', text_lower)
        freq: dict[str, int] = {}
        for w in tokens:
            if w not in _STOP_WORDS and w not in proper_nouns:
                freq[w] = freq.get(w, 0) + 1
        section_data[title] = (text_lower, freq, proper_nouns)

    global_used: set[str] = set()
    result: dict[str, list[str]] = {}

    for section in sections:
        title = section.get("title", "")
        if title not in section_data:
            continue
        _text_lower, freq, _proper_nouns = section_data[title]
        candidates = sorted(
            [(w, c) for w, c in freq.items() if w not in global_used],
            key=lambda x: (-x[1], -len(x[0])),
        )
        chosen = [w for w, _ in candidates[:n_per_section]]
        result[title] = chosen
        global_used.update(chosen)

    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_or_init_state(profile_id: str, age_group: str) -> dict:
    """
    Fetch ML state for a profile. If no state exists yet, return cold-start defaults
    based on age_group without writing to DB (write only happens on first real event).
    """
    state = get_ml_state(profile_id)
    if state is None:
        base = AGE_GROUP_BASE_LEVEL.get(age_group, 5.0)
        return {
            "profile_id": profile_id,
            "reading_level_score": base,
            "engagement_score": 0.5,
            "completion_rate": 0.0,
            "avg_time_per_word_ms": 0.0,
            "replay_rate": 0.0,
            "question_accuracy": 0.0,
            "session_frequency_per_week": 0.0,
            "preferred_themes": [],
            "preferred_settings": [],
            "total_stories_started": 0,
            "total_stories_completed": 0,
            "total_events": 0,
        }
    return state


def _rule_based_reading_level(state: dict, age_group: str) -> float:
    """
    Compute reading level from behavioral signals using hand-crafted rules.

    Rules:
      - Start from age-group base level
      - Completion rate < 0.40 → content too hard → lower
      - Completion rate > 0.90 (after enough stories) → too easy → raise
      - Fast reading (low ms/word) after 3+ stories → raise
      - High question accuracy → raise
      - High replay rate → lower (re-reading indicates difficulty)
    """
    base = AGE_GROUP_BASE_LEVEL.get(age_group, 5.0)
    completed = state["total_stories_completed"]
    cr = state["completion_rate"]
    atpw = state["avg_time_per_word_ms"]
    qa = state["question_accuracy"]
    rr = state["replay_rate"]

    adjustment = 0.0

    if completed >= 3:
        if cr < 0.40:
            adjustment -= 1.0
        elif cr > 0.90 and completed >= 5:
            adjustment += 0.5

    if completed >= 3 and atpw > 0:
        # ~300 ms/word ≈ average reader; < 200 ms/word = fast
        if atpw < 200:
            adjustment += 0.3
        elif atpw > 600:
            adjustment -= 0.3

    if state["total_events"] >= 5:  # need some question data
        if qa > 0.80:
            adjustment += 0.5
        elif qa < 0.40:
            adjustment -= 0.5

    if rr > 0.30 and completed >= 3:
        adjustment -= 0.3

    return base + adjustment


def _sklearn_reading_level(model, scaler, state: dict, age_group: str) -> float:
    """Run sklearn regression model for reading level."""
    try:
        features = _build_sklearn_features(state, age_group)
        scaled = scaler.transform([features])
        return float(model.predict(scaled)[0])
    except Exception as e:
        print(f"[ML] sklearn reading level failed: {e}, falling back to rules")
        return _rule_based_reading_level(state, age_group)


def _rule_based_engagement(state: dict) -> float:
    """Compute engagement score (0–1) from behavioral signals."""
    score = 0.0
    score += 0.35 * state["completion_rate"]
    score += 0.25 * min(1.0, state["session_frequency_per_week"] / 5.0)
    score += 0.20 * state["question_accuracy"]
    score += 0.10 * min(1.0, state["replay_rate"] / 0.5)

    # Recency penalty: penalise if we haven't seen the profile recently
    last_computed = state.get("last_computed_at")
    if last_computed:
        try:
            last_dt = datetime.fromisoformat(last_computed)
            days_ago = (datetime.now(timezone.utc) - last_dt).days
            recency_penalty = max(0, (days_ago - 7) / 30.0)
            score -= 0.10 * recency_penalty
        except Exception:
            pass

    return score


def _sklearn_engagement(model, scaler, state: dict) -> float:
    """Run sklearn logistic regression for engagement probability."""
    try:
        features = _build_sklearn_features(state, "6-8")  # age_group less important here
        scaled = scaler.transform([features])
        proba = model.predict_proba(scaled)
        return float(proba[0][1])  # probability of class 1 (engaged)
    except Exception as e:
        print(f"[ML] sklearn engagement failed: {e}, falling back to rules")
        return _rule_based_engagement(state)


def _build_sklearn_features(state: dict, age_group: str) -> list:
    """Build numeric feature vector for sklearn models."""
    age_encoded = {"3-5": 1, "6-8": 2, "9-12": 3}.get(age_group, 2)
    return [
        age_encoded,
        state["completion_rate"],
        math.log1p(state["avg_time_per_word_ms"]),
        state["question_accuracy"],
        state["replay_rate"],
        math.log1p(state["total_stories_completed"]),
        min(1.0, state["session_frequency_per_week"] / 7.0),
    ]


def _cold_start_recommendation(age_group: str, reading_score: float) -> dict:
    """Return age-group default recommendation for profiles with little data."""
    themes = AGE_DEFAULT_THEMES.get(age_group, ["friendship"])
    settings = AGE_DEFAULT_SETTINGS.get(age_group, ["a magical world"])
    return {
        "age_group": age_group,
        "theme": random.choice(themes),
        "setting": random.choice(settings),
        "complexity_hint": _score_to_complexity(reading_score),
        "vocabulary_hint": _score_to_vocab(reading_score),
        "confidence": 0.30,
        "cold_start": True,
        "model_tier": "cold_start_defaults",
    }


def _pick_diverse(preferred: list, recent: list, fallback: list) -> str:
    """Pick a preferred item that isn't in the recent list. Fall back to defaults."""
    candidates = [p for p in preferred if p not in recent]
    if candidates:
        return candidates[0]
    if preferred:
        return preferred[0]  # all preferred seen recently — allow repeat
    return random.choice(fallback)


def _recommendation_confidence(state: dict) -> float:
    """
    Confidence of preference-based recommendation.
    Grows with the number of completed stories (caps at ~0.90).
    """
    n = state["total_stories_completed"]
    return min(0.90, 0.30 + 0.06 * n)


def _score_to_complexity(score: float) -> str:
    for threshold, label in COMPLEXITY_THRESHOLDS:
        if score <= threshold:
            return label
    return "rich"


def _score_to_vocab(score: float) -> str:
    for threshold, label in VOCAB_THRESHOLDS:
        if score <= threshold:
            return label
    return "stretch"


def _level_to_label(score: float) -> str:
    """Convert numeric reading level to human-readable grade label."""
    mapping = [
        (1.5, "Pre-K"),
        (2.5, "Kindergarten"),
        (3.5, "Grade 1"),
        (4.5, "Grade 1–2"),
        (5.5, "Grade 2–3"),
        (6.5, "Grade 3–4"),
        (7.5, "Grade 4–5"),
        (8.5, "Grade 5–6"),
        (9.5, "Grade 6–7"),
        (10.1, "Grade 7+"),
    ]
    for threshold, label in mapping:
        if score <= threshold:
            return label
    return "Grade 7+"


def _level_to_age_group(score: float, registered_age_group: str) -> str:
    """
    Convert a reading level score to the closest age-group string.
    Only allows one step deviation from registered age group to avoid jarring shifts.
    """
    if score <= 3.5:
        suggested = "3-5"
    elif score <= 7.0:
        suggested = "6-8"
    else:
        suggested = "9-12"

    # One-step-only rule (3-5 → 6-8 → 9-12)
    order = ["3-5", "6-8", "9-12"]
    r_idx = order.index(registered_age_group)
    s_idx = order.index(suggested)
    final_idx = max(r_idx - 1, min(r_idx + 1, s_idx))
    return order[final_idx]


def _engagement_label(score: float) -> str:
    if score >= 0.70:
        return "high"
    if score >= 0.45:
        return "medium"
    if score >= 0.20:
        return "low"
    return "at_risk"


def _vocab_score_label(score: float) -> str:
    """Human-readable label for vocabulary score (1–10)."""
    if score <= 3.5:
        return "Simple"
    if score <= 7.0:
        return "Grade Level"
    return "Advanced"


def _llm_questions_for_words(
    words: list[str],
    act_text: str,
    age_group: str,
) -> list[dict] | None:
    """
    Ask Gemini to write one MCQ definition question for each word in ``words``.
    All words are guaranteed to appear in act_text (caller's responsibility).
    Returns a list of question dicts, or None on any failure.

    This is more reliable than _llm_generate_vocab_questions because the LLM
    is not asked to pick words — it only needs to write definitions.
    """
    try:
        import config
        if not config.GEMINI_API_KEY:
            return None

        import google.genai as genai
        import re

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        words_json = json.dumps(words)

        prompt = f"""You are a vocabulary teacher for children aged {age_group}.

Chapter text (the words below all appear in this chapter):
\"\"\"
{act_text[:4000]}
\"\"\"

For EACH word in the list below, write one multiple-choice question that asks what the word means.
Words to use: {words_json}

Rules:
- Write exactly one question per word, in the same order as the list.
- question_text must contain the word in double quotes and end with a question mark.
- Use 4 options (A, B, C, D). One is correct; three are plausible but wrong.
- Vary which letter (A/B/C/D) is the correct answer across questions.
- Language and difficulty must suit age group {age_group}.
- No scary, violent, or inappropriate content.

Return ONLY a valid JSON array — no markdown fences, no extra text:
[
  {{
    "word": "gleaming",
    "question_text": "In the story, what does the word \\"gleaming\\" mean?",
    "options": ["A. Making a loud noise", "B. Shining brightly", "C. Moving very fast", "D. Feeling sad"],
    "correct_answer": "B"
  }}
]"""

        response = client.models.generate_content(
            model=config.GEMINI_MODEL_STANDARD,
            contents=prompt,
        )
        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        items = json.loads(raw)
        if not isinstance(items, list) or len(items) == 0:
            return None

        # Build a lookup: provided word → canonical form (lowercase)
        provided_lower = {w.lower(): w for w in words}
        act_text_lower = act_text.lower()
        result = []
        for item in items:
            if not all(k in item for k in ("question_text", "options", "correct_answer")):
                continue
            word_raw = item.get("word", "").strip()
            word_lower = word_raw.lower()

            # Try to resolve back to one of the provided words.
            # 1. Exact match in provided list
            # 2. The provided word starts with the LLM word (e.g. provided "trembling", LLM "trembl")
            # 3. The LLM word starts with the provided word (e.g. provided "tremble", LLM "trembled")
            resolved = None
            if word_lower in provided_lower:
                resolved = word_lower
            else:
                for pw in provided_lower:
                    if pw.startswith(word_lower[:5]) or word_lower.startswith(pw[:5]):
                        resolved = pw
                        break

            # Verify the resolved word is in the chapter text (it should be — it came from the allocator)
            if resolved and resolved in act_text_lower:
                canonical = provided_lower[resolved]
            elif word_lower in act_text_lower:
                canonical = word_raw
            else:
                print(f"[ML] _llm_questions_for_words: '{word_lower}' not in chapter text — skipping")
                continue

            if not item["question_text"].endswith("?"):
                item["question_text"] = item["question_text"].rstrip(".") + "?"
            result.append({
                "question_text": item["question_text"],
                "options": item["options"][:4],
                "correct_answer": item["correct_answer"].strip().upper(),
                "word": canonical,
            })

        return result if result else None

    except Exception as e:
        print(f"[ML] _llm_questions_for_words failed: {e}")
        return None


def _simple_questions_for_words(
    words: list[str],
    profile_id: str,
    story_id: str,
    act_number: int,
    act_text: str,
    used_words: set,
) -> list[dict]:
    """
    Fallback when _llm_questions_for_words fails.
    Priority order for each word:
      1. Look up in _VOCAB_DEFINITIONS (always correct, no LLM needed)
      2. Ask Gemini for a one-sentence definition (_fetch_definition_mcq)
      3. Skip the word entirely — never emit a question with a wrong correct answer
    """
    act_text_lower = act_text.lower()
    result = []
    for word in words:
        word_lower = word.lower()
        if word_lower not in act_text_lower:
            continue

        # --- 1. Built-in dictionary (guaranteed correct) ---
        if word_lower in _VOCAB_DEFINITIONS:
            correct_def, wrong_defs = _VOCAB_DEFINITIONS[word_lower]
            letters = ["A", "B", "C", "D"]
            correct_pos = random.randint(0, 3)
            correct_letter = letters[correct_pos]
            all_defs: list[str] = list(wrong_defs[:3])
            all_defs.insert(correct_pos, correct_def)
            options = [f"{l}. {d[0].upper() + d[1:]}" for l, d in zip(letters, all_defs)]
            qdata = {"options": options, "correct_answer": correct_letter}
        else:
            # --- 2. Ask Gemini for a real definition ---
            qdata = _fetch_definition_mcq(word)
            if qdata is None:
                # --- 3. No reliable answer available — skip this word ---
                print(f"[ML] Skipping word '{word}' — no definition available")
                continue

        q = {
            "question_id":    str(uuid.uuid4()),
            "profile_id":     profile_id,
            "story_id":       story_id,
            "act_number":     act_number,
            "question_text":  f'What does the word "{word}" mean?',
            "question_type":  "vocabulary",
            "options":        qdata["options"],
            "correct_answer": qdata["correct_answer"],
            "word":           word,
            "generated_by":   "simple_fallback",
        }
        save_question(q)
        result.append(q)
        used_words.add(word_lower)
    return result


def _fetch_definition_mcq(word: str) -> dict | None:
    """
    Ask Gemini for a real one-sentence definition and 3 wrong options for a word.
    Returns {options, correct_answer} or None if unavailable.
    Never falls back to heuristics — caller decides what to do with None.
    """
    try:
        import config
        if not config.GEMINI_API_KEY:
            return None
        import google.genai as genai, re, json as _json
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        prompt = (
            f'Give a child-friendly definition of the word "{word}" in 5-8 words.\n'
            f'Also give 3 wrong but plausible definitions (5-8 words each) that a child might confuse it with.\n'
            f'Return ONLY valid JSON (no markdown, no extra text):\n'
            f'{{"correct": "shining with a bright gentle light", "wrong": ["making a very loud crashing noise", "moving forward very quickly", "feeling cold and shivery"]}}'
        )
        resp = client.models.generate_content(model=config.GEMINI_MODEL_STANDARD, contents=prompt)
        raw = resp.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        data = _json.loads(raw)
        correct_def = str(data["correct"]).strip()
        wrong_defs  = [str(d).strip() for d in data["wrong"][:3]]
        if len(wrong_defs) < 3:
            return None  # malformed response
        # Sanity: correct answer must not contain the word itself
        if word.lower() in correct_def.lower():
            correct_def = correct_def.replace(word, "it").replace(word.capitalize(), "it")
        letters = ["A", "B", "C", "D"]
        correct_pos = random.randint(0, 3)
        correct_letter = letters[correct_pos]
        all_defs: list[str] = list(wrong_defs)
        all_defs.insert(correct_pos, correct_def)
        options = [f"{l}. {d[0].upper() + d[1:]}" for l, d in zip(letters, all_defs)]
        return {"options": options, "correct_answer": correct_letter}
    except Exception as e:
        print(f"[ML] _fetch_definition_mcq failed for '{word}': {e}")
        return None


def _llm_generate_vocab_questions(
    act_text: str,
    age_group: str,
    n: int,
    used_words: set | None = None,
) -> list[dict] | None:
    """
    Ask Gemini to identify challenge words in the text and create n vocabulary MCQ
    questions. Returns a list of question dicts or None on any failure.

    ``used_words`` (lowercase) are excluded from selection so earlier-chapter words
    are never repeated.
    """
    try:
        import config
        if not config.GEMINI_API_KEY:
            return None

        import google.genai as genai
        import re

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        exclusion_note = ""
        if used_words:
            words_list = ", ".join(sorted(used_words))
            exclusion_note = (
                f"\nEXCLUDED WORDS (already used in earlier chapters — do NOT use these): {words_list}\n"
            )

        # Send up to 4000 chars so the LLM has the full chapter context
        chapter_excerpt = act_text[:4000]

        prompt = f"""You are a vocabulary teacher creating quiz questions for children aged {age_group}.

Below is the EXACT chapter text:
\"\"\"
{chapter_excerpt}
\"\"\"
{exclusion_note}
Your job: Find {n} teaching words in the chapter text above.

STRICT RULES for choosing words:
1. The word MUST appear verbatim (exactly as written) somewhere in the chapter text above.
   Copy it exactly — lowercase, as it appears.
2. Do NOT use names of people, places, or animals.
3. Do NOT use very simple words (a, the, is, was, big, run, etc.).
4. Do NOT use any word from the EXCLUDED WORDS list.
5. Every word must be different from all others in your list.
6. Pick words a child aged {age_group} might not know — good teaching words.

For each word write one multiple-choice question (4 options A/B/C/D).
One option is the correct definition; the others are plausible but wrong.
Vary which letter is correct.

Return ONLY a valid JSON array — no explanation, no markdown fences:
[
  {{
    "word": "gleaming",
    "question_text": "In the story, what does the word \\"gleaming\\" mean?",
    "options": ["A. Making a loud noise", "B. Shining brightly", "C. Moving very fast", "D. Feeling sad"],
    "correct_answer": "B"
  }}
]

Reminders:
- question_text must include the word and end with ?
- Options must start with A. B. C. D.
- Language suitable for age {age_group}
- No scary, violent, or inappropriate content"""

        response = client.models.generate_content(
            model=config.GEMINI_MODEL_STANDARD,
            contents=prompt,
        )
        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        items = json.loads(raw)
        if not isinstance(items, list) or len(items) == 0:
            return None

        act_text_lower = act_text.lower()
        result = []
        seen_this_batch: set = set()
        for item in items:
            if len(result) >= n:
                break
            if not all(k in item for k in ("question_text", "options", "correct_answer")):
                continue
            word_lower = item.get("word", "").lower().strip()
            if not word_lower:
                continue
            # Hard check: word must actually appear in this chapter's text
            if word_lower not in act_text_lower:
                print(f"[ML] LLM returned word '{word_lower}' not found in chapter text — skipping")
                continue
            # Hard check: word must not have been used in a previous chapter
            if word_lower in used_words:
                print(f"[ML] LLM returned already-used word '{word_lower}' — skipping")
                continue
            # Hard check: no intra-batch duplicates
            if word_lower in seen_this_batch:
                continue
            seen_this_batch.add(word_lower)
            if not item["question_text"].endswith("?"):
                item["question_text"] = item["question_text"].rstrip(".") + "?"
            result.append({
                "question_text": item["question_text"],
                "options": item["options"][:4],
                "correct_answer": item["correct_answer"].strip().upper(),
                "word": item.get("word", ""),
            })

        return result if result else None

    except Exception as e:
        print(f"[ML] LLM vocab question generation failed: {e}")
        return None


def _rule_based_vocab_questions(
    profile_id: str,
    story_id: str,
    act_number: int,
    act_text: str,
    age_group: str,
    n: int,
    used_words: set | None = None,
) -> list[dict]:
    """
    Build vocabulary questions from the pre-defined word bank.
    Preferentially uses words that actually appear in act_text.
    Words already in ``used_words`` (from previous chapters) are excluded.
    The set is updated in-place with the words chosen here.
    """
    if used_words is None:
        used_words = set()

    bank = _FALLBACK_VOCAB.get(age_group, _FALLBACK_VOCAB["6-8"])
    text_lower = act_text.lower()

    # Only use words that actually appear in the chapter text AND haven't been used yet.
    # This guarantees readers can infer the meaning from the chapter they just read.
    in_text = [
        entry for entry in bank
        if entry[0].lower() in text_lower and entry[0].lower() not in used_words
    ]
    random.shuffle(in_text)
    ordered = in_text[:n]

    letters = ["A", "B", "C", "D"]
    questions = []
    for word, correct_def, wrong_defs in ordered:
        correct_letter = random.choice(letters)
        options_pool = wrong_defs[:3]
        all_opts: dict[str, str] = {}
        other_letters = [l for l in letters if l != correct_letter][:len(options_pool)]
        all_opts[correct_letter] = correct_def
        for l, d in zip(other_letters, options_pool):
            all_opts[l] = d
        # Fill missing letter if bank has < 3 wrong defs
        for l in letters:
            if l not in all_opts:
                all_opts[l] = "none of these"
        opts_list = [f"{l}. {all_opts[l]}" for l in letters]

        q = {
            "question_id":   str(uuid.uuid4()),
            "profile_id":    profile_id,
            "story_id":      story_id,
            "act_number":    act_number,
            "question_text": f'What does the word "{word}" mean?',
            "question_type": "vocabulary",
            "options":       opts_list,
            "correct_answer": correct_letter,
            "word":          word,
            "generated_by":  "rule_based",
        }
        save_question(q)
        questions.append(q)
        used_words.add(word.lower())  # mark as used for subsequent chapters

    return questions


def _extract_first_character(text: str) -> str:
    """
    Heuristic: extract the most likely character name from act text.
    Used to personalize question templates. Returns 'the hero' as default.
    """
    import re
    # Look for a capitalized word that appears 2+ times (likely a character name)
    words = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
    if not words:
        return "the hero"
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    # Exclude common non-name words
    exclude = {"The", "And", "But", "For", "With", "That", "This", "When", "Then"}
    candidates = [(w, c) for w, c in counts.items() if w not in exclude]
    if not candidates:
        return "the hero"
    return max(candidates, key=lambda x: x[1])[0]


def _rule_based_question(
    profile_id: str,
    story_id: str,
    act_number: int,
    question_type: str,
    character: str,
) -> dict:
    """Generate a rule-based question using templates."""
    templates = QUESTION_TEMPLATES.get(question_type, QUESTION_TEMPLATES["comprehension"])
    template = random.choice(templates)
    question_text = template.replace("{character}", character).replace("{word}", "mysterious")

    # Minimal multiple choice options for comprehension/prediction
    if question_type == "comprehension":
        options = [
            f"A. {character} was brave and kept going.",
            "B. Nothing important happened.",
            f"C. {character} decided to turn back.",
        ]
        correct = "A"
    elif question_type == "prediction":
        options = [
            f"A. {character} will find a clever solution.",
            f"B. {character} will ask a friend for help.",
            f"C. {character} will discover something surprising.",
        ]
        correct = random.choice(["A", "B", "C"])
    else:  # reflection / vocabulary
        options = []
        correct = ""

    return {
        "question_id": str(uuid.uuid4()),
        "profile_id": profile_id,
        "story_id": story_id,
        "act_number": act_number,
        "question_text": question_text,
        "question_type": question_type,
        "options": options,
        "correct_answer": correct,
        "generated_by": "rule_based",
    }


def _llm_generate_question(
    act_text: str,
    age_group: str,
    question_type: str,
    character: str,
) -> dict | None:
    """
    Use Gemini Flash to generate a contextual question from act text.
    Returns parsed question dict or None on failure.
    """
    try:
        import config
        if not config.GEMINI_API_KEY:
            return None

        import google.genai as genai

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        prompt = f"""You are helping generate interactive questions for a children's story app.
Age group: {age_group}
Question type: {question_type} (comprehension=check understanding, prediction=what happens next, reflection=moral/feelings)
Character in focus: {character}

Story excerpt:
\"\"\"
{act_text[:800]}
\"\"\"

Generate exactly 1 age-appropriate {question_type} question.
Return ONLY valid JSON in this exact format, no other text:
{{
  "question_text": "...",
  "options": ["A. ...", "B. ...", "C. ..."],
  "correct_answer": "A",
  "question_type": "{question_type}"
}}

Rules:
- Language must be appropriate for age group {age_group}
- No scary, violent, or inappropriate content
- Options must be plausible but have one clear best answer
- question_text must end with a question mark"""

        response = client.models.generate_content(
            model=config.GEMINI_MODEL_STANDARD,
            contents=prompt,
        )
        raw = response.text.strip()

        # Strip markdown code fences if present
        import re
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        data = json.loads(raw)

        # Validate required keys
        if not all(k in data for k in ("question_text", "options", "correct_answer")):
            return None
        if not data["question_text"].endswith("?"):
            return None

        return {
            "question_text": data["question_text"],
            "options": data["options"][:3],
            "correct_answer": data["correct_answer"],
            "question_type": data.get("question_type", question_type),
        }

    except Exception as e:
        print(f"[ML] LLM question generation failed: {e}")
        return None


# ── Model loading (V2+) ────────────────────────────────────────────────────────

def _load_model(name: str):
    """
    Load a pickled sklearn model and scaler from data/models/.
    Returns (model, scaler) or (None, None) if not available.

    File convention:
      data/models/reading_level_model.pkl
      data/models/reading_level_scaler.pkl
    """
    model_path = os.path.join(MODELS_DIR, f"{name}_model.pkl")
    scaler_path = os.path.join(MODELS_DIR, f"{name}_scaler.pkl")

    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return None, None

    try:
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)
        return model, scaler
    except Exception as e:
        print(f"[ML] Failed to load model '{name}': {e}")
        return None, None


# ── Training entrypoint (V2) ───────────────────────────────────────────────────

def train_reading_level_model():
    """
    Train and persist a GradientBoostingRegressor for reading level estimation.
    Requires scikit-learn. Should be called from a nightly cron job.

    Pseudo-label: for each profile, the reading level score is computed by
    the rule-based estimator on a held-out window, then used as the training target.
    This bootstraps the model from heuristic labels until parent labels are available.

    Call this only when you have >= 50 profiles with >= 10 completed stories each.
    """
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_squared_error
        import numpy as np
        from services.storage import get_db as _get_db

        conn = _get_db()
        rows = conn.execute("SELECT * FROM profile_ml_state WHERE total_stories_completed >= 10").fetchall()
        conn.close()

        if len(rows) < 20:
            print(f"[ML TRAIN] Insufficient data: {len(rows)} eligible profiles (need >= 20). Skipping.")
            return

        X, y = [], []
        for row in rows:
            state = dict(row)
            # We need the profile's age_group — fetch from profiles table
            conn = _get_db()
            profile_row = conn.execute(
                "SELECT age_group FROM profiles WHERE id = ?", (state["profile_id"],)
            ).fetchone()
            conn.close()
            if not profile_row:
                continue
            age_group = dict(profile_row)["age_group"]
            features = _build_sklearn_features(state, age_group)
            label = _rule_based_reading_level(state, age_group)  # pseudo-label
            X.append(features)
            y.append(label)

        X_arr = np.array(X)
        y_arr = np.array(y)

        X_train, X_test, y_train, y_test = train_test_split(X_arr, y_arr, test_size=0.2, random_state=42)

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42)
        model.fit(X_train_s, y_train)

        rmse = mean_squared_error(y_test, model.predict(X_test_s)) ** 0.5
        print(f"[ML TRAIN] Reading level RMSE: {rmse:.3f}")

        os.makedirs(MODELS_DIR, exist_ok=True)
        with open(os.path.join(MODELS_DIR, "reading_level_model.pkl"), "wb") as f:
            pickle.dump(model, f)
        with open(os.path.join(MODELS_DIR, "reading_level_scaler.pkl"), "wb") as f:
            pickle.dump(scaler, f)

        print(f"[ML TRAIN] Reading level model saved (trained on {len(X_train)} profiles).")

    except ImportError:
        print("[ML TRAIN] scikit-learn not installed. Skipping model training.")
    except Exception as e:
        print(f"[ML TRAIN] Training failed: {e}")


def train_engagement_model():
    """
    Train and persist a LogisticRegression engagement classifier.
    Label: profile returned within 72h AND completed >= 1 story in that session.
    Requires scikit-learn.
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import roc_auc_score
        import numpy as np
        from services.storage import get_db as _get_db
        from datetime import timedelta

        conn = _get_db()
        rows = conn.execute("SELECT * FROM profile_ml_state WHERE total_events >= 20").fetchall()
        conn.close()

        if len(rows) < 20:
            print(f"[ML TRAIN] Insufficient data for engagement model. Skipping.")
            return

        X, y = [], []
        for row in rows:
            state = dict(row)
            pid = state["profile_id"]

            # Proxy label: check if profile returned within 72h of last computed date
            conn = _get_db()
            last_session_row = conn.execute(
                """SELECT MAX(server_ts) FROM reading_events
                   WHERE profile_id = ? AND event_type = 'session_ended'""",
                (pid,),
            ).fetchone()
            conn.close()

            label = 0
            if last_session_row and last_session_row[0]:
                last_ts = datetime.fromisoformat(last_session_row[0])
                cutoff = last_ts + timedelta(hours=72)
                conn = _get_db()
                return_count = conn.execute(
                    """SELECT COUNT(*) FROM reading_events
                       WHERE profile_id = ? AND event_type = 'story_completed'
                       AND server_ts > ? AND server_ts <= ?""",
                    (pid, last_ts.isoformat(), cutoff.isoformat()),
                ).fetchone()[0]
                conn.close()
                label = 1 if return_count >= 1 else 0

            conn = _get_db()
            profile_row = conn.execute("SELECT age_group FROM profiles WHERE id = ?", (pid,)).fetchone()
            conn.close()
            age_group = dict(profile_row)["age_group"] if profile_row else "6-8"

            X.append(_build_sklearn_features(state, age_group))
            y.append(label)

        X_arr = np.array(X)
        y_arr = np.array(y)

        if len(set(y_arr)) < 2:
            print("[ML TRAIN] Engagement labels are all one class. Skipping.")
            return

        X_train, X_test, y_train, y_test = train_test_split(X_arr, y_arr, test_size=0.2, random_state=42)

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = LogisticRegression(class_weight="balanced", max_iter=500)
        model.fit(X_train_s, y_train)

        auc = roc_auc_score(y_test, model.predict_proba(X_test_s)[:, 1])
        print(f"[ML TRAIN] Engagement AUC: {auc:.3f}")

        os.makedirs(MODELS_DIR, exist_ok=True)
        with open(os.path.join(MODELS_DIR, "engagement_model.pkl"), "wb") as f:
            pickle.dump(model, f)
        with open(os.path.join(MODELS_DIR, "engagement_scaler.pkl"), "wb") as f:
            pickle.dump(scaler, f)

        print(f"[ML TRAIN] Engagement model saved (trained on {len(X_train)} profiles).")

    except ImportError:
        print("[ML TRAIN] scikit-learn not installed. Skipping engagement model training.")
    except Exception as e:
        print(f"[ML TRAIN] Engagement training failed: {e}")


def generate_parent_insights(state: dict, age_group: str) -> list[str]:
    """
    Generate human-readable, explainable insight strings for the parent dashboard.
    All insights are derived purely from behavioral data — no PII.
    """
    insights = []
    completed = state["total_stories_completed"]
    cr = state["completion_rate"]
    qa = state["question_accuracy"]
    freq = state["session_frequency_per_week"]
    preferred_themes = state.get("preferred_themes", [])
    atpw = state["avg_time_per_word_ms"]

    if completed == 0:
        insights.append("No stories completed yet — get started to unlock personalized recommendations!")
        return insights

    if cr >= 0.85:
        insights.append("Excellent focus! This reader completes almost every story they start.")
    elif cr >= 0.60:
        insights.append("Good engagement — most stories are finished. Consider slightly shorter stories to boost completion further.")
    else:
        insights.append("Some stories are abandoned early — this may mean the content is too long or complex. We are adjusting difficulty.")

    if preferred_themes:
        insights.append(f"Favourite topics so far: {', '.join(preferred_themes[:2])}.")

    if freq >= 5:
        insights.append("Reading almost every day — great habit forming!")
    elif freq >= 3:
        insights.append("Reading a few times per week — steady progress.")
    elif freq > 0:
        insights.append("Occasional sessions — even one story a week builds vocabulary and comprehension.")

    if len(state.get("preferred_themes", [])) > 0 and qa > 0:
        if qa >= 0.75:
            insights.append("Strong comprehension — question answers show good story understanding.")
        elif qa >= 0.50:
            insights.append("Comprehension is developing — interactive questions are helping.")
        else:
            insights.append("Comprehension questions are challenging right now — we're adjusting difficulty to build confidence.")

    if atpw > 0 and completed >= 3:
        wpm = 60_000 / atpw
        insights.append(f"Estimated reading pace: ~{int(wpm)} words per minute.")

    return insights
