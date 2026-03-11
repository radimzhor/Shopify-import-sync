# Testing Workflow Skill

## Running Tests

### Full Test Suite
```bash
pytest                                    # Run all tests
pytest --cov=app --cov-report=html       # With coverage report
pytest -v                                 # Verbose output
pytest -x                                 # Stop on first failure
```

### Specific Tests
```bash
pytest tests/test_services.py            # One file
pytest tests/test_services.py::test_name # One test
pytest -k "shopify"                      # Tests matching pattern
```

### Coverage Requirements
- **Minimum**: 80% overall coverage
- **Target**: 90%+ for services and models
- View report: `open htmlcov/index.html`

## Writing Unit Tests

### Test File Structure
```python
# tests/test_services.py
import pytest
from app.services.mergado_client import MergadoClient

class TestMergadoClient:
    """Test MergadoClient service."""
    
    def test_get_project_success(self, mocker):
        """Should fetch project details successfully."""
        # Arrange
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "id": "123",
            "name": "Test Project",
            "url": "https://example.com/feed.xml"
        }
        mocker.patch.object(MergadoClient, "_request", return_value=mock_response)
        
        client = MergadoClient(access_token="test_token")
        
        # Act
        result = client.get_project("123")
        
        # Assert
        assert result["id"] == "123"
        assert result["name"] == "Test Project"
```

### Using Fixtures

Define in `tests/conftest.py`:

```python
import pytest
from app import create_app, db

@pytest.fixture
def app():
    """Create and configure a test app."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Test client for making requests."""
    return app.test_client()

@pytest.fixture
def auth_headers():
    """Authenticated request headers."""
    return {"Authorization": "Bearer test_token"}
```

Use in tests:

```python
def test_endpoint(client, auth_headers):
    response = client.get("/api/projects", headers=auth_headers)
    assert response.status_code == 200
```

## Mocking External APIs

### Mock Mergado API Response
```python
def test_import_products(mocker):
    # Mock the entire request
    mock_get = mocker.patch("requests.get")
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"data": [...]}
    
    # Or mock just the client method
    mocker.patch.object(
        MergadoClient,
        "get_project_products",
        return_value=[{"id": "1", "sku": "TEST-SKU"}]
    )
```

### Mock Shopify Proxy
```python
def test_create_shopify_product(mocker):
    mock_proxy = mocker.patch.object(
        ShopifyProxyService,
        "create_product",
        return_value={"product": {"id": 12345, "variants": [{"id": 67890}]}}
    )
    
    service = ImportService()
    result = service.import_product({"sku": "TEST-SKU"})
    
    assert result["shopify_id"] == 12345
    mock_proxy.assert_called_once()
```

## Integration Tests

Test multiple components together:

```python
def test_full_import_flow(app, client, mocker):
    """Test complete product import from CSV to Shopify."""
    # Mock external APIs
    mocker.patch.object(MergadoClient, "get_project", return_value={...})
    mocker.patch("requests.get", return_value=mock_csv_response)
    mocker.patch.object(ShopifyProxyService, "create_product", return_value={...})
    
    # Make request
    response = client.post("/import/start", json={"project_id": "123"})
    
    # Assert full workflow
    assert response.status_code == 200
    assert ImportJob.query.count() == 1
    assert ImportLog.query.count() > 0
```

## Testing Database Models

```python
def test_project_model(app):
    """Test Project model creation and relationships."""
    with app.app_context():
        shop = Shop(mergado_shop_id="shop1", name="Test Shop")
        db.session.add(shop)
        db.session.flush()
        
        project = Project(
            mergado_project_id="proj1",
            shop_id=shop.id,
            name="Test Project"
        )
        db.session.add(project)
        db.session.commit()
        
        # Test relationship
        assert project.shop.name == "Test Shop"
        assert shop.projects[0].name == "Test Project"
```

## Testing Error Handling

```python
def test_api_error_handling(mocker):
    """Should handle API errors gracefully."""
    mock_request = mocker.patch.object(MergadoClient, "_request")
    mock_request.side_effect = APIError("Connection failed")
    
    client = MergadoClient(access_token="test_token")
    
    with pytest.raises(APIError) as exc_info:
        client.get_project("123")
    
    assert "Connection failed" in str(exc_info.value)
```

## Test Markers

Use markers to categorize tests:

```python
@pytest.mark.unit
def test_parse_csv():
    """Unit test for CSV parser."""
    pass

@pytest.mark.integration
def test_import_workflow():
    """Integration test for full import."""
    pass

@pytest.mark.slow
def test_large_dataset():
    """Test with large dataset."""
    pass
```

Run specific markers:
```bash
pytest -m unit          # Only unit tests
pytest -m "not slow"    # Skip slow tests
```

## Pre-Commit Testing

Before committing:
```bash
# Format code
black . --line-length 100
isort .

# Lint
flake8 app/ tests/

# Run tests
pytest --cov=app --cov-report=term-missing

# Check coverage threshold
pytest --cov=app --cov-fail-under=80
```

## Common Testing Patterns

### Test API Endpoint
```python
def test_get_projects(client, auth_headers, mocker):
    mocker.patch.object(MergadoClient, "get_projects", return_value=[...])
    response = client.get("/api/projects", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json["projects"]) > 0
```

### Test CSV Parsing
```python
def test_parse_shopify_csv():
    csv_content = "Handle,Title,Variant SKU\ntest-product,Test Product,TEST-SKU"
    parser = ShopifyCSVParser()
    products = parser.parse(csv_content)
    assert len(products) == 1
    assert products[0]["sku"] == "TEST-SKU"
```

### Test Background Job
```python
def test_sync_stock_job(mocker):
    mocker.patch.object(SyncService, "sync_stock", return_value={"synced": 10})
    job = StockSyncJob()
    result = job.run()
    assert result["synced"] == 10
```

## Coverage Goals by Module

- `app/services/`: 90%+ (critical business logic)
- `app/models/`: 85%+ (data layer)
- `app/routes/`: 80%+ (endpoints)
- `app/auth/`: 95%+ (security critical)
- `app/middleware/`: 75%+ (framework code)
