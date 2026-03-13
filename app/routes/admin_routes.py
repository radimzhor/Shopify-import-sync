"""
Admin routes for debugging and maintenance tasks.
"""
import logging
from flask import Blueprint, jsonify
from flask_migrate import current, upgrade
from app import db

logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/db-status', methods=['GET'])
def db_status():
    """
    Check database and Alembic migration status.
    Returns current revision, pending migrations, and column existence.
    """
    try:
        # Check current Alembic revision
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import inspect, text
        
        # Get Alembic config
        from flask import current_app
        alembic_cfg = Config()
        alembic_cfg.set_main_option('script_location', 'migrations')
        
        # Get current revision from database
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            current_revision = result[0] if result else None
        
        # Get latest revision from scripts
        script = ScriptDirectory.from_config(alembic_cfg)
        head_revision = script.get_current_head()
        
        # Check if projects table has shopify_writeback_rule_id column
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('projects')]
        has_writeback_column = 'shopify_writeback_rule_id' in columns
        
        return jsonify({
            'status': 'ok',
            'current_revision': current_revision,
            'head_revision': head_revision,
            'up_to_date': current_revision == head_revision,
            'projects_columns': columns,
            'has_shopify_writeback_rule_id': has_writeback_column
        })
        
    except Exception as e:
        logger.error(f"Failed to check DB status: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@admin_bp.route('/run-migrations', methods=['POST'])
def run_migrations():
    """
    Manually run pending database migrations.
    USE WITH CAUTION - only for debugging migration issues.
    """
    try:
        from flask_migrate import upgrade as flask_migrate_upgrade
        from flask import current_app
        import os
        
        # Get migrations directory
        migrations_dir = os.path.join(current_app.root_path, '..', 'migrations')
        
        logger.info(f"Running migrations from {migrations_dir}")
        
        # Run upgrade
        flask_migrate_upgrade(directory=migrations_dir)
        
        logger.info("Migrations completed successfully")
        
        return jsonify({
            'status': 'success',
            'message': 'Migrations applied successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


@admin_bp.route('/add-column-directly', methods=['POST'])
def add_column_directly():
    """
    Emergency fix: directly add the missing column using raw SQL.
    This bypasses Alembic and should only be used if migrations are failing.
    """
    try:
        from sqlalchemy import text
        
        with db.engine.connect() as conn:
            # Use IF NOT EXISTS so it's idempotent
            conn.execute(text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS shopify_writeback_rule_id VARCHAR(50)"
            ))
            conn.commit()
        
        logger.info("Successfully added shopify_writeback_rule_id column")
        
        return jsonify({
            'status': 'success',
            'message': 'Column added successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to add column: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
