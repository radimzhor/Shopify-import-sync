"""
Product Matcher - matches Mergado products with Shopify by SKU.

Determines which products need to be created vs updated based on SKU matching.
"""
import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from app.services.shopify_csv_parser import ShopifyProduct, ShopifyVariant
from app.services.shopify_service import ShopifyService
from app.services.exceptions import APIError


logger = logging.getLogger(__name__)


class MatchAction(str, Enum):
    """Action to take for a product/variant."""
    CREATE = 'create'
    UPDATE = 'update'
    SKIP = 'skip'


@dataclass
class VariantMatch:
    """Match result for a single variant."""
    csv_variant: ShopifyVariant
    action: MatchAction
    shopify_product_id: Optional[str] = None
    shopify_variant_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class ProductMatch:
    """Match result for a product with all variants."""
    csv_product: ShopifyProduct
    action: MatchAction
    shopify_product_id: Optional[str] = None
    variant_matches: List[VariantMatch] = None
    reason: Optional[str] = None
    
    def __post_init__(self):
        if self.variant_matches is None:
            self.variant_matches = []
    
    @property
    def primary_sku(self) -> Optional[str]:
        """Get primary SKU (first variant)."""
        if self.csv_product.variants:
            return self.csv_product.variants[0].sku
        return None


@dataclass
class MatchPreview:
    """Summary of matching results."""
    total_products: int
    products_to_create: int
    products_to_update: int
    products_to_skip: int
    total_variants: int
    variants_to_create: int
    variants_to_update: int
    variants_to_skip: int
    matches: List[ProductMatch] = None
    
    def __post_init__(self):
        if self.matches is None:
            self.matches = []
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for JSON responses."""
        return {
            'total_products': self.total_products,
            'products_to_create': self.products_to_create,
            'products_to_update': self.products_to_update,
            'products_to_skip': self.products_to_skip,
            'total_variants': self.total_variants,
            'variants_to_create': self.variants_to_create,
            'variants_to_update': self.variants_to_update,
            'variants_to_skip': self.variants_to_skip,
        }


class ProductMatcher:
    """
    Matches CSV products with existing Shopify products by SKU.
    
    Strategy:
    1. Extract all SKUs from CSV
    2. Query Shopify for products with those SKUs
    3. Build SKU -> Shopify product/variant mapping
    4. For each CSV product, determine action based on matches
    """
    
    def __init__(self, shopify_service: ShopifyService):
        """
        Initialize product matcher.
        
        Args:
            shopify_service: Initialized ShopifyService instance
        """
        self.shopify = shopify_service
        self._sku_map: Dict[str, Tuple[str, str]] = {}  # sku -> (product_id, variant_id)
    
    def _build_sku_map(self, skus: List[str]) -> None:
        """
        Build mapping of SKU -> (product_id, variant_id) from Shopify.
        
        Args:
            skus: List of SKUs to query
        """
        logger.info(f"Building SKU map for {len(skus)} SKUs")
        self._sku_map = {}
        
        # Query Shopify products in batches
        # Note: Shopify has no bulk SKU query, so we need to list all products
        # For MVP, we'll fetch all products. For production, consider caching or GraphQL.
        
        page_info = None
        total_fetched = 0
        
        try:
            while True:
                result = self.shopify.list_products(limit=250, page_info=page_info)
                products = result['products']
                
                if not products:
                    break
                
                # Build SKU map from products
                for product in products:
                    product_id = str(product['id'])
                    for variant in product.get('variants', []):
                        variant_sku = variant.get('sku')
                        if variant_sku:
                            variant_id = str(variant['id'])
                            self._sku_map[variant_sku] = (product_id, variant_id)
                
                total_fetched += len(products)
                page_info = result.get('next_page_info')
                
                if not page_info:
                    break
            
            logger.info(f"Fetched {total_fetched} Shopify products, mapped {len(self._sku_map)} SKUs")
            
        except APIError as e:
            logger.error(f"Failed to build SKU map: {e}")
            raise
    
    def match_products(
        self,
        csv_products: List[ShopifyProduct],
        force_create: bool = False
    ) -> List[ProductMatch]:
        """
        Match CSV products with Shopify products.
        
        Args:
            csv_products: Products parsed from CSV
            force_create: If True, skip Shopify lookup and create all products
            
        Returns:
            List of ProductMatch results
        """
        logger.info(f"Matching {len(csv_products)} CSV products")
        
        # Validate CSV products before matching
        if not csv_products:
            logger.warning("No CSV products to match!")
            return []
        
        # Extract all SKUs from CSV
        all_skus = []
        products_without_variants = 0
        products_without_skus = 0
        
        for product in csv_products:
            if not product.variants:
                products_without_variants += 1
                continue
            
            has_sku = False
            for variant in product.variants:
                if variant.sku:
                    all_skus.append(variant.sku)
                    has_sku = True
            
            if not has_sku:
                products_without_skus += 1
        
        logger.info(f"Extracted {len(all_skus)} SKUs from CSV")
        if products_without_variants > 0:
            logger.warning(f"{products_without_variants} products have no variants")
        if products_without_skus > 0:
            logger.warning(f"{products_without_skus} products have no SKUs in variants")
        
        # Build SKU map from Shopify (unless force_create)
        if not force_create:
            self._build_sku_map(all_skus)
        
        # Match each product
        matches = []
        for csv_product in csv_products:
            match = self._match_product(csv_product, force_create)
            matches.append(match)
        
        return matches
    
    def _match_product(
        self,
        csv_product: ShopifyProduct,
        force_create: bool = False
    ) -> ProductMatch:
        """
        Match single product with Shopify.
        
        Args:
            csv_product: Product from CSV
            force_create: Force creation without checking existence
            
        Returns:
            ProductMatch result
        """
        # Skip products without variants
        if not csv_product.variants:
            return ProductMatch(
                csv_product=csv_product,
                action=MatchAction.SKIP,
                reason="No variants found"
            )
        
        # Skip products without SKUs
        if not any(v.sku for v in csv_product.variants):
            return ProductMatch(
                csv_product=csv_product,
                action=MatchAction.SKIP,
                reason="No SKUs in variants"
            )
        
        # Force create mode
        if force_create:
            return ProductMatch(
                csv_product=csv_product,
                action=MatchAction.CREATE,
                variant_matches=[
                    VariantMatch(csv_variant=v, action=MatchAction.CREATE)
                    for v in csv_product.variants
                ],
                reason="Force create mode"
            )
        
        # Check if any variant SKU exists in Shopify
        variant_matches = []
        shopify_product_ids = set()
        
        for csv_variant in csv_product.variants:
            if not csv_variant.sku:
                variant_matches.append(VariantMatch(
                    csv_variant=csv_variant,
                    action=MatchAction.SKIP,
                    reason="No SKU"
                ))
                continue
            
            # Check if SKU exists in Shopify
            if csv_variant.sku in self._sku_map:
                product_id, variant_id = self._sku_map[csv_variant.sku]
                shopify_product_ids.add(product_id)
                
                variant_matches.append(VariantMatch(
                    csv_variant=csv_variant,
                    action=MatchAction.UPDATE,
                    shopify_product_id=product_id,
                    shopify_variant_id=variant_id,
                    reason=f"SKU exists in Shopify"
                ))
            else:
                variant_matches.append(VariantMatch(
                    csv_variant=csv_variant,
                    action=MatchAction.CREATE,
                    reason="New SKU"
                ))
        
        # Determine product-level action
        if len(shopify_product_ids) > 1:
            # Multiple existing products with same SKUs - complex case, skip for MVP
            return ProductMatch(
                csv_product=csv_product,
                action=MatchAction.SKIP,
                variant_matches=variant_matches,
                reason=f"Variants belong to {len(shopify_product_ids)} different products"
            )
        
        if len(shopify_product_ids) == 1:
            # All matching variants belong to same product - UPDATE
            shopify_product_id = list(shopify_product_ids)[0]
            return ProductMatch(
                csv_product=csv_product,
                action=MatchAction.UPDATE,
                shopify_product_id=shopify_product_id,
                variant_matches=variant_matches,
                reason="Product exists in Shopify"
            )
        
        # No variants exist in Shopify - CREATE
        return ProductMatch(
            csv_product=csv_product,
            action=MatchAction.CREATE,
            variant_matches=variant_matches,
            reason="New product"
        )
    
    def generate_preview(
        self,
        matches: List[ProductMatch]
    ) -> MatchPreview:
        """
        Generate summary preview of matching results.
        
        Args:
            matches: List of product matches
            
        Returns:
            MatchPreview with counts and statistics
        """
        preview = MatchPreview(
            total_products=len(matches),
            products_to_create=sum(1 for m in matches if m.action == MatchAction.CREATE),
            products_to_update=sum(1 for m in matches if m.action == MatchAction.UPDATE),
            products_to_skip=sum(1 for m in matches if m.action == MatchAction.SKIP),
            total_variants=sum(len(m.csv_product.variants) for m in matches),
            variants_to_create=0,
            variants_to_update=0,
            variants_to_skip=0,
            matches=matches
        )
        
        # Count variant actions
        for match in matches:
            for vm in match.variant_matches:
                if vm.action == MatchAction.CREATE:
                    preview.variants_to_create += 1
                elif vm.action == MatchAction.UPDATE:
                    preview.variants_to_update += 1
                elif vm.action == MatchAction.SKIP:
                    preview.variants_to_skip += 1
        
        logger.info(
            f"Match preview: {preview.products_to_create} create, "
            f"{preview.products_to_update} update, {preview.products_to_skip} skip"
        )
        
        return preview
