"""
SyncLog model - tracks stock/price synchronization runs.
"""
from datetime import datetime
from enum import Enum
from sqlalchemy.dialects.postgresql import JSON
from app import db


class SyncStatus(str, Enum):
    """Sync log status enum."""
    SUCCESS = 'success'
    PARTIAL = 'partial'
    FAILED = 'failed'


class SyncLog(db.Model):
    """
    Logs a stock or price synchronization run.
    
    Attributes:
        id: Primary key
        sync_config_id: Foreign key to SyncConfig
        status: Sync status (success/partial/failed)
        items_synced: Number of items successfully synced
        items_failed: Number of items that failed
        started_at: When sync started
        finished_at: When sync finished
        error_message: Error message if failed
        details: JSON field with additional details
        sync_config: Related sync config (many-to-one)
    """
    __tablename__ = 'sync_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    sync_config_id = db.Column(db.Integer, db.ForeignKey('sync_configs.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, index=True)
    
    # Counts
    items_synced = db.Column(db.Integer, default=0, nullable=False)
    items_failed = db.Column(db.Integer, default=0, nullable=False)
    
    # Timestamps
    started_at = db.Column(db.DateTime, nullable=False, index=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    
    # Error and details
    error_message = db.Column(db.Text, nullable=True)
    details = db.Column(JSON, nullable=True)
    
    # Relationships
    sync_config = db.relationship('SyncConfig', back_populates='logs')
    
    def __repr__(self):
        return f'<SyncLog {self.id}: {self.status}>'
    
    def to_dict(self):
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'sync_config_id': self.sync_config_id,
            'status': self.status,
            'items_synced': self.items_synced,
            'items_failed': self.items_failed,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'error_message': self.error_message,
            'details': self.details,
        }
