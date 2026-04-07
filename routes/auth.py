from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
import bcrypt
from services.storage import (
    create_user, get_user_by_username, get_user_by_id,
    create_profile, get_profiles_for_user, get_profile_by_id, delete_profile
)

auth_bp = Blueprint("auth", __name__)


def login_required(f):
    """Decorator: redirect to login if not authenticated."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


# ── Auth routes ───────────────────────────────────────────────────────────────

@auth_bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = create_user(username, password_hash)

    if not user:
        return jsonify({"error": "Username already exists"}), 409

    session.permanent = True          # honour PERMANENT_SESSION_LIFETIME
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"success": True, "user_id": user["id"], "username": user["username"]}), 201


@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    user = get_user_by_username(username)
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Invalid username or password"}), 401

    session.permanent = True          # honour PERMANENT_SESSION_LIFETIME
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"success": True, "user_id": user["id"], "username": user["username"]}), 200


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True}), 200


@auth_bp.route("/api/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({"authenticated": False}), 200
    return jsonify({
        "authenticated": True,
        "user_id": session["user_id"],
        "username": session["username"]
    }), 200


# ── Profile routes ────────────────────────────────────────────────────────────

@auth_bp.route("/api/profiles", methods=["GET"])
def list_profiles():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    profiles = get_profiles_for_user(session["user_id"])
    return jsonify({"profiles": profiles}), 200


@auth_bp.route("/api/profiles", methods=["POST"])
def create_profile_route():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json()
    name = data.get("name", "").strip()
    age_group = data.get("age_group", "6-8")
    avatar_color = data.get("avatar_color", "#6366f1")

    if not name:
        return jsonify({"error": "Profile name is required"}), 400
    if age_group not in ["3-5", "6-8", "9-12"]:
        return jsonify({"error": "Invalid age group"}), 400

    profile = create_profile(session["user_id"], name, age_group, avatar_color)
    return jsonify({"profile": profile}), 201


@auth_bp.route("/api/profiles/<profile_id>", methods=["DELETE"])
def delete_profile_route(profile_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    success = delete_profile(profile_id, session["user_id"])
    if not success:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify({"success": True}), 200


@auth_bp.route("/api/profiles/<profile_id>", methods=["GET"])
def get_profile_route(profile_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    profile = get_profile_by_id(profile_id)
    if not profile or profile["user_id"] != session["user_id"]:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify({"profile": profile}), 200


# ── Page routes ───────────────────────────────────────────────────────────────

def _session_user():
    """Return current user dict from Flask session for template injection."""
    if "user_id" in session:
        return {"user_id": session["user_id"], "username": session["username"]}
    return None


@auth_bp.route("/app")
def app_page():
    return render_template("builder.html", session_user=_session_user())


@auth_bp.route("/library")
def library_page():
    return render_template("library.html", session_user=_session_user())


@auth_bp.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html", session_user=_session_user())
