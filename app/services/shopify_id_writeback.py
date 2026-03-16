"""
Shopify ID Writeback - writes Shopify product IDs back to Mergado.

Workflow per import job:
1. Upsert SKU -> Shopify ID mappings into ShopifyIDMapping table
2. Ensure the shopify_id element exists in the Mergado project
3. Ensure a custom app rule instance exists on the project (created once, reused)

The actual writing of values happens when Mergado applies rules: it calls
POST /api/rules/shopify-id-writeback with a batch of products, and we return
the shopify_id values from ShopifyIDMapping.
"""
import logging
from typing import Dict, Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db
from app.models.project import Project
from app.models.import_log import ImportLog, ImportLogStatus
from app.models.shopify_id_mapping import ShopifyIDMapping
from app.services.mergado_client import MergadoClient
from app.services.exceptions import APIError
from settings import settings


logger = logging.getLogger(__name__)


class ShopifyIDWriteback:
    """
    Manages Shopify ID writeback to Mergado via a custom app rule.

    After each import:
    1. Mappings are upserted into ShopifyIDMapping (fast lookup table)
    2. A single custom app rule is created on the project (once ever)

    Mergado then calls our /api/rules/shopify-id-writeback endpoint whenever
    it applies rules, and we return current shopify_id values for each product.
    """

    SHOPIFY_ID_ELEMENT_NAME = 'shopify_id'

    def __init__(self, mergado_client: MergadoClient, project: Project):
        self.client = mergado_client
        self.project = project

    # -------------------------------------------------------------------------
    # Step 1: Upsert mappings into ShopifyIDMapping
    # -------------------------------------------------------------------------

    def upsert_sku_mappings(self, import_job_id: int) -> int:
        """
        Upsert SKU -> Shopify ID mappings from a completed import job.

        Reads all successful ImportLog entries that have a shopify_product_id,
        then upserts them into ShopifyIDMapping (insert or update on conflict).

        Args:
            import_job_id: Completed import job ID

        Returns:
            Number of mappings upserted
        """
        logs = ImportLog.query.filter_by(
            import_job_id=import_job_id,
            status=ImportLogStatus.SUCCESS.value
        ).filter(
            ImportLog.shopify_product_id.isnot(None)
        ).all()

        if not logs:
            logger.info(f"No successful import logs with Shopify IDs for job {import_job_id}")
            return 0

        rows = [
            {
                'project_id': self.project.id,
                'sku': log.product_identifier,
                'shopify_product_id': log.shopify_product_id,
                'shopify_variant_id': log.shopify_variant_id,
                'updated_at': db.func.now(),
            }
            for log in logs
        ]

        dialect = db.engine.dialect.name
        if dialect == 'postgresql':
            stmt = pg_insert(ShopifyIDMapping).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint='uq_shopify_id_mapping_project_sku',
                set_={
                    'shopify_product_id': stmt.excluded.shopify_product_id,
                    'shopify_variant_id': stmt.excluded.shopify_variant_id,
                    'updated_at': stmt.excluded.updated_at,
                }
            )
        else:
            stmt = sqlite_insert(ShopifyIDMapping).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=['project_id', 'sku'],
                set_={
                    'shopify_product_id': stmt.excluded.shopify_product_id,
                    'shopify_variant_id': stmt.excluded.shopify_variant_id,
                    'updated_at': stmt.excluded.updated_at,
                }
            )

        db.session.execute(stmt)
        db.session.commit()
        logger.info(f"Upserted {len(rows)} SKU mappings for project {self.project.mergado_project_id}")
        return len(rows)

    # -------------------------------------------------------------------------
    # Step 2: Ensure shopify_id element exists
    # -------------------------------------------------------------------------

    def ensure_shopify_id_element(self) -> str:
        """
        Ensure the shopify_id element exists in the Mergado project.

        Checks the stored element ID first. If missing, lists project elements
        (returned as a name-keyed dict) to find it, or creates it.

        Returns:
            Element ID string
        """
        if self.project.shopify_id_element_id:
            logger.info(f"Using existing shopify_id element: {self.project.shopify_id_element_id}")
            return self.project.shopify_id_element_id

        # API returns a dict keyed by element name: {"shopify_id": {"id": "42", ...}, ...}
        elements_dict = self.client.get_project_elements(self.project.mergado_project_id)

        if self.SHOPIFY_ID_ELEMENT_NAME in elements_dict:
            element_data = elements_dict[self.SHOPIFY_ID_ELEMENT_NAME]
            element_id = str(element_data['id'])
            logger.info(f"Found existing shopify_id element: {element_id}")
            self.project.shopify_id_element_id = element_id
            db.session.commit()
            return element_id

        # Element does not exist - create it
        logger.info(f"Creating shopify_id element in project {self.project.mergado_project_id}")
        element = self.client.create_element(
            self.project.mergado_project_id,
            name=self.SHOPIFY_ID_ELEMENT_NAME,
            hidden=False
        )

        element_id = str(element.get('id', ''))
        if not element_id:
            raise APIError("create_element response did not contain an element ID")

        logger.info(f"Created shopify_id element: {element_id}")
        self.project.shopify_id_element_id = element_id
        db.session.commit()
        return element_id

    # -------------------------------------------------------------------------
    # Step 3: Ensure custom app rule instance exists on the project
    # -------------------------------------------------------------------------

    def ensure_app_rule(self) -> str:
        """
        Ensure a custom app rule instance exists on the Mergado project.

        The rule is created once and its ID stored on the project. On subsequent
        imports, the stored rule ID is reused (no duplicate rules created).

        Returns:
            Mergado rule ID string
        """
        # Check if we have a stored rule ID
        if self.project.shopify_writeback_rule_id:
            # Verify the rule still exists in Mergado (user may have deleted it)
            existing_rule = self.client.get_rule(
                self.project.mergado_project_id,
                self.project.shopify_writeback_rule_id
            )
            if existing_rule:
                logger.info(f"Using existing writeback rule: {self.project.shopify_writeback_rule_id}")
                return self.project.shopify_writeback_rule_id
            else:
                logger.warning(
                    f"Stored rule {self.project.shopify_writeback_rule_id} no longer exists in Mergado, "
                    f"will create a new one"
                )
                self.project.shopify_writeback_rule_id = None

        logger.info(f"Creating writeback app rule for project {self.project.mergado_project_id}")

        # Find the "all products" query (exists in every project by default)
        # The query ID varies per project, so we need to look it up
        queries = self.client.get_queries(self.project.mergado_project_id)
        all_products_query_id = None
        
        for query in queries:
            # Match by name (common variations) or by the special identifier
            query_name = query.get('name', '').lower()
            query_id_str = str(query.get('id', ''))
            
            if ('all' in query_name and 'product' in query_name) or query_id_str == '♥ALLPRODUCTS♥':
                all_products_query_id = str(query.get('id'))
                logger.info(f"Found all-products query: {all_products_query_id}")
                break
        
        if not all_products_query_id:
            raise APIError(
                "Could not find 'all products' query in project. "
                "Every Mergado project should have this query by default."
            )

        # Create the app rule with the all-products query
        rule = self.client.create_rule(
            project_id=self.project.mergado_project_id,
            rule_type='app',
            element_path=None,
            data={'app_rule_type': settings.mergado_writeback_rule_type},
            queries=[{'id': all_products_query_id}],
            name='Shopify ID Writeback',
            applies=True,
            priority='1',
        )

        rule_id = str(rule.get('id', ''))
        if not rule_id:
            raise APIError("create_rule response did not contain a rule ID")

        logger.info(f"Created writeback app rule: {rule_id}")
        self.project.shopify_writeback_rule_id = rule_id
        db.session.commit()
        return rule_id

    # -------------------------------------------------------------------------
    # Public entry point
    # -------------------------------------------------------------------------

    def writeback_from_import_job(self, import_job_id: int) -> Dict[str, Any]:
        """
        Execute full writeback setup after an import job completes.

        Steps:
        1. Upsert SKU -> Shopify ID mappings
        2. Ensure shopify_id element exists
        3. Ensure custom app rule instance exists on the project

        Args:
            import_job_id: Completed import job ID

        Returns:
            Dict with writeback summary
        """
        logger.info(f"Starting Shopify ID writeback for import job {import_job_id}")

        try:
            mappings_count = self.upsert_sku_mappings(import_job_id)

            if mappings_count == 0:
                return {
                    'success': True,
                    'mappings_count': 0,
                    'message': 'No Shopify IDs to write back',
                }

            self.ensure_shopify_id_element()
            rule_id = self.ensure_app_rule()

            logger.info(
                f"Writeback completed successfully for job {import_job_id}: "
                f"{mappings_count} mappings, rule {rule_id}"
            )

            return {
                'success': True,
                'mappings_count': mappings_count,
                'rule_id': rule_id,
                'element_id': self.project.shopify_id_element_id,
                'message': f'Stored {mappings_count} Shopify ID mappings; rule {rule_id} active',
            }

        except APIError as e:
            logger.error(f"Writeback failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Writeback failed',
            }
