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
from app.models.shopify_id_mapping import ShopifyIDMapping
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
    
    # Mergado element paths (from Shopify CSV output feed)
    SKU_ELEMENT = 'Variant SKU'
    STOCK_ELEMENT = 'Variant Inventory Qty'
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
    
    def _handle_stale_mapping(self, project_id: int, sku: str, shopify_id: str) -> None:
        """
        Handle stale mapping when product is not found in Shopify (404).
        
        Logs the deletion for audit trail and removes the mapping from database.
        
        Args:
            project_id: Internal project ID
            sku: Product SKU
            shopify_id: Shopify product ID that no longer exists
        """
        # Look up the mapping
        mapping = ShopifyIDMapping.query.filter_by(
            project_id=project_id,
            sku=sku
        ).first()
        
        if mapping:
            # Audit log before deletion
            logger.warning(
                f"[AUDIT] Deleting stale mapping: project={project_id}, sku={sku}, "
                f"shopify_product_id={mapping.shopify_product_id}, "
                f"shopify_variant_id={mapping.shopify_variant_id}, "
                f"last_updated={mapping.updated_at}, last_synced={mapping.last_synced_at}. "
                f"Reason: Product {shopify_id} returned 404 from Shopify API."
            )
            
            # Delete the stale mapping
            db.session.delete(mapping)
            db.session.commit()
            
            logger.info(f"Removed stale mapping for SKU {sku} (product {shopify_id} not found)")
        else:
            # Mapping not in our database, but was in Mergado feed
            logger.warning(
                f"Product {shopify_id} for SKU {sku} not found in Shopify, "
                f"but no mapping exists in local database"
            )
    
    def _mark_mapping_synced(self, project_id: int, sku: str) -> None:
        """
        Update last_synced_at timestamp for a successful sync.
        
        Args:
            project_id: Internal project ID
            sku: Product SKU
        """
        mapping = ShopifyIDMapping.query.filter_by(
            project_id=project_id,
            sku=sku
        ).first()
        
        if mapping:
            mapping.last_synced_at = datetime.utcnow()
            db.session.commit()
    
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
        logger.info("Debug logs will be written to /tmp/debug-stock-sync.log")
        
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
            
            # #region agent log
            debug_counter = 0
            # #endregion
            
            for product in products:
                # #region agent log
                debug_counter += 1
                # #endregion
                sku = None
                try:
                    # #region agent log
                    if debug_counter <= 3: 
                        product_data = product.get('data', {})
                        import json;open('/tmp/debug-stock-sync.log','a').write(json.dumps({'sessionId':'1a3c34','location':'stock_sync.py:188','message':'Product structure','data':{'product_num':debug_counter,'product_keys':list(product.keys()),'data_keys':list(product_data.keys()),'has_values':'values' in product,'has_data':'data' in product,'element_names_looking_for':[self.SKU_ELEMENT,self.STOCK_ELEMENT,self.SHOPIFY_ID_ELEMENT],'product_data_sample':str(product_data)[:500]},'timestamp':int(datetime.utcnow().timestamp()*1000),'hypothesisId':'C'})+'\n')
                    # #endregion
                    # Extract values (Mergado API returns data under 'data' key, not 'values')
                    sku = product.get('data', {}).get(self.SKU_ELEMENT)
                    stock = product.get('data', {}).get(self.STOCK_ELEMENT)
                    shopify_id = product.get('data', {}).get(self.SHOPIFY_ID_ELEMENT)
                    
                    # #region agent log
                    if debug_counter <= 3: import json;open('/tmp/debug-stock-sync.log','a').write(json.dumps({'sessionId':'1a3c34','location':'stock_sync.py:198','message':'Extracted values','data':{'product_num':debug_counter,'sku':str(sku),'stock':str(stock),'shopify_id':str(shopify_id),'sku_present':bool(sku),'shopify_id_present':bool(shopify_id)},'timestamp':int(datetime.utcnow().timestamp()*1000),'hypothesisId':'A,B'})+'\n')
                    # #endregion
                    
                    # Skip if missing data
                    if not sku or not shopify_id:
                        # #region agent log
                        if debug_counter <= 10: import json;open('/tmp/debug-stock-sync.log','a').write(json.dumps({'sessionId':'1a3c34','location':'stock_sync.py:204','message':'SKIPPED - missing data','data':{'product_num':debug_counter,'sku':str(sku),'shopify_id':str(shopify_id),'missing_sku':not bool(sku),'missing_shopify_id':not bool(shopify_id)},'timestamp':int(datetime.utcnow().timestamp()*1000),'hypothesisId':'A,B'})+'\n')
                        # #endregion
                        continue
                    
                    # Parse shopify_id (format: "productid:variantid")
                    # Extract just the product ID part for get_product API call
                    shopify_product_id = shopify_id.split(':')[0] if ':' in shopify_id else shopify_id
                    
                    # Parse stock value
                    try:
                        stock_qty = int(stock) if stock else 0
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid stock value for SKU {sku}: {stock}")
                        continue
                    
                    # Get Shopify product to find variant
                    try:
                        shopify_product = self.shopify.get_product(shopify_product_id)
                    except APIError as e:
                        # Handle 404 - product was deleted in Shopify
                        if e.status_code == 404:
                            self._handle_stale_mapping(project.id, sku, shopify_product_id)
                            items_failed += 1
                            continue
                        # Re-raise other errors
                        raise
                    
                    # Find variant by SKU
                    variant = None
                    for v in shopify_product.get('product', {}).get('variants', []):
                        if v.get('sku') == sku:
                            variant = v
                            break
                    
                    if not variant:
                        logger.warning(f"Variant not found for SKU {sku} in product {shopify_product_id}")
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
                    
                    # Mark mapping as synced (update last_synced_at)
                    self._mark_mapping_synced(project.id, sku)
                    
                    items_synced += 1
                    logger.debug(f"Updated stock for SKU {sku}: {stock_qty}")
                    
                except APIError as e:
                    logger.error(f"Failed to sync stock for SKU {sku}: {e}")
                    items_failed += 1
                    errors.append(f"{sku}: {str(e)}")
            
            # #region agent log
            import json;open('/tmp/debug-stock-sync.log','a').write(json.dumps({'sessionId':'1a3c34','location':'stock_sync.py:256','message':'Loop completed','data':{'total_products':len(products),'items_synced':items_synced,'items_failed':items_failed,'products_processed':debug_counter},'timestamp':int(datetime.utcnow().timestamp()*1000),'hypothesisId':'ALL'})+'\n')
            try:
                with open('/tmp/debug-stock-sync.log', 'r') as f:
                    debug_content = f.read()
                    logger.info(f"DEBUG LOG CONTENT:\n{debug_content}")
            except Exception as e:
                logger.error(f"Failed to read debug log: {e}")
            # #endregion
            
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
