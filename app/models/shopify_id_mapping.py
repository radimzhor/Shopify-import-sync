"""
ShopifyIDMapping model - operational mapping of Mergado SKU to Shopify product/variant IDs.

This is the source of truth for the custom app rule endpoint. It is updated on every
successful import and queried when Mergado applies the writeback rule to a project.
"""
from datetime import datetime

from app import db


class ShopifyIDMapping(db.Model):
    """
    Maps a product SKU within a Mergado project to its Shopify product and variant IDs.

    Attributes:
        id: Primary key
        project_id: Foreign key to Project (our internal ID)
        sku: Product identifier (ITEM_ID in Mergado, Handle/Variant SKU in Shopify CSV)
        shopify_product_id: Shopify product ID
        shopify_variant_id: Shopify variant ID
        updated_at: Last time this mapping was updated (tracks freshness)
        project: Related project (many-to-one)
    """
    __tablename__ = 'shopify_id_mappings'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    sku = db.Column(db.String(200), nullable=False, index=True)
    shopify_product_id = db.Column(db.String(50), nullable=False)
    shopify_variant_id = db.Column(db.String(50), nullable=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint('project_id', 'sku', name='uq_shopify_id_mapping_project_sku'),
    )

    # Relationships
    project = db.relationship('Project', back_populates='shopify_id_mappings')

    def __repr__(self) -> str:
        return (
            f'<ShopifyIDMapping project={self.project_id} sku={self.sku} '
            f'shopify={self.shopify_product_id}:{self.shopify_variant_id}>'
        )

    @property
    def combined_id(self) -> str:
        """Return the combined shopify_id value written into the Mergado element."""
        if self.shopify_variant_id:
            return f"{self.shopify_product_id}:{self.shopify_variant_id}"
        return self.shopify_product_id

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'sku': self.sku,
            'shopify_product_id': self.shopify_product_id,
            'shopify_variant_id': self.shopify_variant_id,
            'combined_id': self.combined_id,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
