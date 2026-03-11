"""
Stock Sync - synchronizes STOCK_AMOUNT from Mergado to Shopify inventory.

Reads stock data from Mergado products and updates Shopify inventory levels.
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from app import db
from app.models.sync_config import SyncConfig, SyncType
from app.models.sync_log import SyncLog, SyncStatus
from app.services.mergado_client import MergadoClient
from app.services.shopify_service import ShopifyService
from app.services.exceptions import APIError


logger = logging.getLogger(__name__)


class StockSyncService:
    """
    Synchronizes stock levels from Mergado to Shopify.
    
    Workflow:
    1. Fetch products from Mergado with ITEM_ID and STOCK_AMOUNT
    2. For each SKU, find matching Shopify variant
    3. Update Shopify inventory level via Inventory API
    4. Log results to database
    """
    
    # Mergado element paths
    SKU_ELEMENT = 'ITEM_ID'
    STOCK_ELEMENT = 'STOCK_AMOUNT'
    SHOPIFY_ID_ELEMENT = 'shopify_id'
    
    def __init__(
        self,
        mergado_client: MergadoClient,
        shopify_service: ShopifyService,
        sync_config: SyncConfig
    ):
        """
        Initialize stock sync service.
        
        Args:
            mergado_client: Initialized MergadoClient
            shopify_service: Initialized ShopifyService
            sync_config: Database SyncConfig for this sync
        """
        self.mergado = mergado_client
        self.shopify = shopify_service
        self.sync_config = sync_config
        self.shopify_location_id: Optional[str] = None
    
    def _get_primary_location(self) -> str:
        """
        Get primary Shopify location ID.
        
        Returns:
            Location ID
            
        Raises:
            APIError: If no locations found
        """
        if self.shopify_location_id:
            return self.shopify_location_id
        
        locations = self.shopify.get_locations()
        
        if not locations:
            raise APIError("No Shopify locations found")
        
        # Use first location (for MVP)
        # For production, let user configure preferred location
        self.shopify_location_id = str(locations[0]['id'])
        logger.info(f"Using Shopify location: {self.shopify_location_id}")
        
        return self.shopify_location_id
    
    def sync_stock(self) -> Dict[str, Any]:
        """
        Execute stock synchronization.
        
        Returns:
            Sync summary dict
        """
        project = self.sync_config.project
        project_id = project.mergado_project_id
        
        # Create sync log
        sync_log = SyncLog(
            sync_config_id=self.sync_config.id,
            status=SyncStatus.SUCCESS.value,
            started_at=datetime.utcnow()
        )
        db.session.add(sync_log)
        db.session.flush()
        
        logger.info(f"Starting stock sync for project {project_id}")
        
        try:
            # Get primary location
            location_id = self._get_primary_location()
            
            # Fetch products from Mergado with stock data
            products = self.mergado.get_project_products(
                project_id,
                limit=100,
                values_to_extract=[
                    self.SKU_ELEMENT,
                    self.STOCK_ELEMENT,
                    self.SHOPIFY_ID_ELEMENT
                ]
            )
            
            logger.info(f"Fetched {len(products)} products from Mergado")
            
            items_synced = 0
            items_failed = 0
            errors = []
            
            for product in products:
                try:
                    # Extract values
                    sku = product.get('values', {}).get(self.SKU_ELEMENT)
                    stock = product.get('values', {}).get(self.STOCK_ELEMENT)
                    shopify_id = product.get('values', {}).get(self.SHOPIFY_ID_ELEMENT)
                    
                    # Skip if missing data
                    if not sku or not shopify_id:
                        continue
                    
                    # Parse stock value
                    try:
                        stock_qty = int(stock) if stock else 0
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid stock value for SKU {sku}: {stock}")
                        continue
                    
                    # Get Shopify product to find variant
                    shopify_product = self.shopify.get_product(shopify_id)
                    
                    # Find variant by SKU
                    variant = None
                    for v in shopify_product.get('product', {}).get('variants', []):
                        if v.get('sku') == sku:
                            variant = v
                            break
                    
                    if not variant:
                        logger.warning(f"Variant not found for SKU {sku} in product {shopify_id}")
                        items_failed += 1
                        continue
                    
                    # Update inventory
                    inventory_item_id = variant.get('inventory_item_id')
                    if not inventory_item_id:
                        logger.warning(f"No inventory_item_id for variant {variant.get('id')}")
                        items_failed += 1
                        continue
                    
                    self.shopify.update_inventory_level(
                        inventory_item_id=str(inventory_item_id),
                        location_id=location_id,
                        available=stock_qty
                    )
                    
                    items_synced += 1
                    logger.debug(f"Updated stock for SKU {sku}: {stock_qty}")
                    
                except APIError as e:
                    logger.error(f"Failed to sync stock for SKU {sku}: {e}")
                    items_failed += 1
                    errors.append(f"{sku}: {str(e)}")
            
            # Update sync log
            sync_log.status = SyncStatus.PARTIAL.value if items_failed > 0 else SyncStatus.SUCCESS.value
            sync_log.items_synced = items_synced
            sync_log.items_failed = items_failed
            sync_log.finished_at = datetime.utcnow()
            
            if errors:
                sync_log.details = {'errors': errors[:10]}  # Store first 10 errors
            
            # Update sync config last_sync_at
            self.sync_config.last_sync_at = datetime.utcnow()
            
            db.session.commit()
            
            logger.info(
                f"Stock sync completed: {items_synced} synced, "
                f"{items_failed} failed"
            )
            
            return {
                'success': True,
                'items_synced': items_synced,
                'items_failed': items_failed,
                'sync_log_id': sync_log.id
            }
            
        except Exception as e:
            logger.error(f"Stock sync failed: {e}", exc_info=True)
            sync_log.status = SyncStatus.FAILED.value
            sync_log.error_message = str(e)
            sync_log.finished_at = datetime.utcnow()
            db.session.commit()
            
            raise
