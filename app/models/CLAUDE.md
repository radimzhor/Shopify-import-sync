# app/models/ - Database Models

This module defines the database schema using SQLAlchemy ORM. Models represent tables and relationships.

## What's Here

- `shop.py` - Shop model (Mergado eshop)
- `project.py` - Project model (Mergado project linked to shop)
- `import_job.py` - ImportJob model (tracks product imports)
- `import_log.py` - ImportLog model (per-product import results)
- `sync_config.py` - SyncConfig model (stock/price sync settings)
- `sync_log.py` - SyncLog model (sync run history)

## Database Rules

### ALWAYS
- ✅ Use Alembic migrations for ALL schema changes
- ✅ Add indexes on foreign keys
- ✅ Add indexes on frequently queried columns
- ✅ Use `nullable=False` for required fields
- ✅ Set `default` values for optional fields
- ✅ Define relationships with `back_populates`
- ✅ Use `cascade` options appropriately
- ✅ Add `__repr__` for debugging
- ✅ Use `DateTime` with timezone awareness

### NEVER
- ❌ Edit database directly without migration
- ❌ Use raw SQL strings (SQL injection risk)
- ❌ Store sensitive data unencrypted
- ❌ Create circular dependencies between models
- ❌ Forget foreign key constraints
- ❌ Use mutable defaults (e.g., `default=[]`)

## Model Pattern

```python
from app import db
from datetime import datetime

class ModelName(db.Model):
    __tablename__ = 'table_name'  # plural, snake_case
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    parent_id = db.Column(db.Integer, db.ForeignKey('parent_table.id'), nullable=False, index=True)
    
    # Data columns
    name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default='pending', nullable=False)
    count = db.Column(db.Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    parent = db.relationship('Parent', back_populates='children')
    
    def __repr__(self):
        return f'<ModelName {self.id}: {self.name}>'
    
    def to_dict(self):
        """Serialize to dictionary for JSON responses."""
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
        }
```

## Relationships

### One-to-Many
```python
# Parent model
class Shop(db.Model):
    __tablename__ = 'shops'
    id = db.Column(db.Integer, primary_key=True)
    # ...
    projects = db.relationship('Project', back_populates='shop', cascade='all, delete-orphan')

# Child model
class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    # ...
    shop = db.relationship('Shop', back_populates='projects')

# Usage:
shop = Shop.query.get(1)
projects = shop.projects  # List of Project objects

project = Project.query.get(1)
shop = project.shop  # Single Shop object
```

### Cascade Options
- `all, delete-orphan` - Delete children when parent is deleted
- `all, delete` - Delete children, but orphans remain
- `save-update` - Only cascade saves, not deletes

## Indexes

### When to Add Indexes
- Foreign keys (always)
- Columns used in WHERE clauses frequently
- Columns used in ORDER BY
- Unique constraints

### How to Add Indexes
```python
# Single column index
status = db.Column(db.String(50), nullable=False, index=True)

# Composite index (multiple columns)
__table_args__ = (
    db.Index('idx_shop_project', 'shop_id', 'mergado_project_id'),
)

# Unique constraint
mergado_shop_id = db.Column(db.String(50), unique=True, nullable=False)
```

## Common Patterns

### Status Enum
```python
from enum import Enum

class ImportStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'

class ImportJob(db.Model):
    status = db.Column(db.Enum(ImportStatus), default=ImportStatus.PENDING, nullable=False)
```

### JSON Column
```python
from sqlalchemy.dialects.postgresql import JSON

class ImportLog(db.Model):
    details = db.Column(JSON, nullable=True)  # Store arbitrary JSON data
```

### Soft Delete
```python
class Project(db.Model):
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    def soft_delete(self):
        self.deleted_at = datetime.utcnow()
        db.session.commit()
    
    @staticmethod
    def active_projects():
        return Project.query.filter(Project.deleted_at.is_(None))
```

## Queries

### Basic Queries
```python
# Get by ID
project = Project.query.get(123)
# Or with error handling
project = Project.query.get_or_404(123)

# Filter
projects = Project.query.filter_by(shop_id=1, status='active').all()
projects = Project.query.filter(Project.status == 'active').all()

# Order
projects = Project.query.order_by(Project.created_at.desc()).all()

# Limit
recent = Project.query.order_by(Project.created_at.desc()).limit(10).all()

# Pagination
page = Project.query.paginate(page=1, per_page=20, error_out=False)
projects = page.items
total = page.total
```

### Joins
```python
# Explicit join
results = db.session.query(Project, Shop).join(Shop).filter(Shop.name == 'Test').all()

# Using relationship
projects = Project.query.join(Project.shop).filter(Shop.name == 'Test').all()
```

### Aggregation
```python
from sqlalchemy import func

# Count
total = Project.query.count()
active_count = Project.query.filter_by(status='active').count()

# Sum
total_imported = db.session.query(func.sum(ImportJob.success_count)).scalar()

# Group by
counts = db.session.query(
    ImportJob.status,
    func.count(ImportJob.id)
).group_by(ImportJob.status).all()
```

## Transactions

```python
try:
    # Multiple operations in one transaction
    shop = Shop(mergado_shop_id='shop123', name='Test Shop')
    db.session.add(shop)
    db.session.flush()  # Get shop.id without committing
    
    project = Project(shop_id=shop.id, mergado_project_id='proj456', name='Project 1')
    db.session.add(project)
    
    db.session.commit()  # Commit all changes
except Exception as e:
    db.session.rollback()  # Rollback on error
    logger.error(f"Transaction failed: {e}")
    raise
```

## Migrations

### Create Migration
```bash
# After modifying models
flask db migrate -m "Add shopify_id field to Project"

# Review generated migration in migrations/versions/

# Apply migration
flask db upgrade
```

### Migration Best Practices

1. **Review generated code** - Alembic can't detect everything
2. **Test locally first** - Apply and rollback
3. **One concept per migration** - Easier to rollback
4. **Add data migrations** - Populate defaults for new columns
5. **Document complex migrations** - Explain why

### Data Migration Example
```python
# In migration file
def upgrade():
    # Add column as nullable first
    op.add_column('projects', sa.Column('shopify_id_element_id', sa.String(50), nullable=True))
    
    # Populate with defaults
    op.execute("UPDATE projects SET shopify_id_element_id = '' WHERE shopify_id_element_id IS NULL")
    
    # Make it NOT NULL
    op.alter_column('projects', 'shopify_id_element_id', nullable=False)
```

## Testing Models

```python
def test_shop_project_relationship(app):
    with app.app_context():
        shop = Shop(mergado_shop_id='shop123', name='Test Shop')
        db.session.add(shop)
        db.session.flush()
        
        project = Project(
            shop_id=shop.id,
            mergado_project_id='proj123',
            name='Test Project'
        )
        db.session.add(project)
        db.session.commit()
        
        # Test relationship
        assert len(shop.projects) == 1
        assert shop.projects[0].name == 'Test Project'
        assert project.shop.name == 'Test Shop'
```

## Common Gotchas

### 1. Mutable Defaults
```python
# WRONG - all instances share same list!
class Model(db.Model):
    data = db.Column(JSON, default=[])

# RIGHT - use callable
class Model(db.Model):
    data = db.Column(JSON, default=list)
```

### 2. Session Lifecycle
```python
# WRONG - object detached after commit
project = Project.query.get(1)
db.session.commit()
print(project.shop.name)  # Error: DetachedInstanceError

# RIGHT - access relationships before commit or merge back
project = Project.query.get(1)
shop_name = project.shop.name  # Access before commit
db.session.commit()
```

### 3. N+1 Query Problem
```python
# WRONG - queries shop for each project (N+1)
projects = Project.query.all()
for project in projects:
    print(project.shop.name)  # Separate query each time

# RIGHT - use eager loading
projects = Project.query.options(db.joinedload(Project.shop)).all()
for project in projects:
    print(project.shop.name)  # No extra queries
```

### 4. Unique Constraint Violations
```python
# Handle gracefully
try:
    shop = Shop(mergado_shop_id='shop123', name='Test')
    db.session.add(shop)
    db.session.commit()
except IntegrityError as e:
    db.session.rollback()
    if 'unique constraint' in str(e).lower():
        # Shop already exists
        shop = Shop.query.filter_by(mergado_shop_id='shop123').first()
    else:
        raise
```

## Performance Tips

- Use `db.session.bulk_insert_mappings()` for bulk inserts
- Add indexes on columns used in WHERE/ORDER BY
- Use `lazy='dynamic'` for relationships that query often
- Avoid loading unnecessary columns with `defer()` or `load_only()`
- Use pagination for large result sets

## References

- [Database Migration Skill](../../.claude/skills/database-migration.md)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Flask-SQLAlchemy Documentation](https://flask-sqlalchemy.palletsprojects.com/)
