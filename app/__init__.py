"""
Mergado App - Core application package.

This package contains the main Flask application components including
authentication, routes, services, and middleware.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

__version__ = "0.1.0"

# Initialize extensions (will be bound to app in config.py)
db = SQLAlchemy()
migrate = Migrate()
