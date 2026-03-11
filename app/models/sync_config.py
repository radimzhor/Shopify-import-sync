"""
SyncConfig model - configuration for stock/price synchronization.
"""
from datetime import datetime
from enum import Enum
from app import db


class SyncType(str, Enum):
    """Sync configuration type enum."""
    STOCK = 'stock'
    PRICE = 'price'


class SyncConfig(db.Model):
    """
    Configuration for automatic stock or price synchronization.
    
    Attributes:
        id: Primary key
        project_id: Foreign key to Project
        sync_type: Type of sync (stock/price)
        enabled: Whether sync is enabled
        interval_minutes: Sync interval in minutes
        last_sync_at: Timestamp of last sync
        created_at: When config was created
        updated_at: Last update timestamp
        project: Related project (many-to-one)
        logs: Related sync logs (one-to-many)
    """
    __tablename__ = 'sync_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    sync_type = db.Column(db.String(20), nullable=False, index=True)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    interval_minutes = db.Column(db.Integer, default=60, nullable=False)
    
    # Timestamps
    last_sync_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    project = db.relationship('Project', back_populates='sync_configs')
    logs = db.relationship('SyncLog', back_populates='sync_config', cascade='all, delete-orphan', lazy='dynamic')
    
    # Unique constraint: one config per project per sync_type
    __table_args__ = (
        db.UniqueConstraint('project_id', 'sync_type', name='uq_project_sync_type'),
    )
    
    def __repr__(self):
        return f'<SyncConfig {self.id}: {self.sync_type} for project {self.project_id}>'
    
    def to_dict(self):
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'sync_type': self.sync_type,
            'enabled': self.enabled,
            'interval_minutes': self.interval_minutes,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
