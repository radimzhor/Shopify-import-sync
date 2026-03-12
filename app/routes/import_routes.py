"""
Import routes - handles product import operations with background processing.
"""
import logging
import threading

from flask import Blueprint, request, jsonify, current_app
from werkzeug.exceptions import BadRequest

from app import db
from app.auth.oauth import require_auth
from app.models.import_job import ImportJob, ImportStatus
from app.models.import_log import ImportLog
from app.models.project import Project
from app.services import (
    MergadoClient,
    ShopifyService,
    CSVDownloader,
    ShopifyCSVParser,
    ProductMatcher,
    ShopifyIDWriteback,
)
from app.services.product_importer import ProductImporter


logger = logging.getLogger(__name__)
import_bp = Blueprint('import', __name__, url_prefix='/api/import')


def _run_import_in_background(app, job_id: int, access_token: str, shop_id: str):
    """
    Run the full import pipeline in a background thread.

    Uses the Flask app context so SQLAlchemy sessions work correctly.
    Updates the ImportJob row after every product so the polling endpoint
    always has fresh numbers.
    """
    with app.app_context():
        import_job = ImportJob.query.get(job_id)
        if not import_job:
            logger.error(f"[BG] Import job {job_id} not found")
            return

        project = import_job.project

        try:
            mergado_client = MergadoClient(access_token)
            shopify_service = ShopifyService(mergado_client, shop_id)

            logger.info(f"[BG] Job {job_id}: downloading CSV from {project.output_url}")
            downloader = CSVDownloader()
            csv_path = downloader.download(
                project.output_url,
                cache_key=project.mergado_project_id,
            )
            parser = ShopifyCSVParser(csv_path)
            csv_products = parser.parse_all()

            logger.info(f"[BG] Job {job_id}: parsed {len(csv_products)} products, matching...")
            matcher = ProductMatcher(shopify_service)
            matches = matcher.match_products(csv_products)

            logger.info(f"[BG] Job {job_id}: matched {len(matches)} products, importing...")
            importer = ProductImporter(shopify_service, import_job, progress_callback=None)

            for _progress in importer.import_products_iter(matches):
                pass  # DB is updated inside the iterator; nothing else needed

            logger.info(
                f"[BG] Job {job_id} done: "
                f"{import_job.success_count} success, "
                f"{import_job.failed_count} failed, "
                f"{import_job.skipped_count} skipped"
            )

        except Exception as e:
            logger.error(f"[BG] Job {job_id} failed: {e}", exc_info=True)
            import_job.status = ImportStatus.FAILED.value
            import_job.error_message = str(e)
            db.session.commit()


@import_bp.route('/preview', methods=['POST'])
@require_auth
def preview_import():
    """
    Generate import preview (what will be created/updated).
    
    Expects:
        {
            "project_id": "123",  # Database project ID or Mergado project ID
            "shop_id": "456"
        }
    
    Returns:
        Match preview with counts
    """
    data = request.get_json()
    project_id = data.get('project_id')
    shop_id = data.get('shop_id')
    
    if not project_id or not shop_id:
        raise BadRequest("project_id and shop_id required")
    
    # Get project from database (try both database ID and Mergado project ID)
    try:
        project = Project.query.get(int(project_id))
    except (ValueError, TypeError):
        project = None
    
    if not project:
        project = Project.query.filter_by(mergado_project_id=str(project_id)).first()
    
    if not project:
        raise BadRequest(f"Project with ID {project_id} not found")
    
    if not project.output_url:
        raise BadRequest("Project is missing output URL. Please reload the project list.")
    
    # Initialize services
    # Extract token from Authorization header
    auth_header = request.headers.get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
    
    if not access_token:
        raise BadRequest("Access token required")
    
    mergado_client = MergadoClient(access_token)
    shopify_service = ShopifyService(mergado_client, shop_id)
    
    try:
        logger.info(f"Generating preview for project {project.id} (Mergado ID: {project.mergado_project_id})")
        
        # Download CSV
        downloader = CSVDownloader()
        csv_path = downloader.download(project.output_url, cache_key=str(project.id))
        logger.info(f"Downloaded CSV from {project.output_url} to {csv_path}")
        
        # Parse CSV
        parser = ShopifyCSVParser(csv_path)
        csv_products = parser.parse_all()
        logger.info(f"Parsed {len(csv_products)} products from CSV")
        
        # Match products
        matcher = ProductMatcher(shopify_service)
        matches = matcher.match_products(csv_products)
        preview = matcher.generate_preview(matches)
        logger.info(f"Generated preview: {preview.products_to_create} create, {preview.products_to_update} update, {preview.products_to_skip} skip")
        
        return jsonify(preview.to_dict())
        
    except Exception as e:
        logger.error(f"Preview failed for project {project.id}: {e}", exc_info=True)
        error_message = str(e)
        msg_lower = error_message.lower()

        if '404' in error_message and 'shopify/proxy' in msg_lower:
            error_message = (
                "Shopify is not connected for this shop. "
                "Please set up the Shopify connection in your Mergado Keychain first."
            )
        elif 'shopify' in msg_lower or 'connection' in msg_lower:
            error_message = (
                "Failed to connect to Shopify. "
                "Please check if Shopify is connected in your Mergado Keychain."
            )
        elif 'download' in msg_lower or 'url' in msg_lower:
            error_message = (
                "Failed to download product feed. "
                "Please check if the project output is configured in Mergado."
            )
        elif 'parse' in msg_lower or 'csv' in msg_lower:
            error_message = (
                "Failed to parse CSV feed. "
                "Please check if the project is configured for Shopify CSV output."
            )

        return jsonify({'error': error_message}), 500


@import_bp.route('/start', methods=['POST'])
@require_auth
def start_import():
    """
    Start product import job.
    
    Expects:
        {
            "project_id": "123",
            "shop_id": "456",
            "force_create": false (optional)
        }
    
    Returns:
        Import job ID for tracking progress
    """
    data = request.get_json()
    project_id = data.get('project_id')
    shop_id = data.get('shop_id')
    force_create = data.get('force_create', False)
    
    if not project_id or not shop_id:
        raise BadRequest("project_id and shop_id required")
    
    # Get project from database (try both database ID and Mergado project ID)
    try:
        project = Project.query.get(int(project_id))
    except (ValueError, TypeError):
        project = None

    if not project:
        project = Project.query.filter_by(mergado_project_id=str(project_id)).first()

    if not project:
        raise BadRequest(f"Project with ID {project_id} not found")
    if not project.output_url:
        raise BadRequest("Project is missing output URL. Please reload the project list.")

    auth_header = request.headers.get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
    if not access_token:
        raise BadRequest("Access token required")

    import_job = ImportJob(
        project_id=project.id,
        status=ImportStatus.PENDING.value,
    )
    db.session.add(import_job)
    db.session.commit()

    logger.info(f"Created import job {import_job.id} for project {project_id}")

    # Launch import in a background thread so the HTTP response returns immediately
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_import_in_background,
        args=(app, import_job.id, access_token, shop_id),
        daemon=True,
    )
    thread.start()

    return jsonify({
        'job_id': import_job.id,
        'status': import_job.status,
    })


@import_bp.route('/status/<int:job_id>')
@require_auth
def get_import_status(job_id: int):
    """
    Get current status of import job.
    
    Args:
        job_id: Import job ID
        
    Returns:
        Import job status and counts
    """
    import_job = ImportJob.query.get_or_404(job_id)
    return jsonify(import_job.to_dict())


@import_bp.route('/history')
@require_auth
def get_import_history():
    """
    Get import job history.
    
    Query params:
        project_id: Filter by project (optional)
        limit: Number of jobs to return (default 50)
    
    Returns:
        List of import jobs
    """
    project_id = request.args.get('project_id', type=int)
    limit = request.args.get('limit', type=int, default=50)
    
    query = ImportJob.query
    
    if project_id:
        query = query.filter_by(project_id=project_id)
    
    jobs = query.order_by(ImportJob.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'jobs': [job.to_dict() for job in jobs]
    })


@import_bp.route('/writeback/<int:job_id>', methods=['POST'])
@require_auth
def writeback_shopify_ids(job_id: int):
    """
    Write Shopify IDs back to Mergado for an import job.
    
    Args:
        job_id: Import job ID
        
    Returns:
        Writeback result summary
    """
    # Verify job exists and is completed
    import_job = ImportJob.query.get_or_404(job_id)
    
    if import_job.status != ImportStatus.COMPLETED.value:
        raise BadRequest(f"Import job must be completed (current: {import_job.status})")
    
    # Extract token from Authorization header
    auth_header = request.headers.get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
    
    if not access_token:
        raise BadRequest("Access token required")
    
    # Initialize services
    mergado_client = MergadoClient(access_token)
    writeback_service = ShopifyIDWriteback(mergado_client, import_job.project)
    
    try:
        result = writeback_service.writeback_from_import_job(job_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Writeback failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
