import datetime as dt
import os
from pathlib import Path

from flask import Flask

from . import db
from .auth import bp as auth_bp
from .routes.admin import bp as admin_bp
from .routes.dashboard import bp as dashboard_bp
from .routes.diets import bp as diets_bp
from .routes.goals import bp as goals_bp
from .routes.profile import bp as profile_bp
from .routes.stats import bp as stats_bp
from .routes.workouts import bp as workouts_bp


def create_app(config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FITAPP_SECRET_KEY", "dev-secret-change-me"),
        DATABASE=os.path.join(app.instance_path, "fitapp.db"),
    )
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(workouts_bp)
    app.register_blueprint(diets_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(stats_bp)

    with app.app_context():
        db.init_db()

    @app.context_processor
    def inject_year():
        return {"now_year": dt.date.today().year}

    return app
