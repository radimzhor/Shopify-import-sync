"""
Main entrypoint for the Mergado Flask application.
Handles application startup, development server, and production deployment.
"""
import os
import sys

from config import create_app
from settings import settings

# Create Flask application instance for gunicorn
app = create_app()


def main() -> None:
    """Main application entrypoint."""
    try:
        # Run development server if not in production
        if settings.flask_env == "development":
            print(f"Starting development server on {settings.host}:{settings.port}")
            app.run(
                host=settings.host,
                port=settings.port,
                debug=settings.flask_debug,
                use_reloader=True,
            )
        else:
            # In production, gunicorn will handle the server
            print("Application created for production deployment")

    except Exception as e:
        print(f"Failed to start application: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
