"""
ML API Routes — StoryBook Personalization Module
=================================================
Blueprint: /api/ml/

Endpoints:
  POST /api/ml/event                          Track a reading event
  GET  /api/ml/recommend/<profile_id>         Get story parameter recommendations
  GET  /api/ml/profile/<profile_id>/stats     Parent-facing reading stats
  POST /api/ml/questions/generate             Generate an interactive question
  POST /api/ml/questions/<question_id>/answer Record a child's answer
  GET  /api/ml/profile/<profile_id>/export    Export all ML data for a profile (COPPA)
"""

import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

from routes.auth import login_required
from services.event_tracker import (
    get_ml_state,
    get_question,
    recompute_profile_features,
    record_event,
    save_question,
)
from services.ml_service import (
    advise_question_timing,
    estimate_reading_level,
    generate_parent_insights,
    generate_question,
    predict_engagement,
    recommend_story_params,
)
from services.storage import get_profile_by_id

ml_bp = Blueprint("ml", __name__)


# ── Guard: profile must belong to the authenticated user ─────────────────────

def _get_profile_or_403(profile_id: str):
    """
    Fetch the profile and verify it belongs to the current session user.
    Returns (profile_dict, None) on success or (None, error_response) on failure.
    """
    profile = get_profile_by_id(profile_id)
    if not profile:
        return None, (jsonify({"error": "Profile not found"}), 404)
    if profile["user_id"] != session.get("user_id"):
        return None, (jsonify({"error": "Forbidden"}), 403)
    return profile, None


# ── POST /api/ml/event ────────────────────────────────────────────────────────

@ml_bp.route("/api/ml/event", methods=["POST"])
@login_required
def track_event():
    """
    Record a reading behavior event.

    Request body:
      {
        "profile_id":  string (required),
        "session_id":  string (required),
        "event_type":  string (required),
        "story_id":    string (optional),
        "payload":     object (required, schema varies by event_type),
        "client_ts":   string ISO-8601 (optional)
      }
    """
    data = request.get_json(silent=True) or {}

    profile_id = (data.get("profile_id") or "").strip()
    session_id = (data.get("session_id") or "").strip()
    event_type = (data.get("event_type") or "").strip()
    story_id = (data.get("story_id") or "").strip() or None
    payload = data.get("payload", {})
    client_ts = data.get("client_ts")

    if not profile_id or not session_id or not event_type:
        return jsonify({"error": "profile_id, session_id, and event_type are required"}), 400

    if not isinstance(payload, dict):
        return jsonify({"error": "'payload' must be a JSON object"}), 400

    profile, err = _get_profile_or_403(profile_id)
    if err:
        return err

    try:
        result = record_event(
            profile_id=profile_id,
            session_id=session_id,
            event_type=event_type,
            payload=payload,
            story_id=story_id,
            client_ts=client_ts,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "recorded": True,
        "event_id": result["event_id"],
        "server_ts": result["server_ts"],
        "features_refreshed": result["features_refreshed"],
    }), 201


# ── GET /api/ml/recommend/<profile_id> ───────────────────────────────────────

@ml_bp.route("/api/ml/recommend/<profile_id>", methods=["GET"])
@login_required
def get_recommendation(profile_id: str):
    """
    Return personalized story parameter recommendations for the next story.

    Response: {
      profile_id, recommendation, reading_level, engagement,
      cold_start, model_tier, confidence, generated_at
    }
    """
    profile, err = _get_profile_or_403(profile_id)
    if err:
        return err

    age_group = profile["age_group"]

    reading = estimate_reading_level(profile_id, age_group)
    engagement = predict_engagement(profile_id, age_group)
    params = recommend_story_params(profile_id, age_group)

    return jsonify({
        "profile_id": profile_id,
        "recommendation": {
            "age_group": params["age_group"],
            "theme": params["theme"],
            "setting": params["setting"],
            "complexity_hint": params["complexity_hint"],
            "vocabulary_hint": params["vocabulary_hint"],
        },
        "reading_level": {
            "score": reading["score"],
            "label": reading["label"],
        },
        "engagement": {
            "score": engagement["score"],
            "label": engagement["label"],
        },
        "cold_start": params["cold_start"],
        "model_tier": params["model_tier"],
        "confidence": params["confidence"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }), 200


# ── GET /api/ml/profile/<profile_id>/stats ────────────────────────────────────

@ml_bp.route("/api/ml/profile/<profile_id>/stats", methods=["GET"])
@login_required
def profile_stats(profile_id: str):
    """
    Return ML-derived stats and insights for the parent dashboard.
    All values are derived from behavioral signals — no PII exposed.
    """
    profile, err = _get_profile_or_403(profile_id)
    if err:
        return err

    age_group = profile["age_group"]

    # Force feature recompute if explicitly requested
    if request.args.get("refresh") == "1":
        recompute_profile_features(profile_id)

    state = get_ml_state(profile_id)
    reading = estimate_reading_level(profile_id, age_group)
    engagement = predict_engagement(profile_id, age_group)

    if state is None:
        # Cold-start — return defaults
        return jsonify({
            "profile_id": profile_id,
            "reading_level_score": reading["score"],
            "reading_level_label": reading["label"],
            "engagement_score": engagement["score"],
            "engagement_label": engagement["label"],
            "completion_rate": 0.0,
            "avg_reading_time_minutes": 0.0,
            "total_stories_completed": 0,
            "preferred_themes": [],
            "preferred_settings": [],
            "question_accuracy": 0.0,
            "session_frequency_per_week": 0.0,
            "last_computed_at": None,
            "insights": ["No stories read yet — start reading to unlock personalized stats!"],
        }), 200

    avg_wpm = state["avg_time_per_word_ms"]
    # Estimate average story reading time: assume avg story is 300 words
    avg_reading_time_minutes = round((avg_wpm * 300) / 60_000, 1) if avg_wpm > 0 else 0.0

    insights = generate_parent_insights(state, age_group)

    return jsonify({
        "profile_id": profile_id,
        "reading_level_score": reading["score"],
        "reading_level_label": reading["label"],
        "engagement_score": engagement["score"],
        "engagement_label": engagement["label"],
        "completion_rate": state["completion_rate"],
        "avg_reading_time_minutes": avg_reading_time_minutes,
        "total_stories_completed": state["total_stories_completed"],
        "preferred_themes": state["preferred_themes"],
        "preferred_settings": state["preferred_settings"],
        "question_accuracy": state["question_accuracy"],
        "session_frequency_per_week": state["session_frequency_per_week"],
        "last_computed_at": state["last_computed_at"],
        "insights": insights,
    }), 200


# ── POST /api/ml/questions/generate ──────────────────────────────────────────

@ml_bp.route("/api/ml/questions/generate", methods=["POST"])
@login_required
def generate_question_endpoint():
    """
    Generate an interactive comprehension/prediction/reflection question for a story act.

    Request body:
      {
        "profile_id":    string (required),
        "story_id":      string (required),
        "act_number":    int 1–8 (required),
        "act_text":      string (required, story act content),
        "question_type": string (optional, default: auto from act_number)
      }
    """
    data = request.get_json(silent=True) or {}

    profile_id = (data.get("profile_id") or "").strip()
    story_id = (data.get("story_id") or "").strip()
    act_number = data.get("act_number")
    act_text = (data.get("act_text") or "").strip()

    if not profile_id or not story_id or not act_text:
        return jsonify({"error": "profile_id, story_id, and act_text are required"}), 400

    try:
        act_number = int(act_number)
        if not (1 <= act_number <= 8):
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "act_number must be an integer between 1 and 8"}), 400

    profile, err = _get_profile_or_403(profile_id)
    if err:
        return err

    age_group = profile["age_group"]

    # Auto-detect question type from act number if not supplied
    from services.ml_service import QUESTION_ACT_TRIGGERS
    default_type = QUESTION_ACT_TRIGGERS.get(act_number, "comprehension")
    question_type = (data.get("question_type") or default_type).strip()

    # Advise timing
    state = get_ml_state(profile_id)
    avg_tpw = state["avg_time_per_word_ms"] if state else 0.0
    timing = advise_question_timing(act_number, avg_tpw)

    question = generate_question(
        profile_id=profile_id,
        story_id=story_id,
        act_number=act_number,
        act_text=act_text,
        age_group=age_group,
        question_type=question_type,
        use_llm=True,
    )

    return jsonify({
        "question_id": question["question_id"],
        "question_text": question["question_text"],
        "question_type": question["question_type"],
        "options": question.get("options", []),
        "generated_by": question.get("generated_by", "rule_based"),
        "timing_recommendation": timing,
    }), 201


# ── GET /api/ml/questions/<question_id> ──────────────────────────────────────

@ml_bp.route("/api/ml/questions/<question_id>", methods=["GET"])
@login_required
def fetch_question_by_id(question_id: str):
    """
    Fetch a question for display in the story reader.
    The correct answer is intentionally omitted — it is only returned after
    the child submits their answer via POST .../answer.
    """
    q = get_question(question_id)
    if not q:
        return jsonify({"error": "Question not found"}), 404
    return jsonify({
        "question_id":   q["question_id"],
        "question_text": q["question_text"],
        "question_type": q.get("question_type", "comprehension"),
        "options":       q.get("answer_options", []),
        "act_number":    q.get("act_number"),
    }), 200


# ── POST /api/ml/questions/<question_id>/answer ───────────────────────────────

@ml_bp.route("/api/ml/questions/<question_id>/answer", methods=["POST"])
@login_required
def record_answer(question_id: str):
    """
    Record a child's answer to an interactive question and return feedback.

    Request body:
      {
        "profile_id":       string (required),
        "session_id":       string (required),
        "answer":           string (required, e.g. "A"),
        "response_time_ms": int (required)
      }
    """
    data = request.get_json(silent=True) or {}

    profile_id = (data.get("profile_id") or "").strip()
    session_id = (data.get("session_id") or "").strip()
    answer = (data.get("answer") or "").strip()
    response_time_ms = data.get("response_time_ms", 0)

    if not profile_id or not session_id or not answer:
        return jsonify({"error": "profile_id, session_id, and answer are required"}), 400

    try:
        response_time_ms = int(response_time_ms)
    except (TypeError, ValueError):
        response_time_ms = 0

    profile, err = _get_profile_or_403(profile_id)
    if err:
        return err

    question = get_question(question_id)
    if not question:
        return jsonify({"error": "Question not found"}), 404

    is_correct = answer.strip().upper() == (question.get("correct_answer") or "").strip().upper()

    # Record the answer as a reading event
    try:
        record_event(
            profile_id=profile_id,
            session_id=session_id,
            event_type="question_answered",
            payload={
                "question_id": question_id,
                "is_correct": is_correct,
                "response_time_ms": response_time_ms,
            },
            story_id=question.get("story_id"),
        )
    except ValueError:
        pass  # Non-critical — answer recorded even if event tracking fails

    # Age-appropriate feedback
    age_group = profile.get("age_group", "6-8")
    if is_correct:
        feedback = _correct_feedback(age_group)
    else:
        feedback = _incorrect_feedback(age_group)

    return jsonify({
        "is_correct": is_correct,
        "feedback": feedback,
        "correct_answer": question.get("correct_answer", ""),
    }), 200


# ── GET /api/ml/profile/<profile_id>/export ──────────────────────────────────

@ml_bp.route("/api/ml/profile/<profile_id>/export", methods=["GET"])
@login_required
def export_ml_data(profile_id: str):
    """
    Export all ML data for a profile as JSON (COPPA data portability).
    Returns reading_events and profile_ml_state for the profile.
    """
    from services.storage import get_db

    profile, err = _get_profile_or_403(profile_id)
    if err:
        return err

    conn = get_db()
    events = conn.execute(
        "SELECT * FROM reading_events WHERE profile_id = ? ORDER BY server_ts",
        (profile_id,),
    ).fetchall()
    state_row = conn.execute(
        "SELECT * FROM profile_ml_state WHERE profile_id = ?", (profile_id,)
    ).fetchone()
    questions = conn.execute(
        "SELECT * FROM question_log WHERE profile_id = ? ORDER BY created_at",
        (profile_id,),
    ).fetchall()
    conn.close()

    return jsonify({
        "profile_id": profile_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "reading_events": [dict(r) for r in events],
        "profile_ml_state": dict(state_row) if state_row else None,
        "question_log": [dict(q) for q in questions],
    }), 200


# ── POST /api/ml/questions/timing ─────────────────────────────────────────────

@ml_bp.route("/api/ml/questions/timing", methods=["POST"])
@login_required
def question_timing():
    """
    Advise whether to show a question after a given act.

    Request body:
      {
        "profile_id": string (required),
        "act_number": int (required)
      }
    """
    data = request.get_json(silent=True) or {}
    profile_id = (data.get("profile_id") or "").strip()

    try:
        act_number = int(data.get("act_number", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "act_number must be an integer"}), 400

    profile, err = _get_profile_or_403(profile_id)
    if err:
        return err

    state = get_ml_state(profile_id)
    avg_tpw = state["avg_time_per_word_ms"] if state else 0.0
    timing = advise_question_timing(act_number, avg_tpw)

    return jsonify(timing), 200


# ── Feedback helpers ──────────────────────────────────────────────────────────

_CORRECT_FEEDBACK = {
    "3-5": ["Great job! You got it! ⭐", "Wow, you're so smart!", "That's exactly right! 🌟"],
    "6-8": ["Correct! Well done!", "Spot on! You really paid attention!", "That's right! Great thinking!"],
    "9-12": ["Correct! Excellent comprehension.", "Well reasoned — that's the right answer.", "Precisely! Great insight."],
}

_INCORRECT_FEEDBACK = {
    "3-5": ["Good try! The answer was", "Almost! Let's look again —", "Nice try! Here's the answer:"],
    "6-8": ["Not quite, but good try! The answer was", "Almost there! The correct answer is", "Keep trying! The answer was"],
    "9-12": ["Close, but not quite. The answer is", "Good attempt. The correct answer is", "Not quite — the answer is"],
}


def _correct_feedback(age_group: str) -> str:
    import random
    options = _CORRECT_FEEDBACK.get(age_group, _CORRECT_FEEDBACK["6-8"])
    return random.choice(options)


def _incorrect_feedback(age_group: str) -> str:
    import random
    options = _INCORRECT_FEEDBACK.get(age_group, _INCORRECT_FEEDBACK["6-8"])
    return random.choice(options)
