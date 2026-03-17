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
from app.models.shopify_id_mapping import ShopifyIDMapping
from app.services.mergado_client import MergadoClient
from app.services.shopify_service import ShopifyService
from app.services.exceptions import APIError


logger = logging.getLogger(__name__)


class PriceSyncService:
    """
    Synchronizes prices from Mergado to Shopify.
    
    Workflow:
    1. Fetch products from Mergado with SKU, price, and compare-at price
    2. Look up Shopify product/variant IDs from database mappings
    3. Find matching Shopify variant (by variant_id, SKU, or single variant)
    4. Update Shopify variant price and compare-at price via Variants API
    5. Log results to database
    """
    
    # Mergado element paths (from Shopify CSV output feed)
    SKU_ELEMENT = 'Variant SKU'
    PRICE_ELEMENT = 'Variant Price'
    COMPARE_AT_PRICE_ELEMENT = 'Variant Compare At Price'
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
                    self.COMPARE_AT_PRICE_ELEMENT
                ]
            )
            
            logger.info(f"Fetched {len(products)} products from Mergado")
            
            items_synced = 0
            items_failed = 0
            errors = []
            
            for product in products:
                sku = None
                try:
                    # Extract values (Mergado API returns data under 'data' key, not 'values')
                    product_data = product.get('data', {})
                    sku = product_data.get(self.SKU_ELEMENT)
                    price = product_data.get(self.PRICE_ELEMENT)
                    compare_at_price = product_data.get(self.COMPARE_AT_PRICE_ELEMENT)
                    
                    # Skip if missing SKU
                    if not sku:
                        continue
                    
                    # Get shopify_id from database mapping (more reliable than Mergado element)
                    mapping = ShopifyIDMapping.query.filter_by(
                        project_id=project.id,
                        sku=sku
                    ).first()
                    
                    if not mapping:
                        continue
                    
                    shopify_product_id = mapping.shopify_product_id
                    shopify_variant_id = mapping.shopify_variant_id
                    
                    # Parse price value
                    try:
                        price_value = float(price) if price else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid price value for SKU {sku}: {price}")
                        continue
                    
                    # Skip if no valid price
                    if price_value is None:
                        continue
                    
                    # Parse compare-at price (optional for non-discounted products)
                    compare_at_price_value = None
                    if compare_at_price:
                        try:
                            compare_at_price_value = float(compare_at_price)
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid compare-at price for SKU {sku}: {compare_at_price}")
                    
                    # Get Shopify product to find variant
                    try:
                        shopify_product = self.shopify.get_product(shopify_product_id)
                    except APIError as e:
                        # Handle 404 - product was deleted in Shopify
                        if e.status_code == 404:
                            logger.warning(
                                f"[AUDIT] Deleting stale mapping: project={project.id}, sku={sku}, "
                                f"shopify_product_id={shopify_product_id}, shopify_variant_id={shopify_variant_id}. "
                                f"Reason: Product returned 404 from Shopify API."
                            )
                            db.session.delete(mapping)
                            db.session.commit()
                            items_failed += 1
                            continue
                        # Re-raise other errors
                        raise
                    
                    # Find variant (same logic as stock sync)
                    variant = None
                    variants = shopify_product.get('product', {}).get('variants', [])
                    
                    # Try to match by variant_id if we have it
                    if shopify_variant_id:
                        for v in variants:
                            if str(v.get('id')) == str(shopify_variant_id):
                                variant = v
                                break
                    
                    # If not found by variant_id, try matching by SKU (for simple products)
                    if not variant:
                        for v in variants:
                            if v.get('sku') == sku:
                                variant = v
                                break
                    
                    # If still not found and product has only one variant, use it (simple product)
                    if not variant and len(variants) == 1:
                        variant = variants[0]
                    
                    if not variant:
                        logger.warning(f"Variant not found for SKU {sku} in product {shopify_product_id}")
                        items_failed += 1
                        continue
                    
                    # Update variant price (and compare-at price if present)
                    variant_id = variant.get('id')
                    variant_update = {
                        'variant': {
                            'id': variant_id,
                            'price': f"{price_value:.2f}"
                        }
                    }
                    
                    # Add compare-at price if present (for discounted products)
                    if compare_at_price_value is not None:
                        variant_update['variant']['compare_at_price'] = f"{compare_at_price_value:.2f}"
                    
                    self.shopify.update_variant(
                        variant_id=str(variant_id),
                        variant_data=variant_update
                    )
                    
                    # Mark mapping as synced (update last_synced_at)
                    mapping.last_synced_at = datetime.utcnow()
                    db.session.commit()
                    
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
