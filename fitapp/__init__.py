import datetime as dt
import os
import secrets
from pathlib import Path

from flask import Flask, abort, request, session

from . import db
from .auth import bp as auth_bp
from .routes.admin import bp as admin_bp
from .routes.dashboard import bp as dashboard_bp
from .routes.diets import bp as diets_bp
from .routes.goals import bp as goals_bp
from .routes.library import bp as library_bp
from .routes.profile import bp as profile_bp
from .routes.stats import bp as stats_bp
from .routes.sports import bp as sports_bp
from .utils import format_duration


def create_app(config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FITAPP_SECRET_KEY") or secrets.token_urlsafe(48),
        DATABASE=os.path.join(app.instance_path, "fitapp.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FITAPP_COOKIE_SECURE", "0").lower()
        in {"1", "true", "yes"},
    )
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)

    app.jinja_env.filters["duration"] = format_duration

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(sports_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(diets_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(stats_bp)

    with app.app_context():
        db.init_db()

    @app.before_request
    def protect_state_changes():
        if app.testing:
            return None
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, description="The form security token is missing or invalid. Reload the page and try again.")

    @app.context_processor
    def inject_csrf_token():
        def csrf_token():
            token = session.get("csrf_token")
            if token is None:
                token = secrets.token_urlsafe(32)
                session["csrf_token"] = token
            return token

        return {"csrf_token": csrf_token}

    @app.context_processor
    def inject_year():
        return {"now_year": dt.date.today().year}

    return app
