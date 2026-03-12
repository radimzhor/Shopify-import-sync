"""
Project routes - handles project selection and configuration.
"""
import logging

from flask import Blueprint, request, jsonify, render_template
from werkzeug.exceptions import BadRequest

from app import db
from app.auth.oauth import require_auth
from app.models.shop import Shop
from app.models.project import Project
from app.services import MergadoClient


logger = logging.getLogger(__name__)
project_bp = Blueprint('project', __name__, url_prefix='/api/project')


@project_bp.route('/shops', methods=['GET'])
@require_auth
def get_shops():
    """
    Get user's Mergado shops.
    
    Returns:
        List of shops from Mergado API
    """
    # Extract token from Authorization header
    auth_header = request.headers.get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
    
    if not access_token:
        raise BadRequest("Access token required")
    
    mergado_client = MergadoClient(access_token)
    
    try:
        # For MVP, we'll fetch shop info from the first shop the user has access to
        # In production, there should be an endpoint to list all user shops
        # For now, user needs to provide shop_id, or we can get it from a profile endpoint
        
        # Return shops from database for now
        shops = Shop.query.all()
        return jsonify({
            'shops': [shop.to_dict() for shop in shops]
        })
        
    except Exception as e:
        logger.error(f"Failed to fetch shops: {e}")
        return jsonify({'error': str(e)}), 500


@project_bp.route('/shops/<shop_id>/projects', methods=['GET'])
@require_auth
def get_shop_projects(shop_id: str):
    """
    Get projects for a specific shop.
    
    Args:
        shop_id: Mergado shop ID
        
    Returns:
        List of projects
    """
    # Extract token from Authorization header
    auth_header = request.headers.get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
    
    if not access_token:
        raise BadRequest("Access token required")
    
    mergado_client = MergadoClient(access_token)
    
    try:
        # Fetch projects from Mergado API
        projects = mergado_client.get_projects(shop_id)
        
        # Get or create shop first
        shop = Shop.query.filter_by(mergado_shop_id=shop_id).first()
        if not shop:
            # Create shop
            shop = Shop(
                mergado_shop_id=shop_id,
                name=f"Shop {shop_id}",  # Will be updated when we fetch shop details
                shopify_connected=True  # Assume true for now
            )
            db.session.add(shop)
            db.session.flush()
        
        # Sync with database - fetch full details for each project
        for api_project in projects:
            project_id = str(api_project['id'])
            
            # Fetch full project details to get output_url
            try:
                project_details = mergado_client.get_project(project_id)
                logger.info(f"Fetched project {project_id} details - slug: {project_details.get('slug')}, "
                           f"output_format: {project_details.get('output_format')}")
                logger.debug(f"Full project details keys: {list(project_details.keys())}")
            except Exception as e:
                logger.warning(f"Failed to fetch details for project {project_id}: {e}")
                project_details = api_project
            
            slug = project_details.get('slug')
            output_format = project_details.get('output_format', '')

            # Construct output URL from slug (NOT from 'url' field which is the INPUT feed)
            output_url = None
            if slug:
                fmt = output_format.lower()
                if 'csv' in fmt or 'shopify' in fmt:
                    extension = 'csv'
                else:
                    extension = 'xml'
                output_url = f"https://feeds.mergado.com/{slug}.{extension}"
                logger.info(f"Constructed output URL for project {project_id}: {output_url}")
            else:
                logger.warning(f"Project {project_id} has no slug, cannot construct output URL")
            
            # Get or create project
            project = Project.query.filter_by(mergado_project_id=project_id).first()
            if not project:
                project = Project(
                    shop_id=shop.id,
                    mergado_project_id=project_id,
                    name=project_details.get('name', api_project.get('name', project_id)),
                    output_url=output_url,
                    output_format=project_details.get('output_format', 'shopify_csv')
                )
                db.session.add(project)
            else:
                project.name = project_details.get('name', api_project.get('name', project_id))
                project.output_url = output_url
                project.output_format = project_details.get('output_format', 'shopify_csv')

        
        db.session.commit()
        
        # Return projects from database
        db_projects = Project.query.join(Shop).filter(Shop.mergado_shop_id == shop_id).all()
        
        return jsonify({
            'projects': [p.to_dict() for p in db_projects]
        })
        
    except Exception as e:
        logger.error(f"Failed to fetch projects: {e}")
        return jsonify({'error': str(e)}), 500


@project_bp.route('/<int:project_id>', methods=['GET'])
@require_auth
def get_project(project_id: int):
    """
    Get project details.
    
    Args:
        project_id: Database project ID
        
    Returns:
        Project details
    """
    project = Project.query.get_or_404(project_id)
    return jsonify(project.to_dict())
