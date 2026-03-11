"""
ImportLog model - per-product import results.
"""
from datetime import datetime
from enum import Enum
from sqlalchemy.dialects.postgresql import JSON
from app import db


class ImportLogStatus(str, Enum):
    """Import log entry status enum."""
    SUCCESS = 'success'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class ImportLog(db.Model):
    """
    Logs the result of importing a single product.
    
    Attributes:
        id: Primary key
        import_job_id: Foreign key to ImportJob
        product_identifier: Product SKU or identifier
        status: Import status (success/failed/skipped)
        shopify_product_id: Shopify product ID (if created/updated)
        shopify_variant_id: Shopify variant ID (if created/updated)
        error_message: Error message if failed
        details: JSON field with additional details
        created_at: When log entry was created
        import_job: Related import job (many-to-one)
    """
    __tablename__ = 'import_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    import_job_id = db.Column(db.Integer, db.ForeignKey('import_jobs.id'), nullable=False, index=True)
    product_identifier = db.Column(db.String(200), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, index=True)
    
    # Shopify IDs
    shopify_product_id = db.Column(db.String(50), nullable=True, index=True)
    shopify_variant_id = db.Column(db.String(50), nullable=True)
    
    # Error and details
    error_message = db.Column(db.Text, nullable=True)
    details = db.Column(JSON, nullable=True)
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    import_job = db.relationship('ImportJob', back_populates='logs')
    
    def __repr__(self):
        return f'<ImportLog {self.id}: {self.product_identifier} - {self.status}>'
    
    def to_dict(self):
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'import_job_id': self.import_job_id,
            'product_identifier': self.product_identifier,
            'status': self.status,
            'shopify_product_id': self.shopify_product_id,
            'shopify_variant_id': self.shopify_variant_id,
            'error_message': self.error_message,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
