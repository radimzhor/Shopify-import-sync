"""
ImportJob model - tracks product import operations.
"""
from datetime import datetime
from enum import Enum
from app import db


class ImportStatus(str, Enum):
    """Import job status enum."""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ImportJob(db.Model):
    """
    Tracks a product import job from Mergado to Shopify.
    
    Attributes:
        id: Primary key
        project_id: Foreign key to Project
        status: Job status (pending/running/completed/failed)
        total_count: Total products to import
        success_count: Successfully imported products
        failed_count: Failed products
        skipped_count: Skipped products
        started_at: When import started
        finished_at: When import finished
        error_message: Error message if failed
        created_at: When job was created
        project: Related project (many-to-one)
        logs: Related import logs (one-to-many)
    """
    __tablename__ = 'import_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default=ImportStatus.PENDING.value, nullable=False, index=True)
    
    # Counts
    total_count = db.Column(db.Integer, default=0, nullable=False)
    success_count = db.Column(db.Integer, default=0, nullable=False)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    skipped_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Timestamps
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Error info
    error_message = db.Column(db.Text, nullable=True)
    
    # Relationships
    project = db.relationship('Project', back_populates='import_jobs')
    logs = db.relationship('ImportLog', back_populates='import_job', cascade='all, delete-orphan', lazy='dynamic')
    
    def __repr__(self):
        return f'<ImportJob {self.id}: {self.status}>'
    
    def to_dict(self):
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'status': self.status,
            'total_count': self.total_count,
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'skipped_count': self.skipped_count,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'error_message': self.error_message,
        }
