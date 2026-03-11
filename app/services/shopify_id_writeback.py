"""
Shopify ID Writeback - writes Shopify product IDs back to Mergado.

Uses batch_rewriting rules to map SKU -> Shopify ID in Mergado elements.
"""
import logging
from typing import Dict, List, Optional, Tuple, Any

from app import db
from app.models.project import Project
from app.models.import_log import ImportLog, ImportLogStatus
from app.services.mergado_client import MergadoClient
from app.services.exceptions import APIError


logger = logging.getLogger(__name__)


class ShopifyIDWriteback:
    """
    Manages Shopify ID writeback to Mergado via batch_rewriting rules.
    
    Workflow:
    1. Ensure shopify_id element exists in project
    2. Collect SKU -> Shopify ID mappings from successful imports
    3. Create batch_rewriting rule to write IDs
    4. Mark project dirty to trigger rule application
    """
    
    # Element configuration
    SHOPIFY_ID_ELEMENT_NAME = 'shopify_id'
    SHOPIFY_ID_ELEMENT_HIDDEN = False
    
    # Rule configuration
    RULE_NAME_PREFIX = 'Shopify ID Mapping'
    SOURCE_ELEMENT = 'ITEM_ID'  # SKU element in Mergado
    
    def __init__(self, mergado_client: MergadoClient, project: Project):
        """
        Initialize writeback service.
        
        Args:
            mergado_client: Initialized MergadoClient
            project: Database Project model
        """
        self.client = mergado_client
        self.project = project
    
    def ensure_shopify_id_element(self) -> str:
        """
        Ensure shopify_id element exists in Mergado project.
        
        Returns:
            Element ID (creates if needed, or uses existing)
        """
        # Check if already created and stored
        if self.project.shopify_id_element_id:
            logger.info(
                f"Using existing shopify_id element: "
                f"{self.project.shopify_id_element_id}"
            )
            return self.project.shopify_id_element_id
        
        # Check if element exists by listing elements
        try:
            elements = self.client.get_project_elements(
                self.project.mergado_project_id
            )
            
            # Search for shopify_id element
            for element in elements:
                if element.get('name') == self.SHOPIFY_ID_ELEMENT_NAME:
                    element_id = element['id']
                    logger.info(f"Found existing shopify_id element: {element_id}")
                    
                    # Store in project
                    self.project.shopify_id_element_id = element_id
                    db.session.commit()
                    
                    return element_id
            
            # Element doesn't exist, create it
            logger.info(f"Creating shopify_id element in project {self.project.mergado_project_id}")
            
            element = self.client.create_element(
                self.project.mergado_project_id,
                name=self.SHOPIFY_ID_ELEMENT_NAME,
                hidden=self.SHOPIFY_ID_ELEMENT_HIDDEN
            )
            
            element_id = element['id']
            logger.info(f"Created shopify_id element: {element_id}")
            
            # Store in project
            self.project.shopify_id_element_id = element_id
            db.session.commit()
            
            return element_id
            
        except APIError as e:
            logger.error(f"Failed to ensure shopify_id element: {e}")
            raise
    
    def collect_sku_mappings(
        self,
        import_job_id: int
    ) -> List[Tuple[str, str]]:
        """
        Collect SKU -> Shopify ID mappings from successful import logs.
        
        Args:
            import_job_id: Import job ID to get logs from
            
        Returns:
            List of (sku, shopify_product_id) tuples
        """
        # Query successful import logs with Shopify IDs
        logs = ImportLog.query.filter_by(
            import_job_id=import_job_id,
            status=ImportLogStatus.SUCCESS.value
        ).filter(
            ImportLog.shopify_product_id.isnot(None)
        ).all()
        
        mappings = []
        for log in logs:
            # product_identifier is the SKU
            mappings.append((log.product_identifier, log.shopify_product_id))
        
        logger.info(f"Collected {len(mappings)} SKU -> Shopify ID mappings")
        return mappings
    
    def create_writeback_rule(
        self,
        mappings: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        """
        Create batch_rewriting rule to write Shopify IDs.
        
        Args:
            mappings: List of (sku, shopify_product_id) tuples
            
        Returns:
            Created rule data
        """
        if not mappings:
            logger.warning("No mappings to write back")
            return {}
        
        # Ensure element exists
        element_id = self.ensure_shopify_id_element()
        
        # Build batch_rewriting data format
        # Format: [["source_value", "target_value"], ...]
        batch_data = [[sku, shopify_id] for sku, shopify_id in mappings]
        
        # Create empty query (applies to all products)
        query_response = self.client.create_query(
            self.project.mergado_project_id,
            query='',  # Empty query = all products
            name=f'{self.RULE_NAME_PREFIX} - All Products'
        )
        
        query_id = query_response['id']
        
        # Create batch_rewriting rule
        rule_name = f'{self.RULE_NAME_PREFIX} ({len(mappings)} products)'
        
        rule = self.client.create_rule(
            project_id=self.project.mergado_project_id,
            rule_type='batch_rewriting',
            element_path=self.SHOPIFY_ID_ELEMENT_NAME,
            data=batch_data,
            queries=[{'id': query_id}],
            name=rule_name,
            applies=True
        )
        
        logger.info(f"Created batch_rewriting rule: {rule.get('id')} with {len(mappings)} mappings")
        
        # Mark project dirty to trigger rule application
        self.client.mark_project_dirty(self.project.mergado_project_id)
        logger.info(f"Marked project {self.project.mergado_project_id} dirty")
        
        return rule
    
    def writeback_from_import_job(self, import_job_id: int) -> Dict[str, Any]:
        """
        Execute full writeback workflow from import job.
        
        Args:
            import_job_id: Import job ID
            
        Returns:
            Dict with writeback summary
        """
        logger.info(f"Starting Shopify ID writeback for import job {import_job_id}")
        
        try:
            # Collect mappings
            mappings = self.collect_sku_mappings(import_job_id)
            
            if not mappings:
                return {
                    'success': True,
                    'mappings_count': 0,
                    'message': 'No Shopify IDs to write back'
                }
            
            # Create rule
            rule = self.create_writeback_rule(mappings)
            
            return {
                'success': True,
                'mappings_count': len(mappings),
                'rule_id': rule.get('id'),
                'element_id': self.project.shopify_id_element_id,
                'message': f'Wrote back {len(mappings)} Shopify IDs'
            }
            
        except APIError as e:
            logger.error(f"Writeback failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Writeback failed'
            }
