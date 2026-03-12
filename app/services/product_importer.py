"""
Product Importer - imports products to Shopify with progress tracking.

Handles batch import with SSE progress updates, error handling, and logging.
"""
import gc
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from app import db
from app.models.import_job import ImportJob, ImportStatus
from app.models.import_log import ImportLog, ImportLogStatus
from app.services.shopify_service import ShopifyService
from app.services.product_matcher import ProductMatch, VariantMatch, MatchAction
from app.services.exceptions import APIError


logger = logging.getLogger(__name__)


class ProductImporter:
    """
    Imports products to Shopify with progress tracking.
    
    Handles both create and update operations, logs results to database,
    and sends progress updates via callback.
    """
    
    def __init__(
        self,
        shopify_service: ShopifyService,
        import_job: ImportJob,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initialize product importer.
        
        Args:
            shopify_service: Initialized ShopifyService
            import_job: Database ImportJob to track
            progress_callback: Optional callback for progress updates (for SSE)
        """
        self.shopify = shopify_service
        self.import_job = import_job
        self.progress_callback = progress_callback
    
    def _send_progress(self, data: Dict[str, Any]) -> None:
        """Send progress update via callback."""
        if self.progress_callback:
            self.progress_callback(data)
    
    def _log_product_result(
        self,
        product_identifier: str,
        status: ImportLogStatus,
        shopify_product_id: Optional[str] = None,
        shopify_variant_id: Optional[str] = None,
        error_message: Optional[str] = None,
        details: Optional[Dict] = None
    ) -> None:
        """
        Log import result for a product to database.
        
        Args:
            product_identifier: Product SKU or handle
            status: Import status
            shopify_product_id: Created/updated product ID
            shopify_variant_id: Created/updated variant ID
            error_message: Error message if failed
            details: Additional details dict
        """
        log_entry = ImportLog(
            import_job_id=self.import_job.id,
            product_identifier=product_identifier,
            status=status.value,
            shopify_product_id=shopify_product_id,
            shopify_variant_id=shopify_variant_id,
            error_message=error_message,
            details=details
        )
        db.session.add(log_entry)
    
    def _build_shopify_product_data(self, match: ProductMatch) -> Dict[str, Any]:
        """
        Build Shopify product payload from CSV product.
        
        Args:
            match: ProductMatch with CSV data
            
        Returns:
            Product data dict for Shopify API
        """
        csv_product = match.csv_product
        
        # Build base product
        product_data: Dict[str, Any] = {
            'title': csv_product.title,
            'body_html': csv_product.body_html or '',
            'vendor': csv_product.vendor or '',
            'product_type': csv_product.product_type or '',
            'tags': csv_product.tags or '',
            'status': csv_product.status or 'draft',
        }
        
        # Add handle for create operations
        if match.action == MatchAction.CREATE:
            product_data['handle'] = csv_product.handle
        
        # Add SEO if present
        if csv_product.seo_title or csv_product.seo_description:
            product_data['metafields_global_title_tag'] = csv_product.seo_title
            product_data['metafields_global_description_tag'] = csv_product.seo_description
        
        # Add variants
        variants = []
        for vm in match.variant_matches:
            if vm.action == MatchAction.SKIP:
                continue
            
            csv_variant = vm.csv_variant
            variant_data: Dict[str, Any] = {
                'sku': csv_variant.sku,
                'price': csv_variant.price or '0.00',
            }
            
            # Add variant ID for updates
            if vm.action == MatchAction.UPDATE and vm.shopify_variant_id:
                variant_data['id'] = vm.shopify_variant_id
            
            # Add inventory data
            if csv_variant.inventory_qty:
                variant_data['inventory_quantity'] = int(csv_variant.inventory_qty)
            if csv_variant.inventory_tracker:
                variant_data['inventory_management'] = csv_variant.inventory_tracker
            if csv_variant.inventory_policy:
                variant_data['inventory_policy'] = csv_variant.inventory_policy
            
            # Add options
            if csv_variant.option1_value:
                variant_data['option1'] = csv_variant.option1_value
            if csv_variant.option2_value:
                variant_data['option2'] = csv_variant.option2_value
            if csv_variant.option3_value:
                variant_data['option3'] = csv_variant.option3_value
            
            # Add other fields
            if csv_variant.grams:
                variant_data['grams'] = int(csv_variant.grams)
            if csv_variant.barcode:
                variant_data['barcode'] = csv_variant.barcode
            if csv_variant.requires_shipping:
                variant_data['requires_shipping'] = csv_variant.requires_shipping.lower() == 'true'
            
            variants.append(variant_data)
        
        product_data['variants'] = variants
        
        # Add images
        if csv_product.image_src:
            product_data['images'] = [{'src': url} for url in csv_product.image_src if url]
        
        # Add metafields (Shopify expects specific format)
        if csv_product.metafields:
            metafields = []
            for key, value in csv_product.metafields.items():
                namespace, field_key = key.split('.', 1)
                metafields.append({
                    'namespace': namespace,
                    'key': field_key,
                    'value': value,
                    'type': 'single_line_text_field'
                })
            product_data['metafields'] = metafields
        
        return {'product': product_data}
    
    def import_products(self, matches: List[ProductMatch]) -> None:
        """
        Import all matched products to Shopify (batch, no progress yielding).

        Args:
            matches: List of product matches from ProductMatcher
        """
        for progress in self.import_products_iter(matches):
            self._send_progress(progress)

    @staticmethod
    def _mem_mb() -> float:
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024.0
        except Exception:
            pass
        return -1.0

    def import_products_iter(self, matches: List[ProductMatch]):
        """
        Import products one at a time, yielding progress dicts after each.

        Yields:
            dict with status, counts, and percent
        """
        self.import_job.status = ImportStatus.RUNNING.value
        self.import_job.started_at = datetime.utcnow()
        self.import_job.total_count = len([m for m in matches if m.action != MatchAction.SKIP])
        db.session.commit()

        yield {
            'status': 'started',
            'total': self.import_job.total_count,
            'processed': 0,
        }

        processed = 0
        pending_skips = 0

        try:
            for idx, match in enumerate(matches):
                if match.action == MatchAction.SKIP:
                    self._log_product_result(
                        product_identifier=match.primary_sku or match.csv_product.handle,
                        status=ImportLogStatus.SKIPPED,
                        error_message=match.reason,
                    )
                    self.import_job.skipped_count += 1
                    matches[idx] = None
                    pending_skips += 1
                    if pending_skips >= 50:
                        db.session.commit()
                        db.session.expire_all()
                        pending_skips = 0
                    continue

                if pending_skips > 0:
                    db.session.commit()
                    db.session.expire_all()
                    pending_skips = 0

                try:
                    if match.action == MatchAction.CREATE:
                        result = self._create_product(match)
                    else:
                        result = self._update_product(match)

                    self._log_product_result(
                        product_identifier=match.primary_sku or match.csv_product.handle,
                        status=ImportLogStatus.SUCCESS,
                        shopify_product_id=result.get('product', {}).get('id'),
                        details={'variants_count': len(result.get('product', {}).get('variants', []))},
                    )
                    self.import_job.success_count += 1

                except APIError as e:
                    logger.error(f"Failed to import {match.primary_sku}: {e}")
                    self._log_product_result(
                        product_identifier=match.primary_sku or match.csv_product.handle,
                        status=ImportLogStatus.FAILED,
                        error_message=str(e),
                    )
                    self.import_job.failed_count += 1

                matches[idx] = None
                processed += 1
                db.session.commit()
                db.session.expire_all()

                # #region agent log
                if processed % 25 == 0:
                    gc.collect()
                    logger.info(
                        f"[DBG-654f3d] import_iter job={self.import_job.id} "
                        f"processed={processed} mem_mb={self._mem_mb():.1f}"
                    )
                # #endregion

                time.sleep(0.6)

                total = max(self.import_job.total_count, 1)
                yield {
                    'status': 'processing',
                    'total': self.import_job.total_count,
                    'processed': processed,
                    'success': self.import_job.success_count,
                    'failed': self.import_job.failed_count,
                    'skipped': self.import_job.skipped_count,
                    'percent': int((processed / total) * 100),
                }

            if pending_skips > 0:
                db.session.commit()
                db.session.expire_all()

            self.import_job.status = ImportStatus.COMPLETED.value
            self.import_job.finished_at = datetime.utcnow()
            db.session.commit()

            logger.info(
                f"Import job {self.import_job.id} completed: "
                f"{self.import_job.success_count} success, "
                f"{self.import_job.failed_count} failed, "
                f"{self.import_job.skipped_count} skipped"
            )

            yield {
                'status': 'completed',
                'total': self.import_job.total_count,
                'processed': processed,
                'success': self.import_job.success_count,
                'failed': self.import_job.failed_count,
                'skipped': self.import_job.skipped_count,
                'percent': 100,
            }

        except Exception as e:
            logger.error(f"Import job {self.import_job.id} failed: {e}")
            self.import_job.status = ImportStatus.FAILED.value
            self.import_job.error_message = str(e)
            self.import_job.finished_at = datetime.utcnow()
            db.session.commit()

            yield {'status': 'failed', 'error': str(e)}
            raise
    
    def _create_product(self, match: ProductMatch) -> Dict[str, Any]:
        """
        Create new product in Shopify.
        
        Args:
            match: ProductMatch with CREATE action
            
        Returns:
            Created product data from Shopify
        """
        product_data = self._build_shopify_product_data(match)
        logger.info(f"Creating product: {match.csv_product.handle} ({match.primary_sku})")
        
        result = self.shopify.create_product(product_data)
        
        logger.info(
            f"Created product {result['product']['id']} "
            f"with {len(result['product']['variants'])} variants"
        )
        
        return result
    
    def _update_product(self, match: ProductMatch) -> Dict[str, Any]:
        """
        Update existing product in Shopify.
        
        Args:
            match: ProductMatch with UPDATE action
            
        Returns:
            Updated product data from Shopify
        """
        product_data = self._build_shopify_product_data(match)
        logger.info(
            f"Updating product: {match.shopify_product_id} "
            f"({match.csv_product.handle})"
        )
        
        result = self.shopify.update_product(match.shopify_product_id, product_data)
        
        logger.info(
            f"Updated product {result['product']['id']} "
            f"with {len(result['product']['variants'])} variants"
        )
        
        return result
