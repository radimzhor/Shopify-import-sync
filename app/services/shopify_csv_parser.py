"""
Shopify CSV Parser - parses Shopify CSV format with metafields and variants.

Handles the complex Shopify CSV format with product grouping, variants,
and custom metafields according to Shopify's import specification.
"""
import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterator
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class ShopifyVariant:
    """Single product variant from CSV."""
    sku: str
    price: Optional[str] = None
    inventory_qty: Optional[str] = None
    inventory_tracker: Optional[str] = None
    inventory_policy: Optional[str] = None
    fulfillment_service: Optional[str] = None
    requires_shipping: Optional[str] = None
    grams: Optional[str] = None
    barcode: Optional[str] = None
    image_src: Optional[str] = None
    
    # Options (up to 3)
    option1_name: Optional[str] = None
    option1_value: Optional[str] = None
    option2_name: Optional[str] = None
    option2_value: Optional[str] = None
    option3_name: Optional[str] = None
    option3_value: Optional[str] = None
    
    # Raw row for additional fields
    raw_data: Dict[str, str] = field(default_factory=dict)


@dataclass
class ShopifyProduct:
    """Product with all variants and metadata from CSV."""
    handle: str
    title: str
    body_html: Optional[str] = None
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    tags: Optional[str] = None
    published: Optional[str] = None
    status: Optional[str] = None
    
    # SEO
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    
    # Images (product-level)
    image_src: List[str] = field(default_factory=list)
    
    # Metafields (dict of namespace.key: value)
    metafields: Dict[str, str] = field(default_factory=dict)
    
    # Variants
    variants: List[ShopifyVariant] = field(default_factory=list)
    
    # Raw first row for reference
    raw_data: Dict[str, str] = field(default_factory=dict)


class ShopifyCSVParser:
    """
    Parser for Shopify CSV import format.
    
    Handles the multi-row format where:
    - First row has product-level data
    - Subsequent rows with same handle are variants
    - Metafields use format "Name (product.metafields.custom.key)"
    """
    
    # Standard Shopify column mappings
    PRODUCT_COLUMNS = {
        'Handle', 'Title', 'Body (HTML)', 'Vendor', 'Type', 'Tags',
        'Published', 'Status', 'SEO Title', 'SEO Description', 'Image Src'
    }
    
    VARIANT_COLUMNS = {
        'Variant SKU', 'Variant Grams', 'Variant Inventory Tracker',
        'Variant Inventory Qty', 'Variant Inventory Policy',
        'Variant Fulfillment Service', 'Variant Price',
        'Variant Requires Shipping', 'Variant Barcode', 'Variant Image',
        'Option1 Name', 'Option1 Value', 'Option2 Name', 'Option2 Value',
        'Option3 Name', 'Option3 Value'
    }
    
    def __init__(self, csv_path: Path):
        """
        Initialize parser with CSV file.
        
        Args:
            csv_path: Path to Shopify CSV file
        """
        self.csv_path = csv_path
        self._metafield_columns = []
        self._other_columns = []
    
    def _detect_metafield_columns(self, headers: List[str]) -> None:
        """
        Detect metafield columns from headers.
        
        Metafield columns use format: "Name (product.metafields.custom.key)"
        """
        self._metafield_columns = []
        self._other_columns = []
        
        for header in headers:
            if '(product.metafields.custom.' in header:
                # Extract metafield key
                start = header.find('(product.metafields.custom.') + len('(product.metafields.custom.')
                end = header.find(')', start)
                if end > start:
                    key = header[start:end]
                    self._metafield_columns.append((header, key))
            elif header not in self.PRODUCT_COLUMNS and header not in self.VARIANT_COLUMNS:
                self._other_columns.append(header)
    
    def _parse_variant(self, row: Dict[str, str]) -> ShopifyVariant:
        """
        Parse variant data from CSV row.
        
        Args:
            row: CSV row as dict
            
        Returns:
            ShopifyVariant instance
        """
        return ShopifyVariant(
            sku=row.get('Variant SKU', ''),
            price=row.get('Variant Price'),
            inventory_qty=row.get('Variant Inventory Qty'),
            inventory_tracker=row.get('Variant Inventory Tracker'),
            inventory_policy=row.get('Variant Inventory Policy'),
            fulfillment_service=row.get('Variant Fulfillment Service'),
            requires_shipping=row.get('Variant Requires Shipping'),
            grams=row.get('Variant Grams'),
            barcode=row.get('Variant Barcode'),
            image_src=row.get('Variant Image'),
            option1_name=row.get('Option1 Name'),
            option1_value=row.get('Option1 Value'),
            option2_name=row.get('Option2 Name'),
            option2_value=row.get('Option2 Value'),
            option3_name=row.get('Option3 Name'),
            option3_value=row.get('Option3 Value'),
            raw_data=row
        )
    
    def _parse_product_base(self, row: Dict[str, str]) -> ShopifyProduct:
        """
        Parse product-level data from first row.
        
        Args:
            row: CSV row as dict
            
        Returns:
            ShopifyProduct instance (without variants)
        """
        # Extract metafields
        metafields = {}
        for column_name, metafield_key in self._metafield_columns:
            value = row.get(column_name, '').strip()
            if value:
                metafields[f'custom.{metafield_key}'] = value
        
        # Parse image sources
        image_src = []
        if row.get('Image Src'):
            image_src.append(row['Image Src'])
        
        return ShopifyProduct(
            handle=row.get('Handle', ''),
            title=row.get('Title', ''),
            body_html=row.get('Body (HTML)'),
            vendor=row.get('Vendor'),
            product_type=row.get('Type'),
            tags=row.get('Tags'),
            published=row.get('Published'),
            status=row.get('Status'),
            seo_title=row.get('SEO Title'),
            seo_description=row.get('SEO Description'),
            image_src=image_src,
            metafields=metafields,
            raw_data=row
        )
    
    def parse(self) -> Iterator[ShopifyProduct]:
        """
        Parse CSV file and yield products.
        
        Yields:
            ShopifyProduct instances with all variants
            
        Note:
            Products with the same handle are grouped together.
            First row with handle has product data, subsequent rows are variants.
        """
        logger.info(f"Parsing Shopify CSV: {self.csv_path}")
        
        current_product: Optional[ShopifyProduct] = None
        products_parsed = 0
        
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Detect metafield columns from header
            if reader.fieldnames:
                self._detect_metafield_columns(list(reader.fieldnames))
                logger.info(f"Detected {len(self._metafield_columns)} metafield columns")
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                handle = row.get('Handle', '').strip()
                
                if not handle:
                    # Empty handle = variant row (continue current product)
                    if current_product:
                        variant = self._parse_variant(row)
                        if variant.sku:  # Only add variants with SKU
                            current_product.variants.append(variant)
                    continue
                
                # New product (handle is present)
                if current_product:
                    # Yield previous product
                    products_parsed += 1
                    yield current_product
                
                # Start new product
                current_product = self._parse_product_base(row)
                
                # First row also contains first variant
                variant = self._parse_variant(row)
                if variant.sku:
                    current_product.variants.append(variant)
                
                # Add image from first row
                if row.get('Image Src') and row['Image Src'] not in current_product.image_src:
                    current_product.image_src.append(row['Image Src'])
            
            # Yield last product
            if current_product:
                products_parsed += 1
                yield current_product
        
        logger.info(f"Parsed {products_parsed} products from CSV")
    
    def parse_all(self) -> List[ShopifyProduct]:
        """
        Parse entire CSV and return list of products.
        
        Returns:
            List of ShopifyProduct instances
        """
        return list(self.parse())
    
    def get_sku_list(self) -> List[str]:
        """
        Quick parse to extract only SKUs from CSV.
        
        Returns:
            List of all SKUs found in CSV
        """
        skus = []
        
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sku = row.get('Variant SKU', '').strip()
                if sku:
                    skus.append(sku)
        
        logger.info(f"Extracted {len(skus)} SKUs from CSV")
        return skus
