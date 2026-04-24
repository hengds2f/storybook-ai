import sqlite3
import os
import json
import uuid
from datetime import datetime

DB_PATH = os.path.join("data", "storybook.db")


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    os.makedirs("data", exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # Users (parents)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Child profiles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            age_group TEXT NOT NULL,
            avatar_color TEXT DEFAULT '#6366f1',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Stories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            parameters TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES profiles(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Story Generation Tasks (for Background processing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS story_tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_pct INTEGER DEFAULT 0,
            status_message TEXT,
            result_story_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (profile_id) REFERENCES profiles(id)
        )
    """)

    conn.commit()
    conn.close()

    # ML tables (reading_events, profile_ml_state, question_log)
    from services.event_tracker import init_ml_tables
    init_ml_tables()


# ── User functions ──────────────────────────────────────────────────────────

def create_user(username: str, password_hash: str) -> dict:
    conn = get_db()
    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": password_hash,
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user["id"], user["username"], user["password_hash"], user["created_at"])
        )
        conn.commit()
        return user
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Profile functions ────────────────────────────────────────────────────────

def create_profile(user_id: str, name: str, age_group: str, avatar_color: str = "#6366f1") -> dict:
    conn = get_db()
    profile = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": name,
        "age_group": age_group,
        "avatar_color": avatar_color,
        "created_at": datetime.utcnow().isoformat()
    }
    conn.execute(
        "INSERT INTO profiles (id, user_id, name, age_group, avatar_color, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (profile["id"], profile["user_id"], profile["name"],
         profile["age_group"], profile["avatar_color"], profile["created_at"])
    )
    conn.commit()
    conn.close()
    return profile


def get_profiles_for_user(user_id: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM profiles WHERE user_id = ? ORDER BY created_at ASC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_profile_by_id(profile_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_profile(profile_id: str, user_id: str) -> bool:
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM profiles WHERE id = ? AND user_id = ?", (profile_id, user_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Story functions ──────────────────────────────────────────────────────────

def save_story(profile_id: str, user_id: str, title: str, parameters: dict, content: dict) -> dict:
    conn = get_db()
    story = {
        "id": str(uuid.uuid4()),
        "profile_id": profile_id,
        "user_id": user_id,
        "title": title,
        "parameters": json.dumps(parameters),
        "content": json.dumps(content),
        "created_at": datetime.utcnow().isoformat()
    }
    conn.execute(
        "INSERT INTO stories (id, profile_id, user_id, title, parameters, content, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (story["id"], story["profile_id"], story["user_id"],
         story["title"], story["parameters"], story["content"], story["created_at"])
    )
    conn.commit()
    conn.close()
    return story


def get_stories_for_profile(profile_id: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM stories WHERE profile_id = ? ORDER BY created_at DESC", (profile_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        s = dict(r)
        s["parameters"] = json.loads(s["parameters"])
        s["content"] = json.loads(s["content"])
        result.append(s)
    return result


def get_stories_for_user(user_id: str) -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT s.*, p.name as profile_name, p.age_group, p.avatar_color
           FROM stories s JOIN profiles p ON s.profile_id = p.id
           WHERE s.user_id = ? ORDER BY s.created_at DESC""",
        (user_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        s = dict(r)
        s["parameters"] = json.loads(s["parameters"])
        s["content"] = json.loads(s["content"])
        result.append(s)
    return result


def get_story_by_id(story_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        """SELECT s.*, p.name as profile_name, p.age_group, p.avatar_color
           FROM stories s JOIN profiles p ON s.profile_id = p.id
           WHERE s.id = ?""",
        (story_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    s = dict(row)
    s["parameters"] = json.loads(s["parameters"])
    s["content"] = json.loads(s["content"])
    return s


def delete_story(story_id: str, user_id: str) -> bool:
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM stories WHERE id = ? AND user_id = ?", (story_id, user_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Story Tasks (Background) ──────────────────────────────────────────────

def create_story_task(user_id: str, profile_id: str, params: dict) -> dict:
    conn = get_db()
    task = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "profile_id": profile_id,
        "params": json.dumps(params),
        "status": "pending",
        "progress_pct": 0,
        "status_message": "Initializing...",
        "created_at": datetime.utcnow().isoformat()
    }
    conn.execute(
        "INSERT INTO story_tasks (id, user_id, profile_id, params, status, progress_pct, status_message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (task["id"], task["user_id"], task["profile_id"],
         task["params"], task["status"], task["progress_pct"], task["status_message"], task["created_at"])
    )
    conn.commit()
    conn.close()
    return task


def update_story_task(task_id: str, **kwargs) -> bool:
    if not kwargs:
        return False
    conn = get_db()
    fields = []
    values = []
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        values.append(v)
    values.append(task_id)
    
    query = f"UPDATE story_tasks SET {', '.join(fields)} WHERE id = ?"
    cursor = conn.execute(query, tuple(values))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_story_task(task_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM story_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if not row:
        return None
    t = dict(row)
    t["params"] = json.loads(t["params"])
    return t


def get_stats_for_user(user_id: str) -> dict:
    conn = get_db()
    total_stories = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    profile_count = conn.execute(
        "SELECT COUNT(*) FROM profiles WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return {"total_stories": total_stories, "profile_count": profile_count}
