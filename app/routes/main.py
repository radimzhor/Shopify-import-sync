"""
Main routes for the Mergado Flask application.

Contains the primary web routes including index, dashboard, and protected routes.
"""
from flask import Blueprint, render_template, redirect, url_for, request, current_app

main_bp = Blueprint('routes', __name__)


@main_bp.route('/')
def index():
    """Home page with login/logout options."""
    try:
        return render_template(
            'index.html',
            settings={'flask_env': 'production'}  # Basic settings for template
        )
    except Exception as e:
        # If templates are missing (e.g. wrong path on host), avoid 404 and log
        current_app.logger.exception("Index template failed")
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Mergado</title></head>'
            '<body><p>Loading…</p><script>window.location.href="/auth/login" + window.location.search;</script></body></html>',
            200,
            {'Content-Type': 'text/html; charset=utf-8'},
        )


@main_bp.route('/dashboard')
def dashboard():
    """Dashboard page - authentication handled via JavaScript."""
    return render_template('dashboard.html')


@main_bp.route('/projects')
def projects():
    """Project selection page - authentication handled via JavaScript."""
    return render_template('projects.html')


@main_bp.route('/import')
def import_wizard():
    """Import wizard page - authentication handled via JavaScript."""
    return render_template('import_wizard.html')


@main_bp.route('/import/logs')
def import_logs():
    """Import logs history page - authentication handled via JavaScript."""
    return render_template('import_logs.html')


@main_bp.route('/sync')
def sync_config():
    """Sync configuration page - authentication handled via JavaScript."""
    return render_template('sync_config.html')


@main_bp.route('/profile')
def profile():
    """User profile page - authentication handled via JavaScript."""
    return render_template('profile.html')


@main_bp.route('/health')
def health():
    """
    Health check endpoint for monitoring.
    
    Checks database connectivity and returns service status.
    """
    from app import db
    import sys
    
    health_status = {
        'status': 'healthy',
        'service': 'mergado-shopify-import-sync',
        'version': '0.1.0',
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'checks': {}
    }
    
    # Check database connectivity
    try:
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        health_status['checks']['database'] = 'healthy'
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['checks']['database'] = f'unhealthy: {str(e)}'
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return health_status, status_code


@main_bp.route('/debug')
def debug():
    """Debug endpoint showing application configuration (development only)."""
    from settings import settings

    if not settings.flask_debug:
        return {'error': 'Debug endpoint only available in development'}, 403

    return {
        'settings': {
            'flask_env': settings.flask_env,
            'log_level': settings.log_level,
            'host': settings.host,
            'port': settings.port,
        },
        'config': dict(request.headers),
    }
