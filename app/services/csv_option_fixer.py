"""
CSV Option Fixer - fixes Mergado's incorrect Option Name/Value columns.

TEMPORARY solution until Mergado generates correct Shopify CSV output.
Applies 3 transformations to ensure variants are properly grouped in Shopify.
"""
import logging
from pathlib import Path
from typing import List, Optional
import pandas as pd


logger = logging.getLogger(__name__)


class CSVOptionFixer:
    """
    Applies transformations to fix Mergado's incorrect Option columns.
    
    TEMPORARY: This is a workaround for Mergado's CSV generation issues.
    Remove this class when Mergado fixes their Shopify CSV output.
    
    Applies 3 transformations in order:
    1. Copy custom field values to Option1/2/3 Value columns
    2. Set Option1/2/3 Name based on which custom fields have values
    3. Shift options left to fill gaps (ensure Option1 always filled first)
    """
    
    CUSTOM_FIELD_COLUMNS = [
        "Barva (product.metafields.custom.barva)",
        "Velikost (product.metafields.custom.velikost)",
        "Provedení (product.metafields.custom.provedeni)",
        "Hodnota (product.metafields.custom.hodnota)",
        "Pevnost (product.metafields.custom.pevnost)",
        "Značka (product.metafields.custom.znacka)",
        "Šířka (product.metafields.custom.sirka)",
        "Velikost balení (product.metafields.custom.velikost_baleni)"
    ]
    
    def fix_csv(self, csv_path: Path) -> Path:
        """
        Apply all fixes to CSV and return path to fixed file.
        
        Args:
            csv_path: Path to original CSV file
            
        Returns:
            Path to fixed CSV file
            
        Raises:
            Exception: If transformation fails
        """
        logger.info(f"Applying CSV option fixes to {csv_path}")
        
        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            
            original_rows = len(df)
            logger.debug(f"Loaded CSV with {original_rows} rows")
            
            df = self._copy_custom_fields_to_options(df)
            df = self._set_option_names(df)
            df = self._shift_options_left(df)
            
            fixed_path = csv_path.parent / f"{csv_path.stem}_fixed.csv"
            df.to_csv(fixed_path, index=False)
            
            logger.info(f"Applied CSV fixes successfully, saved to {fixed_path}")
            return fixed_path
            
        except Exception as e:
            logger.error(f"Failed to apply CSV fixes: {e}", exc_info=True)
            raise
    
    def _copy_custom_fields_to_options(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Script 1: Copy first 3 non-empty custom field values to Option columns.
        
        For each row, finds the first 3 custom field columns that have values
        and copies those values to Option1/2/3 Value columns.
        
        Args:
            df: DataFrame with CSV data
            
        Returns:
            Modified DataFrame
        """
        logger.debug("Step 1: Copying custom field values to option columns")
        
        option_value_cols = ['Option1 Value', 'Option2 Value', 'Option3 Value']
        
        for col in option_value_cols:
            if col not in df.columns:
                df[col] = ''
        
        for idx, row in df.iterrows():
            values_to_copy = []
            
            for custom_field in self.CUSTOM_FIELD_COLUMNS:
                if custom_field in df.columns:
                    value = row[custom_field]
                    if value and value.strip():
                        values_to_copy.append(value)
                        if len(values_to_copy) == 3:
                            break
            
            if values_to_copy:
                for i, value in enumerate(values_to_copy):
                    df.at[idx, option_value_cols[i]] = value
        
        logger.debug(f"Copied custom field values to option columns for {len(df)} rows")
        return df
    
    def _set_option_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Script 2: Set Option Names based on which custom fields have values.
        
        For each row, extracts the first word from custom field column names
        (e.g., "Barva" from "Barva (product.metafields.custom.barva)")
        and sets it as the corresponding Option Name.
        
        Args:
            df: DataFrame with CSV data
            
        Returns:
            Modified DataFrame
        """
        logger.debug("Step 2: Setting option names based on custom fields")
        
        option_name_cols = ['Option1 Name', 'Option2 Name', 'Option3 Name']
        
        for col in option_name_cols:
            if col not in df.columns:
                df[col] = ''
        
        for idx, row in df.iterrows():
            option_names = []
            
            for custom_field in self.CUSTOM_FIELD_COLUMNS:
                if custom_field in df.columns:
                    value = row[custom_field]
                    if value and value.strip():
                        label = custom_field.split(' ')[0]
                        option_names.append(label)
                        if len(option_names) == 3:
                            break
            
            if option_names:
                for i, name in enumerate(option_names):
                    df.at[idx, option_name_cols[i]] = name
        
        logger.debug(f"Set option names for {len(df)} rows")
        return df
    
    def _shift_options_left(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Script 3: Shift options left to fill gaps.
        
        Ensures Option1 is always filled before Option2, and Option2 before Option3.
        If Option1 is empty but Option2 has values, moves Option2 to Option1.
        If Option2 is empty but Option3 has values, moves Option3 to Option2.
        
        Args:
            df: DataFrame with CSV data
            
        Returns:
            Modified DataFrame
        """
        logger.debug("Step 3: Shifting options left to fill gaps")
        
        shifts_made = 0
        
        for idx, row in df.iterrows():
            option1_name = row.get('Option1 Name', '').strip()
            option1_value = row.get('Option1 Value', '').strip()
            option2_name = row.get('Option2 Name', '').strip()
            option2_value = row.get('Option2 Value', '').strip()
            option3_name = row.get('Option3 Name', '').strip()
            option3_value = row.get('Option3 Value', '').strip()
            
            if not option1_name and not option1_value and option2_name and option2_value:
                df.at[idx, 'Option1 Name'] = option2_name
                df.at[idx, 'Option1 Value'] = option2_value
                df.at[idx, 'Option2 Name'] = ''
                df.at[idx, 'Option2 Value'] = ''
                shifts_made += 1
                
                option2_name = ''
                option2_value = ''
            
            if not option2_name and not option2_value and option3_name and option3_value:
                df.at[idx, 'Option2 Name'] = option3_name
                df.at[idx, 'Option2 Value'] = option3_value
                df.at[idx, 'Option3 Name'] = ''
                df.at[idx, 'Option3 Value'] = ''
                shifts_made += 1
        
        logger.debug(f"Shifted options left {shifts_made} times")
        return df
