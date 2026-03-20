"""
Tests for service layer components.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.services.mergado_client import MergadoClient
from app.services.shopify_service import ShopifyService
from app.services.csv_downloader import CSVDownloader
from app.services.shopify_csv_parser import ShopifyCSVParser, ShopifyProduct
from app.services.product_matcher import ProductMatcher, MatchAction
from app.services.exceptions import APIError, AuthenticationError


class TestMergadoClient:
    """Tests for MergadoClient."""
    
    def test_initialization(self):
        """Test client initialization."""
        client = MergadoClient(access_token="test_token")
        assert client.access_token == "test_token"
        assert client.base_url == "https://api.mergado.com"
    
    @patch('requests.request')
    def test_get_shop(self, mock_request):
        """Test get_shop API call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': '123', 'name': 'Test Shop'}
        mock_request.return_value = mock_response
        
        client = MergadoClient(access_token="test_token")
        result = client.get_shop('123')
        
        assert result['id'] == '123'
        assert result['name'] == 'Test Shop'
        mock_request.assert_called_once()
    
    @patch('requests.request')
    def test_authentication_error(self, mock_request):
        """Test 401 raises AuthenticationError."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("401")
        mock_request.return_value = mock_response
        
        client = MergadoClient(access_token="invalid_token")
        
        with pytest.raises(AuthenticationError):
            client.get_shop('123')


class TestShopifyService:
    """Tests for ShopifyService."""
    
    def test_initialization(self):
        """Test service initialization."""
        client = MergadoClient(access_token="test_token")
        service = ShopifyService(client, shop_id="456")
        
        assert service.shop_id == "456"
        assert service.client == client
    
    def test_api_path_building(self):
        """Test API path building."""
        client = MergadoClient(access_token="test_token")
        service = ShopifyService(client, shop_id="456")
        
        path = service._api_path('products.json')
        assert path == 'admin/api/2024-01/products.json'
        
        path = service._api_path('/products.json')
        assert path == 'admin/api/2024-01/products.json'


class TestCSVDownloader:
    """Tests for CSVDownloader."""
    
    def test_initialization(self):
        """Test downloader initialization."""
        downloader = CSVDownloader()
        assert downloader.cache_dir is not None
        assert downloader.timeout == 300
    
    def test_get_cached_path(self):
        """Test cache path generation returns None for non-existent cache."""
        downloader = CSVDownloader()
        path = downloader.get_cached_path("project_123")
        assert path is None or not path.exists()


class TestShopifyCSVParser:
    """Tests for ShopifyCSVParser."""
    
    @pytest.fixture
    def sample_csv(self, tmp_path):
        """Create sample CSV file for testing."""
        csv_path = tmp_path / "test.csv"
        csv_content = """Handle,Title,Body (HTML),Vendor,Variant SKU,Variant Price
test-product,Test Product,Description,Test Vendor,SKU123,29.99
,,,,,
test-product-2,Test Product 2,Description 2,Vendor 2,SKU456,39.99
"""
        csv_path.write_text(csv_content)
        return csv_path
    
    @pytest.fixture
    def multi_variant_csv(self, tmp_path):
        """Create CSV with metafield-based options."""
        csv_path = tmp_path / "multi_variant.csv"
        csv_content = """Handle,Title,Variant SKU,Variant Price,Image Src,Variant Image,Barva (product.metafields.custom.barva),Velikost (product.metafields.custom.velikost)
multi-product,Multi Variant Product,SKU-RED-S,29.99,http://example.com/img1.jpg,http://example.com/img1.jpg,Red,Small
,,SKU-BLUE-M,35.99,,http://example.com/img2.jpg,Blue,Medium
,,SKU-BLUE-L,39.99,,http://example.com/img2.jpg,Blue,Large
"""
        csv_path.write_text(csv_content)
        return csv_path
    
    @pytest.fixture
    def single_variant_csv(self, tmp_path):
        """Create CSV for single-variant product (no options)."""
        csv_path = tmp_path / "single_variant.csv"
        csv_content = """Handle,Title,Variant SKU,Variant Price
single-product,Single Variant Product,SKU-SINGLE,19.99
"""
        csv_path.write_text(csv_content)
        return csv_path
    
    @pytest.fixture
    def variant_metafields_csv(self, tmp_path):
        """Create CSV with variant-level metafields."""
        csv_path = tmp_path / "variant_meta.csv"
        csv_content = """Handle,Title,Variant SKU,Variant Price,Color (product.metafields.custom.color),Weight (product.metafields.custom.weight)
var-meta-product,Product with Variant Meta,SKU-A,25.00,Red,100g
,,SKU-B,30.00,Blue,150g
"""
        csv_path.write_text(csv_content)
        return csv_path
    
    def test_parse_products(self, sample_csv):
        """Test basic CSV parsing."""
        parser = ShopifyCSVParser(sample_csv)
        products = parser.parse_all()
        
        assert len(products) == 2
        assert products[0].handle == 'test-product'
        assert products[0].title == 'Test Product'
        assert len(products[0].variants) == 1
        assert products[0].variants[0].sku == 'SKU123'
        assert products[0].variants[0].price == '29.99'
    
    def test_multi_variant_with_metafield_options(self, multi_variant_csv):
        """Test parsing product with metafield-based options."""
        parser = ShopifyCSVParser(multi_variant_csv)
        products = parser.parse_all()
        
        assert len(products) == 1
        product = products[0]
        
        assert product.handle == 'multi-product'
        assert len(product.options) == 2
        assert 'Barva' in product.options
        assert 'Velikost' in product.options
        
        assert len(product.variants) == 3
        assert product.variants[0].option1_name == 'Barva'
        assert product.variants[0].option1_value == 'Red'
        assert product.variants[0].option2_name == 'Velikost'
        assert product.variants[0].option2_value == 'Small'
    
    def test_image_collection_from_both_columns(self, multi_variant_csv):
        """Test that images are collected from both Image Src and Variant Image."""
        parser = ShopifyCSVParser(multi_variant_csv)
        products = parser.parse_all()
        
        assert len(products) == 1
        product = products[0]
        
        assert len(product.image_src) == 2
        assert 'http://example.com/img1.jpg' in product.image_src
        assert 'http://example.com/img2.jpg' in product.image_src
    
    def test_single_variant_no_options(self, single_variant_csv):
        """Test single-variant product has no options."""
        parser = ShopifyCSVParser(single_variant_csv)
        products = parser.parse_all()
        
        assert len(products) == 1
        product = products[0]
        
        assert len(product.options) == 0
        assert len(product.variants) == 1
        
        variant = product.variants[0]
        assert variant.option1_name is None
        assert variant.option1_value is None
        assert variant.option2_name is None
        assert variant.option2_value is None
        assert variant.option3_name is None
        assert variant.option3_value is None
    
    def test_variant_metafields_assigned(self, variant_metafields_csv):
        """Test variant-level metafields are assigned correctly."""
        parser = ShopifyCSVParser(variant_metafields_csv)
        products = parser.parse_all()
        
        assert len(products) == 1
        product = products[0]
        
        assert len(product.variants) == 2
        
        variant1 = product.variants[0]
        assert 'custom.color' in variant1.metafields
        assert variant1.metafields['custom.color'] == 'Red'
        assert 'custom.weight' in variant1.metafields
        assert variant1.metafields['custom.weight'] == '100g'
        
        variant2 = product.variants[1]
        assert 'custom.color' in variant2.metafields
        assert variant2.metafields['custom.color'] == 'Blue'
        assert 'custom.weight' in variant2.metafields
        assert variant2.metafields['custom.weight'] == '150g'
    
    def test_default_variant_creation(self, tmp_path):
        """Test that a default variant is created when no variants exist."""
        csv_path = tmp_path / "no_variants.csv"
        csv_content = """Handle,Title,Variant SKU,Variant Price
no-var-product,No Variants Product,SKU-DEFAULT,15.00
"""
        csv_path.write_text(csv_content)
        
        parser = ShopifyCSVParser(csv_path)
        products = parser.parse_all()
        
        assert len(products) == 1
        product = products[0]
        
        assert len(product.variants) == 1
        assert product.variants[0].sku == 'SKU-DEFAULT'
        assert product.variants[0].option1_name is None
    
    def test_get_sku_list(self, sample_csv):
        """Test SKU extraction."""
        parser = ShopifyCSVParser(sample_csv)
        skus = parser.get_sku_list()
        
        assert len(skus) == 2
        assert 'SKU123' in skus
        assert 'SKU456' in skus


class TestProductMatcher:
    """Tests for ProductMatcher."""
    
    @pytest.fixture
    def mock_shopify_service(self):
        """Create mock ShopifyService."""
        service = Mock(spec=ShopifyService)
        service.list_products.return_value = {
            'products': [
                {
                    'id': '111',
                    'variants': [
                        {'id': '222', 'sku': 'EXISTING_SKU'}
                    ]
                }
            ],
            'next_page_info': None
        }
        return service
    
    def test_match_new_product(self, mock_shopify_service):
        """Test matching a new product (should create)."""
        from app.services.shopify_csv_parser import ShopifyProduct, ShopifyVariant
        
        csv_product = ShopifyProduct(
            handle='new-product',
            title='New Product',
            variants=[ShopifyVariant(sku='NEW_SKU', price='29.99')]
        )
        
        matcher = ProductMatcher(mock_shopify_service)
        matches = matcher.match_products([csv_product])
        
        assert len(matches) == 1
        assert matches[0].action == MatchAction.CREATE
    
    def test_match_existing_product(self, mock_shopify_service):
        """Test matching existing product (should update)."""
        from app.services.shopify_csv_parser import ShopifyProduct, ShopifyVariant
        
        csv_product = ShopifyProduct(
            handle='existing-product',
            title='Existing Product',
            variants=[ShopifyVariant(sku='EXISTING_SKU', price='29.99')]
        )
        
        matcher = ProductMatcher(mock_shopify_service)
        matches = matcher.match_products([csv_product])
        
        assert len(matches) == 1
        assert matches[0].action == MatchAction.UPDATE
        assert matches[0].shopify_product_id == '111'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
