"""
Shop model - represents a Mergado eshop.
"""
from datetime import datetime
from app import db


class Shop(db.Model):
    """
    Represents a Mergado eshop connected to this application.
    
    Attributes:
        id: Primary key
        mergado_shop_id: Unique Mergado eshop ID
        name: Shop name
        shopify_connected: Whether Shopify is connected via Keychain
        created_at: When shop was first connected
        updated_at: Last update timestamp
        projects: Related projects (one-to-many)
    """
    __tablename__ = 'shops'
    
    id = db.Column(db.Integer, primary_key=True)
    mergado_shop_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    shopify_connected = db.Column(db.Boolean, default=False, nullable=False)
    
    # OAuth tokens (for background sync operations)
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    projects = db.relationship('Project', back_populates='shop', cascade='all, delete-orphan', lazy='dynamic')
    
    def __repr__(self):
        return f'<Shop {self.id}: {self.name}>'
    
    def to_dict(self):
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'mergado_shop_id': self.mergado_shop_id,
            'name': self.name,
            'shopify_connected': self.shopify_connected,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
