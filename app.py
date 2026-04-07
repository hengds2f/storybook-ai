import os
from flask import Flask, render_template, redirect, url_for, session
from dotenv import load_dotenv
from services.storage import init_db

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "storybook-dev-secret-change-in-prod")
    app.config["SESSION_TYPE"] = "filesystem"
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

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(404)
    def not_found(e):
        return render_template("index.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return {"error": "Internal server error"}, 500

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
