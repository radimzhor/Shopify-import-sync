"""
CSV Feed Downloader - downloads and caches Mergado project output feeds.
"""
import logging
import tempfile
from pathlib import Path
from typing import Optional

import requests

from app.services.exceptions import APIError


logger = logging.getLogger(__name__)


class CSVDownloader:
    """
    Downloads CSV feeds from URLs with caching support.
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize CSV downloader.
        
        Args:
            cache_dir: Directory for temporary file storage (defaults to system temp)
        """
        self.cache_dir = cache_dir or Path(tempfile.gettempdir())
        self.timeout = 300  # 5 minutes for large feeds
    
    def download(
        self,
        url: str,
        cache_key: Optional[str] = None
    ) -> Path:
        """
        Download CSV from URL and save to temporary file.
        
        Args:
            url: Feed URL to download
            cache_key: Optional cache identifier (e.g., project_id)
            
        Returns:
            Path to downloaded CSV file
            
        Raises:
            APIError: If download fails
        """
        # #region agent log - Hypothesis A,B: trace exact URL being downloaded
        logger.info(f"[DBG-654f3d] HYP-AB download: url={url!r}, cache_key={cache_key!r}")
        # #endregion
        
        try:
            # Stream download for large files
            response = requests.get(url, stream=True, timeout=self.timeout)
            response.raise_for_status()
            
            # #region agent log - Hypothesis B: check content type (XML vs CSV?)
            logger.info(
                f"[DBG-654f3d] HYP-B download response: status={response.status_code}, "
                f"content_type={response.headers.get('Content-Type')!r}, "
                f"content_length={response.headers.get('Content-Length')!r}"
            )
            # #endregion
            
            # Create temp file with optional cache key
            if cache_key:
                file_path = self.cache_dir / f"feed_{cache_key}.csv"
            else:
                temp_file = tempfile.NamedTemporaryFile(
                    mode='wb',
                    suffix='.csv',
                    dir=self.cache_dir,
                    delete=False
                )
                file_path = Path(temp_file.name)
            
            # Write content in chunks
            bytes_written = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bytes_written += len(chunk)
            
            logger.info(f"Downloaded {bytes_written} bytes to {file_path}")
            
            # #region agent log
            logger.info(f"[DBG-654f3d] download complete: bytes={bytes_written}, path={file_path}")
            # #endregion
            
            # Validate file was written
            if bytes_written == 0:
                raise APIError("Downloaded CSV is empty (0 bytes)")
            
            if not file_path.exists():
                raise APIError(f"Downloaded file not found at {file_path}")
            
            # Log first few lines for debugging
            first_line_content = None
            try:
                with open(file_path, 'r', encoding='utf-8') as check_file:
                    first_lines = [next(check_file) for _ in range(min(3, bytes_written))]
                    first_line_content = first_lines[0][:200] if first_lines else 'empty'
                    logger.debug(f"CSV first line (header): {first_line_content}")
                    
                    # #region agent log - Hypothesis B: is this CSV or XML?
                    logger.info(
                        f"[DBG-654f3d] HYP-B first_line={first_line_content!r}, "
                        f"lines_read={len(first_lines)}"
                    )
                    # #endregion
            except Exception as e:
                logger.warning(f"Could not read CSV for validation: {e}")
                # #region agent log
                logger.info(f"[DBG-654f3d] CSV read error: {e}")
                # #endregion
            
            return file_path
            
        except requests.RequestException as e:
            raise APIError(f"Failed to download CSV: {str(e)}")
    
    def get_cached_path(self, cache_key: str) -> Optional[Path]:
        """
        Get path to cached CSV if it exists.
        
        Args:
            cache_key: Cache identifier
            
        Returns:
            Path to cached file, or None if not cached
        """
        file_path = self.cache_dir / f"feed_{cache_key}.csv"
        return file_path if file_path.exists() else None
    
    def clear_cache(self, cache_key: Optional[str] = None) -> None:
        """
        Clear cached CSV files.
        
        Args:
            cache_key: Specific cache key to clear, or None to clear all
        """
        if cache_key:
            file_path = self.cache_dir / f"feed_{cache_key}.csv"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Cleared cache: {cache_key}")
        else:
            # Clear all feed_*.csv files
            for file_path in self.cache_dir.glob("feed_*.csv"):
                file_path.unlink()
            logger.info("Cleared all CSV cache")
