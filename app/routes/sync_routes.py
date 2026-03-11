"""
Sync routes - handles stock/price sync configuration and execution.
"""
import logging

from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest

from app import db
from app.auth.oauth import require_auth
from app.models.sync_config import SyncConfig, SyncType
from app.models.sync_log import SyncLog
from app.models.project import Project
from app.services import (
    MergadoClient,
    ShopifyService,
    StockSyncService,
    PriceSyncService,
)


logger = logging.getLogger(__name__)
sync_bp = Blueprint('sync', __name__, url_prefix='/api/sync')


@sync_bp.route('/config', methods=['GET'])
@require_auth
def get_sync_configs():
    """
    Get sync configurations.
    
    Query params:
        project_id: Filter by project (required)
    
    Returns:
        List of sync configs
    """
    project_id = request.args.get('project_id', type=int)
    
    if not project_id:
        raise BadRequest("project_id required")
    
    configs = SyncConfig.query.filter_by(project_id=project_id).all()
    
    return jsonify({
        'configs': [config.to_dict() for config in configs]
    })


@sync_bp.route('/config', methods=['POST'])
@require_auth
def create_or_update_sync_config():
    """
    Create or update sync configuration.
    
    Expects:
        {
            "project_id": 123,
            "sync_type": "stock" | "price",
            "enabled": true,
            "interval_minutes": 60
        }
    
    Returns:
        Created/updated config
    """
    data = request.get_json()
    project_id = data.get('project_id')
    sync_type = data.get('sync_type')
    enabled = data.get('enabled', False)
    interval_minutes = data.get('interval_minutes', 60)
    
    if not project_id or not sync_type:
        raise BadRequest("project_id and sync_type required")
    
    if sync_type not in [SyncType.STOCK.value, SyncType.PRICE.value]:
        raise BadRequest(f"Invalid sync_type: {sync_type}")
    
    # Verify project exists
    project = Project.query.get_or_404(project_id)
    
    # Check if config already exists
    config = SyncConfig.query.filter_by(
        project_id=project_id,
        sync_type=sync_type
    ).first()
    
    if config:
        # Update existing
        config.enabled = enabled
        config.interval_minutes = interval_minutes
        logger.info(f"Updated sync config {config.id}")
    else:
        # Create new
        config = SyncConfig(
            project_id=project_id,
            sync_type=sync_type,
            enabled=enabled,
            interval_minutes=interval_minutes
        )
        db.session.add(config)
        logger.info(f"Created sync config for project {project_id}, type {sync_type}")
    
    db.session.commit()
    
    return jsonify(config.to_dict())


@sync_bp.route('/config/<int:config_id>', methods=['DELETE'])
@require_auth
def delete_sync_config(config_id: int):
    """
    Delete sync configuration.
    
    Args:
        config_id: Sync config ID
        
    Returns:
        Success message
    """
    config = SyncConfig.query.get_or_404(config_id)
    db.session.delete(config)
    db.session.commit()
    
    logger.info(f"Deleted sync config {config_id}")
    
    return jsonify({'success': True, 'message': 'Config deleted'})


@sync_bp.route('/execute', methods=['POST'])
@require_auth
def execute_sync():
    """
    Execute sync immediately.
    
    Expects:
        {
            "config_id": 123
        }
    
    Returns:
        Sync result summary
    """
    data = request.get_json()
    config_id = data.get('config_id')
    
    if not config_id:
        raise BadRequest("config_id required")
    
    config = SyncConfig.query.get_or_404(config_id)
    project = config.project
    shop_id = project.shop.mergado_shop_id
    
    # Extract token from Authorization header
    auth_header = request.headers.get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
    
    if not access_token:
        raise BadRequest("Access token required")
    
    # Initialize services
    mergado_client = MergadoClient(access_token)
    shopify_service = ShopifyService(mergado_client, shop_id)
    
    try:
        # Execute appropriate sync
        if config.sync_type == SyncType.STOCK.value:
            sync_service = StockSyncService(mergado_client, shopify_service, config)
            result = sync_service.sync_stock()
        elif config.sync_type == SyncType.PRICE.value:
            sync_service = PriceSyncService(mergado_client, shopify_service, config)
            result = sync_service.sync_prices()
        else:
            raise BadRequest(f"Unknown sync type: {config.sync_type}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Sync execution failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@sync_bp.route('/logs', methods=['GET'])
@require_auth
def get_sync_logs():
    """
    Get sync execution logs.
    
    Query params:
        config_id: Filter by config ID (optional)
        project_id: Filter by project (optional)
        limit: Number of logs to return (default 50)
    
    Returns:
        List of sync logs
    """
    config_id = request.args.get('config_id', type=int)
    project_id = request.args.get('project_id', type=int)
    limit = request.args.get('limit', type=int, default=50)
    
    query = SyncLog.query
    
    if config_id:
        query = query.filter_by(sync_config_id=config_id)
    elif project_id:
        # Join through config to filter by project
        query = query.join(SyncConfig).filter(SyncConfig.project_id == project_id)
    
    logs = query.order_by(SyncLog.started_at.desc()).limit(limit).all()
    
    return jsonify({
        'logs': [log.to_dict() for log in logs]
    })
