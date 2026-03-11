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
    
    def test_parse_products(self, sample_csv):
        """Test CSV parsing."""
        parser = ShopifyCSVParser(sample_csv)
        products = parser.parse_all()
        
        assert len(products) == 2
        assert products[0].handle == 'test-product'
        assert products[0].title == 'Test Product'
        assert len(products[0].variants) == 1
        assert products[0].variants[0].sku == 'SKU123'
        assert products[0].variants[0].price == '29.99'
    
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
