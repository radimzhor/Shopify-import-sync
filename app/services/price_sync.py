"""
Price Sync - synchronizes prices from Mergado to Shopify variants.

Reads price data from Mergado products and updates Shopify variant prices.
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


class PriceSyncService:
    """
    Synchronizes prices from Mergado to Shopify.
    
    Workflow:
    1. Fetch products from Mergado with ITEM_ID, PRICE, and shopify_id
    2. For each SKU, find matching Shopify variant
    3. Update Shopify variant price via Variants API
    4. Log results to database
    """
    
    # Mergado element paths
    SKU_ELEMENT = 'ITEM_ID'
    PRICE_ELEMENT = 'PRICE'
    SHOPIFY_ID_ELEMENT = 'shopify_id'
    
    def __init__(
        self,
        mergado_client: MergadoClient,
        shopify_service: ShopifyService,
        sync_config: SyncConfig
    ):
        """
        Initialize price sync service.
        
        Args:
            mergado_client: Initialized MergadoClient
            shopify_service: Initialized ShopifyService
            sync_config: Database SyncConfig for this sync
        """
        self.mergado = mergado_client
        self.shopify = shopify_service
        self.sync_config = sync_config
    
    def sync_prices(self) -> Dict[str, Any]:
        """
        Execute price synchronization.
        
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
        
        logger.info(f"Starting price sync for project {project_id}")
        
        try:
            # Fetch products from Mergado with price data
            products = self.mergado.get_project_products(
                project_id,
                limit=100,
                values_to_extract=[
                    self.SKU_ELEMENT,
                    self.PRICE_ELEMENT,
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
                    price = product.get('values', {}).get(self.PRICE_ELEMENT)
                    shopify_id = product.get('values', {}).get(self.SHOPIFY_ID_ELEMENT)
                    
                    # Skip if missing data
                    if not sku or not shopify_id or not price:
                        continue
                    
                    # Parse price value
                    try:
                        price_value = float(price)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid price value for SKU {sku}: {price}")
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
                    
                    # Update variant price
                    variant_id = variant.get('id')
                    self.shopify.update_variant(
                        variant_id=str(variant_id),
                        variant_data={
                            'variant': {
                                'id': variant_id,
                                'price': f"{price_value:.2f}"
                            }
                        }
                    )
                    
                    items_synced += 1
                    logger.debug(f"Updated price for SKU {sku}: {price_value:.2f}")
                    
                except APIError as e:
                    logger.error(f"Failed to sync price for SKU {sku}: {e}")
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
                f"Price sync completed: {items_synced} synced, "
                f"{items_failed} failed"
            )
            
            return {
                'success': True,
                'items_synced': items_synced,
                'items_failed': items_failed,
                'sync_log_id': sync_log.id
            }
            
        except Exception as e:
            logger.error(f"Price sync failed: {e}", exc_info=True)
            sync_log.status = SyncStatus.FAILED.value
            sync_log.error_message = str(e)
            sync_log.finished_at = datetime.utcnow()
            db.session.commit()
            
            raise
