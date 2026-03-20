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
    
    # Variant-level metafields (namespace.key: value)
    metafields: Dict[str, str] = field(default_factory=dict)
    
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
    
    # Options (list of option names, e.g., ['Color', 'Size'])
    options: List[str] = field(default_factory=list)
    
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
        self._option_columns = []
    
    def _detect_metafield_columns(self, headers: List[str]) -> None:
        """
        Detect metafield columns from headers.
        
        Metafield columns use format: "Name (product.metafields.custom.key)"
        """
        self._metafield_columns = []
        self._other_columns = []
        
        for header in headers:
            if '(product.metafields.custom.' in header:
                start = header.find('(product.metafields.custom.') + len('(product.metafields.custom.')
                end = header.find(')', start)
                if end > start:
                    key = header[start:end]
                    self._metafield_columns.append((header, key))
            elif header not in self.PRODUCT_COLUMNS and header not in self.VARIANT_COLUMNS:
                self._other_columns.append(header)
    
    def _detect_option_columns(self, rows: List[Dict[str, str]]) -> List[str]:
        """
        Detect which metafield columns should be used as product options.
        
        Scans metafield columns to find up to 3 that contain non-empty values
        in at least one row. These become the product's variant options.
        
        Args:
            rows: All CSV rows for this product
            
        Returns:
            List of up to 3 option names (e.g., ['Barva', 'Velikost'])
        """
        option_columns = []
        
        for column_name, metafield_key in self._metafield_columns:
            if len(option_columns) >= 3:
                break
            
            has_values = any(row.get(column_name, '').strip() for row in rows)
            if has_values:
                option_name = column_name.split(' (')[0]
                option_columns.append(option_name)
                logger.debug(f"Using metafield column '{column_name}' as option '{option_name}'")
        
        return option_columns
    
    def _build_product_from_rows(self, handle: str, rows: List[Dict[str, str]]) -> Optional[ShopifyProduct]:
        """
        Build complete product from all its CSV rows.
        
        This method:
        1. Parses product-level data from first row
        2. Detects dynamic options from metafield columns
        3. Builds variants with option values
        4. Adds variant metafields matched by option values
        5. Collects images from both Image Src and Variant Image
        6. Creates default variant if no variants exist
        
        Args:
            handle: Product handle
            rows: All CSV rows for this product
            
        Returns:
            Complete ShopifyProduct or None if invalid
        """
        if not rows:
            return None
        
        first_row = rows[0]
        product = self._parse_product_base(first_row)
        
        option_columns = self._detect_option_columns(rows)
        product.options = option_columns
        
        all_image_urls = set()
        
        variants = []
        for row in rows:
            if row.get('Image Src'):
                all_image_urls.add(row['Image Src'])
            if row.get('Variant Image'):
                all_image_urls.add(row['Variant Image'])
            
            sku = row.get('Variant SKU', '').strip()
            if not sku:
                continue
            
            has_option_values = False
            if option_columns:
                for column_name, _ in self._metafield_columns:
                    if column_name.split(' (')[0] in option_columns:
                        if row.get(column_name, '').strip():
                            has_option_values = True
                            break
            
            if not option_columns or has_option_values:
                variant = self._parse_variant_with_options(row, option_columns)
                if variant:
                    variants.append(variant)
        
        product.image_src = list(all_image_urls)
        
        if not variants and rows:
            logger.debug(f"No variants found for product {handle}, creating default variant")
            default_variant = self._parse_variant(first_row)
            default_variant.option1_name = None
            default_variant.option1_value = None
            default_variant.option2_name = None
            default_variant.option2_value = None
            default_variant.option3_name = None
            default_variant.option3_value = None
            if default_variant.sku:
                variants.append(default_variant)
        
        if not option_columns and len(variants) > 0:
            variants = [variants[0]]
            variants[0].option1_name = None
            variants[0].option1_value = None
            variants[0].option2_name = None
            variants[0].option2_value = None
            variants[0].option3_name = None
            variants[0].option3_value = None
        
        product.variants = variants
        
        self._assign_variant_metafields(product, rows, option_columns)
        
        return product
    
    def _parse_variant_with_options(
        self, 
        row: Dict[str, str], 
        option_columns: List[str]
    ) -> Optional[ShopifyVariant]:
        """
        Parse variant with dynamic options from metafield columns.
        
        Args:
            row: CSV row
            option_columns: List of option names to use
            
        Returns:
            ShopifyVariant with options set
        """
        variant = self._parse_variant(row)
        
        if option_columns:
            for idx, option_name in enumerate(option_columns):
                for column_name, _ in self._metafield_columns:
                    if column_name.split(' (')[0] == option_name:
                        value = row.get(column_name, '').strip()
                        if value:
                            if idx == 0:
                                variant.option1_name = option_name
                                variant.option1_value = value
                            elif idx == 1:
                                variant.option2_name = option_name
                                variant.option2_value = value
                            elif idx == 2:
                                variant.option3_name = option_name
                                variant.option3_value = value
                        break
        
        return variant
    
    def _assign_variant_metafields(
        self,
        product: ShopifyProduct,
        rows: List[Dict[str, str]],
        option_columns: List[str]
    ) -> None:
        """
        Assign metafields to variants by matching option values.
        
        For each variant, finds its matching CSV row by comparing option values,
        then extracts and assigns metafields from that row.
        
        Args:
            product: Product with variants
            rows: All CSV rows for this product
            option_columns: List of option names used
        """
        option_column_names = []
        for option_name in option_columns:
            for column_name, _ in self._metafield_columns:
                if column_name.split(' (')[0] == option_name:
                    option_column_names.append(column_name)
                    break
        
        for variant in product.variants:
            matching_row = None
            
            for row in rows:
                if row.get('Variant SKU', '').strip() != variant.sku:
                    continue
                
                if not option_column_names:
                    matching_row = row
                    break
                
                match = True
                for idx, column_name in enumerate(option_column_names):
                    option_value = row.get(column_name, '').strip()
                    variant_option_value = None
                    if idx == 0:
                        variant_option_value = variant.option1_value
                    elif idx == 1:
                        variant_option_value = variant.option2_value
                    elif idx == 2:
                        variant_option_value = variant.option3_value
                    
                    if option_value != (variant_option_value or ''):
                        match = False
                        break
                
                if match:
                    matching_row = row
                    break
            
            if matching_row:
                metafields = {}
                for column_name, metafield_key in self._metafield_columns:
                    value = matching_row.get(column_name, '').strip()
                    if value:
                        metafields[f'custom.{metafield_key}'] = value
                variant.metafields = metafields
    
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
            Dynamically detects options from metafield columns.
        """
        logger.info(f"Parsing Shopify CSV: {self.csv_path}")
        
        products_parsed = 0
        
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            if reader.fieldnames:
                self._detect_metafield_columns(list(reader.fieldnames))
                logger.info(f"Detected {len(self._metafield_columns)} metafield columns")
            
            current_handle = None
            current_rows = []
            
            for row_num, row in enumerate(reader, start=2):
                handle = row.get('Handle', '').strip()
                
                if not handle:
                    if current_rows:
                        current_rows.append(row)
                    continue
                
                if current_handle and current_rows:
                    product = self._build_product_from_rows(current_handle, current_rows)
                    if product:
                        products_parsed += 1
                        yield product
                
                current_handle = handle
                current_rows = [row]
            
            if current_handle and current_rows:
                product = self._build_product_from_rows(current_handle, current_rows)
                if product:
                    products_parsed += 1
                    yield product
        
        logger.info(f"Parsed {products_parsed} products from CSV")
        
    
    def parse_all(self) -> List[ShopifyProduct]:
        """
        Parse entire CSV and return list of products.
        
        Returns:
            List of ShopifyProduct instances
        """
        products = list(self.parse())
        logger.info(f"Total products parsed: {len(products)}")
        
        # Log summary
        total_variants = sum(len(p.variants) for p in products)
        products_with_sku = sum(1 for p in products if any(v.sku for v in p.variants))
        logger.info(f"Products with SKUs: {products_with_sku}/{len(products)}, Total variants: {total_variants}")
        
        # Log first product details for debugging
        if products:
            first = products[0]
            logger.debug(f"First product: handle={first.handle}, title={first.title}, variants={len(first.variants)}")
            if first.variants:
                logger.debug(f"First variant: sku={first.variants[0].sku}, price={first.variants[0].price}")
        
        return products
    
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
