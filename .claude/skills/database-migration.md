# Database Migration Skill

## Creating a New Migration

### 1. Make Model Changes
Edit model in `app/models/`:

```python
# app/models/project.py
from app import db

class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    mergado_project_id = db.Column(db.String(50), unique=True, nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    # NEW FIELD:
    shopify_id_element_id = db.Column(db.String(50), nullable=True)
```

### 2. Generate Migration
```bash
flask db migrate -m "Add shopify_id_element_id to Project"
```

This creates a file in `migrations/versions/xxxx_add_shopify_id_element_id.py`

### 3. Review Migration
**ALWAYS** review the generated migration before applying:

```python
def upgrade():
    # Check: Does this look correct?
    op.add_column('projects', sa.Column('shopify_id_element_id', sa.String(length=50), nullable=True))

def downgrade():
    # Check: Can this be safely reversed?
    op.drop_column('projects', 'shopify_id_element_id')
```

### 4. Test Migration Locally
```bash
# Apply migration
flask db upgrade

# Test your code with the new schema

# Test rollback
flask db downgrade  # Go back one version
flask db upgrade    # Reapply
```

### 5. Commit Migration File
```bash
git add migrations/versions/xxxx_*.py
git commit -m "Add shopify_id_element_id field to Project model"
```

## Common Migration Patterns

### Adding a Column
```python
def upgrade():
    op.add_column('table_name', sa.Column('column_name', sa.String(100), nullable=True))
```

### Adding NOT NULL Column to Existing Table
```python
def upgrade():
    # Step 1: Add column as nullable
    op.add_column('table_name', sa.Column('new_col', sa.String(50), nullable=True))
    
    # Step 2: Populate with default values
    op.execute("UPDATE table_name SET new_col = 'default_value' WHERE new_col IS NULL")
    
    # Step 3: Make it NOT NULL
    op.alter_column('table_name', 'new_col', nullable=False)
```

### Adding Foreign Key
```python
def upgrade():
    op.add_column('child_table', sa.Column('parent_id', sa.Integer(), nullable=False))
    op.create_foreign_key(
        'fk_child_parent',  # constraint name
        'child_table',      # source table
        'parent_table',     # referenced table
        ['parent_id'],      # local column
        ['id']              # remote column
    )
```

### Creating Index
```python
def upgrade():
    op.create_index('idx_projects_shop_id', 'projects', ['shop_id'])
```

### Renaming Column
```python
def upgrade():
    op.alter_column('table_name', 'old_name', new_column_name='new_name')
```

## Migration Safety Checklist

Before `flask db upgrade` in production:

- [ ] Reviewed generated migration code
- [ ] Tested upgrade locally
- [ ] Tested downgrade locally
- [ ] Checked for data loss risks
- [ ] Backed up production database
- [ ] Verified migration is reversible
- [ ] Confirmed no breaking changes for running app instances

## Dangerous Operations

⚠️ **These require extra care in production:**

- Dropping columns (data loss!)
- Dropping tables (data loss!)
- Making columns NOT NULL (fails if existing NULLs)
- Adding UNIQUE constraints (fails if duplicates exist)
- Renaming columns (breaks running code)

**Strategy**: Use multi-step migrations for production:
1. Add new column/table (deploy code that uses both old and new)
2. Migrate data in background
3. Remove old column/table (deploy code that only uses new)

## Troubleshooting

### "Target database is not up to date"
```bash
flask db stamp head  # Mark current state as latest
flask db upgrade
```

### Migration Failed Mid-Way
```bash
# Check current version
flask db current

# Manually fix database if needed

# Mark as applied (if you fixed manually)
flask db stamp <revision_id>
```

### Want to Undo Last Migration
```bash
flask db downgrade  # Go back one version
```

## Models Naming Conventions

- **Table names**: snake_case, plural (e.g., `import_jobs`)
- **Column names**: snake_case (e.g., `created_at`)
- **Foreign keys**: `{singular_table}_id` (e.g., `shop_id`)
- **Indexes**: `idx_{table}_{column}` (e.g., `idx_projects_shop_id`)
- **Constraints**: `fk_{child}_{parent}` (e.g., `fk_projects_shops`)
