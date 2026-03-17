"""
Background scheduler for automatic stock/price synchronization.

Uses APScheduler to periodically check for due syncs and execute them.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app import db
from app.models.sync_config import SyncConfig, SyncType
from app.models.project import Project
from app.services.mergado_client import MergadoClient
from app.services.shopify_service import ShopifyService
from app.services.stock_sync import StockSyncService
from app.services.price_sync import PriceSyncService

logger = logging.getLogger(__name__)


class SyncScheduler:
    """
    Background scheduler for automatic synchronization.
    
    Runs a periodic job that checks for due syncs and executes them.
    """
    
    def __init__(self, app=None):
        """
        Initialize the scheduler.
        
        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        self.scheduler: Optional[BackgroundScheduler] = None
    
    def init_app(self, app):
        """
        Initialize scheduler with Flask app.
        
        Args:
            app: Flask application instance
        """
        self.app = app
    
    def start(self):
        """Start the background scheduler."""
        if self.scheduler is not None and self.scheduler.running:
            logger.warning("Scheduler is already running")
            return
        
        self.scheduler = BackgroundScheduler()
        
        # Check for due syncs every minute
        self.scheduler.add_job(
            func=self._check_and_run_due_syncs,
            trigger=IntervalTrigger(minutes=1),
            id='check_due_syncs',
            name='Check for due synchronizations',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Sync scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler."""
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Sync scheduler stopped")
    
    def _check_and_run_due_syncs(self):
        """
        Check for sync configs that are due to run and execute them.
        
        A sync is due if:
        - It's enabled
        - last_sync_at + interval_minutes <= now
        """
        if not self.app:
            logger.error("App not initialized")
            return
        
        with self.app.app_context():
            try:
                # Get all enabled sync configs
                configs = SyncConfig.query.filter_by(enabled=True).all()
                
                for config in configs:
                    if self._is_sync_due(config):
                        logger.info(
                            f"Running scheduled {config.sync_type} sync for "
                            f"project {config.project_id}"
                        )
                        self._execute_sync(config)
            
            except Exception as e:
                logger.error(f"Error checking for due syncs: {e}", exc_info=True)
    
    def _is_sync_due(self, config: SyncConfig) -> bool:
        """
        Check if a sync config is due to run.
        
        Args:
            config: SyncConfig to check
            
        Returns:
            True if sync should run now
        """
        # If never synced before, it's due
        if config.last_sync_at is None:
            return True
        
        # Calculate next sync time
        next_sync_at = config.last_sync_at + timedelta(minutes=config.interval_minutes)
        
        # Check if we've passed the next sync time
        return datetime.utcnow() >= next_sync_at
    
    def _execute_sync(self, config: SyncConfig):
        """
        Execute a sync for the given config.
        
        Args:
            config: SyncConfig to execute
        """
        try:
            project = config.project
            
            # Get OAuth token from session (stored in project for background syncs)
            # Note: For MVP, we'll need the token to be stored or refreshed
            if not project.shop or not project.shop.access_token:
                logger.error(
                    f"No access token available for project {project.id}. "
                    f"Cannot execute scheduled sync."
                )
                return
            
            access_token = project.shop.access_token
            
            # Initialize clients
            mergado_client = MergadoClient(access_token)
            shopify_service = ShopifyService(
                client=mergado_client,
                shop_id=str(project.shop.mergado_shop_id)
            )
            
            # Execute the appropriate sync
            if config.sync_type == SyncType.STOCK.value:
                sync_service = StockSyncService(
                    mergado_client=mergado_client,
                    shopify_service=shopify_service,
                    sync_config=config
                )
                result = sync_service.sync_stock()
            elif config.sync_type == SyncType.PRICE.value:
                sync_service = PriceSyncService(
                    mergado_client=mergado_client,
                    shopify_service=shopify_service,
                    sync_config=config
                )
                result = sync_service.sync_prices()
            else:
                logger.error(f"Unknown sync type: {config.sync_type}")
                return
            
            logger.info(
                f"Scheduled {config.sync_type} sync completed: "
                f"{result.get('items_synced', 0)} synced, "
                f"{result.get('items_failed', 0)} failed"
            )
        
        except Exception as e:
            logger.error(
                f"Failed to execute scheduled sync for config {config.id}: {e}",
                exc_info=True
            )


# Global scheduler instance
sync_scheduler = SyncScheduler()
