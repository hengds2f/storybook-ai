import os
from dotenv import load_dotenv

# Load environment variables at the absolute earliest point
load_dotenv()

from flask import Flask, render_template, session
from services.storage import init_db
from werkzeug.middleware.proxy_fix import ProxyFix

# StoryBook AI - v1.0.1 - Auth Synchronization Fix


def create_app():
    app = Flask(__name__)

    # Trust 1 level of proxy headers (HF Spaces runs behind nginx)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.secret_key = os.environ.get("SECRET_KEY", "storybook-dev-secret-change-in-prod")

    # Session cookie config — must work through HF Spaces HTTPS proxy
    # SameSite=None and Secure=True are REQUIRED for sessions to work in iframes
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 7  # 7 days
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    # Initialize SQLite database
    with app.app_context():
        init_db()

    # Register blueprints
    from routes.auth import auth_bp
    from routes.story import story_bp
    from routes.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(story_bp)
    app.register_blueprint(dashboard_bp)

    def get_session_user():
        """Return session user dict for template injection, or None."""
        if "user_id" in session:
            return {"user_id": session["user_id"], "username": session["username"]}
        return None

    @app.route("/")
    def index():
        return render_template("index.html", session_user=get_session_user())

    @app.errorhandler(404)
    def not_found(e):
        return render_template("index.html", session_user=get_session_user()), 404

    @app.errorhandler(500)
    def server_error(e):
        return {"error": "Internal server error"}, 500

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
