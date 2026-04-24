"""
Event Tracker — StoryBook ML Module
====================================
Persists reading behavior events and maintains the profile_ml_state feature cache.

Design decisions:
- All writes go to reading_events (append-only source of truth).
- profile_ml_state is a derived cache recomputed from events; it can always be rebuilt.
- Feature recompute is triggered: (a) every RECOMPUTE_THRESHOLD events, or (b) on session_end.
- No PII is stored here — profile_id is a UUID, no child names.
"""

import json
import uuid
import sqlite3
from datetime import datetime, timezone, timedelta
from services.storage import get_db

# Recompute profile features after this many new events
RECOMPUTE_THRESHOLD = 10

# Valid event types accepted by the tracker
VALID_EVENT_TYPES = {
    "story_started",
    "story_completed",
    "story_abandoned",
    "act_viewed",
    "question_shown",
    "question_answered",
    "story_replayed",
    "session_ended",
}

# Required payload fields per event type (subset validation)
REQUIRED_PAYLOAD_FIELDS = {
    "story_started": ["word_count", "age_group"],
    "story_completed": ["time_spent_ms", "word_count"],
    "story_abandoned": ["time_spent_ms"],
    "act_viewed": ["act_number", "time_spent_ms"],
    "question_shown": ["act_number", "question_id"],
    "question_answered": ["question_id", "is_correct", "response_time_ms"],
    "story_replayed": [],
    "session_ended": [],
}


# ── Schema initialisation ─────────────────────────────────────────────────────

def init_ml_tables():
    """Create ML-specific tables if they don't exist. Called from init_db()."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reading_events (
            event_id   TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            story_id   TEXT,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload    TEXT NOT NULL DEFAULT '{}',
            client_ts  TEXT,
            server_ts  TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_re_profile ON reading_events(profile_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_re_story ON reading_events(story_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_re_session ON reading_events(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_re_ts ON reading_events(server_ts)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_re_type ON reading_events(event_type)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_ml_state (
            profile_id                TEXT PRIMARY KEY,
            reading_level_score       REAL DEFAULT 5.0,
            engagement_score          REAL DEFAULT 0.5,
            completion_rate           REAL DEFAULT 0.0,
            avg_time_per_word_ms      REAL DEFAULT 0.0,
            replay_rate               REAL DEFAULT 0.0,
            question_accuracy         REAL DEFAULT 0.0,
            preferred_themes          TEXT DEFAULT '[]',
            preferred_settings        TEXT DEFAULT '[]',
            session_frequency_per_week REAL DEFAULT 0.0,
            total_stories_started     INTEGER DEFAULT 0,
            total_stories_completed   INTEGER DEFAULT 0,
            total_events              INTEGER DEFAULT 0,
            model_version             TEXT DEFAULT 'rule_based',
            last_computed_at          TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS question_log (
            question_id     TEXT PRIMARY KEY,
            profile_id      TEXT NOT NULL,
            story_id        TEXT NOT NULL,
            act_number      INTEGER,
            question_text   TEXT,
            answer_options  TEXT DEFAULT '[]',
            correct_answer  TEXT,
            question_type   TEXT DEFAULT 'comprehension',
            generated_by    TEXT DEFAULT 'rule_based',
            created_at      TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ql_profile ON question_log(profile_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ql_story ON question_log(story_id)")

    conn.commit()
    conn.close()


# ── Event ingestion ───────────────────────────────────────────────────────────

def validate_event(event_type: str, payload: dict) -> tuple[bool, str]:
    """Validate event_type and required payload fields. Returns (ok, error_msg)."""
    if event_type not in VALID_EVENT_TYPES:
        return False, f"Unknown event_type '{event_type}'. Valid: {sorted(VALID_EVENT_TYPES)}"
    required = REQUIRED_PAYLOAD_FIELDS.get(event_type, [])
    missing = [f for f in required if f not in payload]
    if missing:
        return False, f"Missing payload fields for '{event_type}': {missing}"
    return True, ""


def record_event(
    profile_id: str,
    session_id: str,
    event_type: str,
    payload: dict,
    story_id: str = None,
    client_ts: str = None,
    event_id: str = None,
) -> dict:
    """
    Persist a single reading event.

    Returns a dict with event_id and whether feature recompute was triggered.
    Raises ValueError on validation failure.
    """
    ok, err = validate_event(event_type, payload)
    if not ok:
        raise ValueError(err)

    event_id = event_id or str(uuid.uuid4())
    server_ts = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO reading_events
                (event_id, profile_id, story_id, session_id, event_type, payload, client_ts, server_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                profile_id,
                story_id,
                session_id,
                event_type,
                json.dumps(payload),
                client_ts,
                server_ts,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Decide whether to recompute features
    features_refreshed = _maybe_recompute(profile_id, event_type)

    return {
        "event_id": event_id,
        "server_ts": server_ts,
        "features_refreshed": features_refreshed,
    }


def _maybe_recompute(profile_id: str, event_type: str) -> bool:
    """Trigger feature recompute if threshold reached or session ended."""
    if event_type == "session_ended":
        recompute_profile_features(profile_id)
        return True

    conn = get_db()
    row = conn.execute(
        "SELECT total_events FROM profile_ml_state WHERE profile_id = ?", (profile_id,)
    ).fetchone()
    prev_total = dict(row)["total_events"] if row else 0
    new_total = conn.execute(
        "SELECT COUNT(*) FROM reading_events WHERE profile_id = ?", (profile_id,)
    ).fetchone()[0]
    conn.close()

    if new_total - prev_total >= RECOMPUTE_THRESHOLD:
        recompute_profile_features(profile_id)
        return True
    return False


# ── Feature engineering ────────────────────────────────────────────────────────

def recompute_profile_features(profile_id: str) -> dict:
    """
    Recompute all derived features for a profile from raw reading_events.
    Upserts the result into profile_ml_state.
    Returns the computed feature dict.
    """
    conn = get_db()
    now = datetime.now(timezone.utc)
    window_30d = (now - timedelta(days=30)).isoformat()
    window_7d = (now - timedelta(days=7)).isoformat()

    # ── Completion stats (30-day rolling) ──────────────────────────────────
    started_row = conn.execute(
        "SELECT COUNT(*) FROM reading_events WHERE profile_id=? AND event_type='story_started' AND server_ts>=?",
        (profile_id, window_30d),
    ).fetchone()[0]
    completed_row = conn.execute(
        "SELECT COUNT(*) FROM reading_events WHERE profile_id=? AND event_type='story_completed' AND server_ts>=?",
        (profile_id, window_30d),
    ).fetchone()[0]
    total_started = max(conn.execute(
        "SELECT COUNT(*) FROM reading_events WHERE profile_id=? AND event_type='story_started'",
        (profile_id,),
    ).fetchone()[0], 0)
    total_completed = max(conn.execute(
        "SELECT COUNT(*) FROM reading_events WHERE profile_id=? AND event_type='story_completed'",
        (profile_id,),
    ).fetchone()[0], 0)
    completion_rate = completed_row / max(started_row, 1)

    # ── Average time per word (from completed stories) ─────────────────────
    completed_events = conn.execute(
        """SELECT payload FROM reading_events
           WHERE profile_id=? AND event_type='story_completed' AND server_ts>=?""",
        (profile_id, window_30d),
    ).fetchall()
    total_ms = 0.0
    total_words = 0
    for row in completed_events:
        p = json.loads(row[0])
        total_ms += p.get("time_spent_ms", 0)
        total_words += p.get("word_count", 1)
    avg_time_per_word_ms = total_ms / max(total_words, 1)

    # ── Replay rate ────────────────────────────────────────────────────────
    replay_count = conn.execute(
        "SELECT COUNT(*) FROM reading_events WHERE profile_id=? AND event_type='story_replayed' AND server_ts>=?",
        (profile_id, window_30d),
    ).fetchone()[0]
    replay_rate = replay_count / max(completed_row, 1)

    # ── Question accuracy ─────────────────────────────────────────────────
    qa_rows = conn.execute(
        """SELECT payload FROM reading_events
           WHERE profile_id=? AND event_type='question_answered'""",
        (profile_id,),
    ).fetchall()
    correct = sum(1 for r in qa_rows if json.loads(r[0]).get("is_correct") is True)
    question_accuracy = correct / max(len(qa_rows), 1)

    # ── Session frequency (last 7 days) ───────────────────────────────────
    session_count_7d = conn.execute(
        """SELECT COUNT(DISTINCT session_id) FROM reading_events
           WHERE profile_id=? AND server_ts>=?""",
        (profile_id, window_7d),
    ).fetchone()[0]
    session_frequency_per_week = float(session_count_7d)

    # ── Preferred themes (by completion rate) ──────────────────────────────
    theme_started: dict[str, int] = {}
    theme_completed: dict[str, int] = {}
    started_events = conn.execute(
        "SELECT payload FROM reading_events WHERE profile_id=? AND event_type='story_started'",
        (profile_id,),
    ).fetchall()
    for row in started_events:
        p = json.loads(row[0])
        t = p.get("theme", "unknown")
        theme_started[t] = theme_started.get(t, 0) + 1
    for row in completed_events:
        p = json.loads(row[0])
        t = p.get("theme", "unknown")
        theme_completed[t] = theme_completed.get(t, 0) + 1
    theme_rates = {
        t: theme_completed.get(t, 0) / max(theme_started.get(t, 1), 1)
        for t in theme_started
    }
    preferred_themes = sorted(theme_rates, key=theme_rates.get, reverse=True)[:3]

    # ── Preferred settings ────────────────────────────────────────────────
    setting_started: dict[str, int] = {}
    setting_completed: dict[str, int] = {}
    for row in started_events:
        p = json.loads(row[0])
        s = p.get("setting", "unknown")
        setting_started[s] = setting_started.get(s, 0) + 1
    for row in completed_events:
        p = json.loads(row[0])
        s = p.get("setting", "unknown")
        setting_completed[s] = setting_completed.get(s, 0) + 1
    setting_rates = {
        s: setting_completed.get(s, 0) / max(setting_started.get(s, 1), 1)
        for s in setting_started
    }
    preferred_settings = sorted(setting_rates, key=setting_rates.get, reverse=True)[:3]

    # ── Total event count ─────────────────────────────────────────────────
    total_events = conn.execute(
        "SELECT COUNT(*) FROM reading_events WHERE profile_id=?", (profile_id,)
    ).fetchone()[0]

    conn.close()

    features = {
        "profile_id": profile_id,
        "completion_rate": round(completion_rate, 4),
        "avg_time_per_word_ms": round(avg_time_per_word_ms, 2),
        "replay_rate": round(replay_rate, 4),
        "question_accuracy": round(question_accuracy, 4),
        "session_frequency_per_week": round(session_frequency_per_week, 2),
        "preferred_themes": json.dumps(preferred_themes),
        "preferred_settings": json.dumps(preferred_settings),
        "total_stories_started": total_started,
        "total_stories_completed": total_completed,
        "total_events": total_events,
        "last_computed_at": now.isoformat(),
    }

    _upsert_ml_state(features)
    return features


def _upsert_ml_state(features: dict):
    """Upsert a row into profile_ml_state with updated feature values."""
    conn = get_db()
    conn.execute(
        """
        INSERT INTO profile_ml_state
            (profile_id, completion_rate, avg_time_per_word_ms, replay_rate,
             question_accuracy, session_frequency_per_week, preferred_themes,
             preferred_settings, total_stories_started, total_stories_completed,
             total_events, last_computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_id) DO UPDATE SET
            completion_rate           = excluded.completion_rate,
            avg_time_per_word_ms      = excluded.avg_time_per_word_ms,
            replay_rate               = excluded.replay_rate,
            question_accuracy         = excluded.question_accuracy,
            session_frequency_per_week= excluded.session_frequency_per_week,
            preferred_themes          = excluded.preferred_themes,
            preferred_settings        = excluded.preferred_settings,
            total_stories_started     = excluded.total_stories_started,
            total_stories_completed   = excluded.total_stories_completed,
            total_events              = excluded.total_events,
            last_computed_at          = excluded.last_computed_at
        """,
        (
            features["profile_id"],
            features["completion_rate"],
            features["avg_time_per_word_ms"],
            features["replay_rate"],
            features["question_accuracy"],
            features["session_frequency_per_week"],
            features["preferred_themes"],
            features["preferred_settings"],
            features["total_stories_started"],
            features["total_stories_completed"],
            features["total_events"],
            features["last_computed_at"],
        ),
    )
    conn.commit()
    conn.close()


def get_ml_state(profile_id: str) -> dict | None:
    """Fetch the current ML feature state for a profile, or None if no data yet."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM profile_ml_state WHERE profile_id = ?", (profile_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    state = dict(row)
    state["preferred_themes"] = json.loads(state.get("preferred_themes") or "[]")
    state["preferred_settings"] = json.loads(state.get("preferred_settings") or "[]")
    return state


def get_recent_story_params(profile_id: str, n: int = 3) -> list[dict]:
    """
    Return the last N story_started event payloads for a profile.
    Used to enforce theme/setting diversity in recommendations.
    """
    conn = get_db()
    rows = conn.execute(
        """SELECT payload FROM reading_events
           WHERE profile_id=? AND event_type='story_started'
           ORDER BY server_ts DESC LIMIT ?""",
        (profile_id, n),
    ).fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]


def save_question(question: dict) -> str:
    """Persist a generated question to question_log. Returns question_id."""
    question_id = question.get("question_id") or str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        """
        INSERT OR IGNORE INTO question_log
            (question_id, profile_id, story_id, act_number, question_text,
             answer_options, correct_answer, question_type, generated_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            question["profile_id"],
            question["story_id"],
            question.get("act_number"),
            question.get("question_text"),
            json.dumps(question.get("options", [])),
            question.get("correct_answer"),
            question.get("question_type", "comprehension"),
            question.get("generated_by", "rule_based"),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return question_id


def get_question(question_id: str) -> dict | None:
    """Fetch a question by ID."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM question_log WHERE question_id = ?", (question_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    q = dict(row)
    q["answer_options"] = json.loads(q.get("answer_options") or "[]")
    return q
