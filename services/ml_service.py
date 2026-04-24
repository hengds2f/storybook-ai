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
