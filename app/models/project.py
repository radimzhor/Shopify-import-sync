"""
Project model - represents a Mergado project linked to a shop.
"""
from datetime import datetime
from app import db


class Project(db.Model):
    """
    Represents a Mergado project configured for Shopify sync.
    
    Attributes:
        id: Primary key
        shop_id: Foreign key to Shop
        mergado_project_id: Unique Mergado project ID
        name: Project name
        output_url: Project output feed URL
        output_format: Output format (e.g., 'shopify_csv')
        shopify_id_element_id: ID of created shopify_id element (nullable)
        shopify_writeback_rule_id: Mergado rule ID for the custom app writeback rule (nullable)
        created_at: When project was first configured
        updated_at: Last update timestamp
        shop: Related shop (many-to-one)
        import_jobs: Related import jobs (one-to-many)
        sync_configs: Related sync configurations (one-to-many)
        shopify_id_mappings: SKU → Shopify ID mappings for this project (one-to-many)
    """
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    mergado_project_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    output_url = db.Column(db.String(500), nullable=True)
    output_format = db.Column(db.String(50), nullable=True)
    shopify_id_element_id = db.Column(db.String(50), nullable=True)
    # Mergado rule ID for the custom app writeback rule (set once, reused on every import)
    shopify_writeback_rule_id = db.Column(db.String(50), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    shop = db.relationship('Shop', back_populates='projects')
    import_jobs = db.relationship('ImportJob', back_populates='project', cascade='all, delete-orphan', lazy='dynamic')
    sync_configs = db.relationship('SyncConfig', back_populates='project', cascade='all, delete-orphan', lazy='dynamic')
    shopify_id_mappings = db.relationship(
        'ShopifyIDMapping', back_populates='project', cascade='all, delete-orphan', lazy='dynamic'
    )
    
    def __repr__(self):
        return f'<Project {self.id}: {self.name}>'
    
    def to_dict(self):
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'shop_id': self.shop_id,
            'mergado_project_id': self.mergado_project_id,
            'name': self.name,
            'output_url': self.output_url,
            'output_format': self.output_format,
            'shopify_id_element_id': self.shopify_id_element_id,
            'shopify_writeback_rule_id': self.shopify_writeback_rule_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
