"""
Base configuration loader for the Mergado Flask application.
Handles Flask app creation, logging setup, and blueprint registration.
"""
import logging
import os
import sys
from typing import Dict, Any

from flask import Flask
from app import db, migrate

from app.auth.oauth import auth_bp
from app.middleware.error_handlers import register_error_handlers
from app.middleware.logging import setup_logging
from app.middleware.rate_limit import init_rate_limiter
from settings import settings


def create_app(config_object: str = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config_object: Optional configuration object name

    Returns:
        Configured Flask application instance
    """
    template_dir = os.path.join(os.path.dirname(__file__), 'app', 'templates')
    app = Flask(__name__, template_folder=template_dir)

    # Load configuration
    _load_config(app, config_object)

    # Setup logging
    setup_logging(app)

    # Register blueprints
    _register_blueprints(app)

    # Register error handlers
    register_error_handlers(app)

    # Initialize database
    _init_database(app)
    
    # Initialize rate limiting
    init_rate_limiter(app)

    return app


def _load_config(app: Flask, config_object: str = None) -> None:
    """Load Flask configuration from settings and optional config object."""
    # Basic Flask configuration from settings
    app.config.update(
        SECRET_KEY=settings.flask_secret_key,
        DEBUG=settings.flask_debug,
        TESTING=getattr(settings, 'testing', False),
    )

    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = settings.database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Session configuration
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False

    # Load additional config if provided
    if config_object:
        app.config.from_object(config_object)


def _register_blueprints(app: Flask) -> None:
    """Register all application blueprints."""
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Import and register other blueprints here as they are created
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)
    
    from app.routes.import_routes import import_bp
    app.register_blueprint(import_bp)
    
    from app.routes.sync_routes import sync_bp
    app.register_blueprint(sync_bp)
    
    from app.routes.project_routes import project_bp
    app.register_blueprint(project_bp)


def _init_database(app: Flask) -> None:
    """Initialize database connection and create tables."""
    # Initialize SQLAlchemy
    db.init_app(app)
    
    # Initialize Flask-Migrate (Alembic)
    migrate.init_app(app, db)
    
    # Import models so they're registered with SQLAlchemy
    from app import models  # noqa: F401
