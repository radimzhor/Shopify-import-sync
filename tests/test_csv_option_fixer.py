"""
Tests for CSV Option Fixer service.

TEMPORARY: These tests verify the CSV transformation logic that fixes
Mergado's incorrect Option columns. Remove when Mergado fixes CSV generation.
"""
import pytest
import pandas as pd
from pathlib import Path
from app.services.csv_option_fixer import CSVOptionFixer


class TestCSVOptionFixer:
    """Tests for CSVOptionFixer transformations."""
    
    @pytest.fixture
    def fixer(self):
        """Create CSVOptionFixer instance."""
        return CSVOptionFixer()
    
    @pytest.fixture
    def sample_csv_path(self, tmp_path):
        """Create sample CSV with incorrect options."""
        csv_path = tmp_path / "test.csv"
        csv_content = """Handle,Title,Variant SKU,Variant Price,Option1 Name,Option1 Value,Option2 Name,Option2 Value,Option3 Name,Option3 Value,Barva (product.metafields.custom.barva),Velikost (product.metafields.custom.velikost)
test-product,Test Product,SKU1,29.99,,,,,,,Red,Small
test-product,,SKU2,35.99,,,,,,,Blue,Medium
test-product,,SKU3,39.99,,,,,,,Green,Large
"""
        csv_path.write_text(csv_content)
        return csv_path
    
    @pytest.fixture
    def single_variant_csv_path(self, tmp_path):
        """Create CSV for single variant product."""
        csv_path = tmp_path / "single.csv"
        csv_content = """Handle,Title,Variant SKU,Variant Price,Option1 Name,Option1 Value,Option2 Name,Option2 Value,Barva (product.metafields.custom.barva)
single-product,Single Product,SKU-SINGLE,19.99,,,,,Red
"""
        csv_path.write_text(csv_content)
        return csv_path
    
    @pytest.fixture
    def gap_options_csv_path(self, tmp_path):
        """Create CSV with gaps in options (Option2 filled but Option1 empty)."""
        csv_path = tmp_path / "gaps.csv"
        csv_content = """Handle,Title,Variant SKU,Option1 Name,Option1 Value,Option2 Name,Option2 Value,Option3 Name,Option3 Value
gap-product,Gap Product,SKU1,,,,Test,Value3,,
"""
        csv_path.write_text(csv_content)
        return csv_path
    
    def test_copy_custom_fields_to_options(self, fixer):
        """Test copying custom field values to Option columns."""
        df = pd.DataFrame({
            'Handle': ['test-product', 'test-product'],
            'Barva (product.metafields.custom.barva)': ['Red', 'Blue'],
            'Velikost (product.metafields.custom.velikost)': ['Small', 'Medium'],
            'Option1 Value': ['', ''],
            'Option2 Value': ['', ''],
            'Option3 Value': ['', '']
        })
        
        result = fixer._copy_custom_fields_to_options(df)
        
        assert result.loc[0, 'Option1 Value'] == 'Red'
        assert result.loc[0, 'Option2 Value'] == 'Small'
        assert result.loc[1, 'Option1 Value'] == 'Blue'
        assert result.loc[1, 'Option2 Value'] == 'Medium'
    
    def test_set_option_names(self, fixer):
        """Test setting Option Names based on custom fields."""
        df = pd.DataFrame({
            'Handle': ['test-product', 'test-product'],
            'Barva (product.metafields.custom.barva)': ['Red', 'Blue'],
            'Velikost (product.metafields.custom.velikost)': ['Small', 'Medium'],
            'Option1 Name': ['', ''],
            'Option2 Name': ['', ''],
            'Option3 Name': ['', '']
        })
        
        result = fixer._set_option_names(df)
        
        assert result.loc[0, 'Option1 Name'] == 'Barva'
        assert result.loc[0, 'Option2 Name'] == 'Velikost'
        assert result.loc[1, 'Option1 Name'] == 'Barva'
        assert result.loc[1, 'Option2 Name'] == 'Velikost'
    
    def test_shift_options_left_option1_empty(self, fixer):
        """Test shifting Option2 to Option1 when Option1 is empty."""
        df = pd.DataFrame({
            'Option1 Name': ['', ''],
            'Option1 Value': ['', ''],
            'Option2 Name': ['Color', 'Color'],
            'Option2 Value': ['Red', 'Blue'],
            'Option3 Name': ['', ''],
            'Option3 Value': ['', '']
        })
        
        result = fixer._shift_options_left(df)
        
        assert result.loc[0, 'Option1 Name'] == 'Color'
        assert result.loc[0, 'Option1 Value'] == 'Red'
        assert result.loc[0, 'Option2 Name'] == ''
        assert result.loc[0, 'Option2 Value'] == ''
    
    def test_shift_options_left_option2_empty(self, fixer):
        """Test shifting Option3 to Option2 when Option2 is empty."""
        df = pd.DataFrame({
            'Option1 Name': ['Color', 'Color'],
            'Option1 Value': ['Red', 'Blue'],
            'Option2 Name': ['', ''],
            'Option2 Value': ['', ''],
            'Option3 Name': ['Size', 'Size'],
            'Option3 Value': ['Small', 'Large']
        })
        
        result = fixer._shift_options_left(df)
        
        assert result.loc[0, 'Option2 Name'] == 'Size'
        assert result.loc[0, 'Option2 Value'] == 'Small'
        assert result.loc[0, 'Option3 Name'] == ''
        assert result.loc[0, 'Option3 Value'] == ''
    
    def test_fix_csv_multi_variant(self, fixer, sample_csv_path):
        """Test full fix_csv flow with multi-variant product."""
        fixed_path = fixer.fix_csv(sample_csv_path)
        
        assert fixed_path.exists()
        assert '_fixed' in fixed_path.name
        
        df = pd.read_csv(fixed_path, dtype=str, keep_default_na=False)
        
        assert df.loc[0, 'Option1 Name'] == 'Barva'
        assert df.loc[0, 'Option1 Value'] == 'Red'
        assert df.loc[0, 'Option2 Name'] == 'Velikost'
        assert df.loc[0, 'Option2 Value'] == 'Small'
        
        assert df.loc[1, 'Option1 Name'] == 'Barva'
        assert df.loc[1, 'Option1 Value'] == 'Blue'
        assert df.loc[1, 'Option2 Name'] == 'Velikost'
        assert df.loc[1, 'Option2 Value'] == 'Medium'
        
        assert df.loc[2, 'Option1 Name'] == 'Barva'
        assert df.loc[2, 'Option1 Value'] == 'Green'
        assert df.loc[2, 'Option2 Name'] == 'Velikost'
        assert df.loc[2, 'Option2 Value'] == 'Large'
    
    def test_fix_csv_single_variant(self, fixer, single_variant_csv_path):
        """Test fix_csv with single variant product."""
        fixed_path = fixer.fix_csv(single_variant_csv_path)
        
        df = pd.read_csv(fixed_path, dtype=str, keep_default_na=False)
        
        assert df.loc[0, 'Option1 Name'] == 'Barva'
        assert df.loc[0, 'Option1 Value'] == 'Red'
        assert df.loc[0, 'Option2 Name'] == ''
        assert df.loc[0, 'Option2 Value'] == ''
    
    def test_fix_csv_with_gaps(self, fixer, gap_options_csv_path):
        """Test that gaps in options are shifted left."""
        fixed_path = fixer.fix_csv(gap_options_csv_path)
        
        df = pd.read_csv(fixed_path, dtype=str, keep_default_na=False)
        
        assert df.loc[0, 'Option1 Name'] == 'Test'
        assert df.loc[0, 'Option1 Value'] == 'Value3'
        assert df.loc[0, 'Option2 Name'] == ''
        assert df.loc[0, 'Option2 Value'] == ''
    
    def test_empty_custom_fields_skipped(self, fixer):
        """Test that empty custom fields are not copied."""
        df = pd.DataFrame({
            'Handle': ['test-product'],
            'Barva (product.metafields.custom.barva)': [''],
            'Velikost (product.metafields.custom.velikost)': ['Medium'],
            'Option1 Value': [''],
            'Option2 Value': ['']
        })
        
        result = fixer._copy_custom_fields_to_options(df)
        
        assert result.loc[0, 'Option1 Value'] == 'Medium'
        assert result.loc[0, 'Option2 Value'] == ''
    
    def test_max_three_options(self, fixer):
        """Test that only first 3 options are used (Shopify limit)."""
        df = pd.DataFrame({
            'Handle': ['test'],
            'Barva (product.metafields.custom.barva)': ['Red'],
            'Velikost (product.metafields.custom.velikost)': ['S'],
            'Provedení (product.metafields.custom.provedeni)': ['A'],
            'Hodnota (product.metafields.custom.hodnota)': ['100'],
            'Option1 Value': [''],
            'Option2 Value': [''],
            'Option3 Value': ['']
        })
        
        result = fixer._copy_custom_fields_to_options(df)
        
        assert result.loc[0, 'Option1 Value'] == 'Red'
        assert result.loc[0, 'Option2 Value'] == 'S'
        assert result.loc[0, 'Option3 Value'] == 'A'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
