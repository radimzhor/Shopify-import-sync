# Pre-Commit Hook

## Automatic Code Quality Checks

Before any commit, ensure code meets quality standards.

### Format Code
```bash
black . --line-length 100
isort .
```

### Lint Code
```bash
flake8 app/ tests/ --max-line-length=100 --exclude=migrations
```

### Type Check (if using mypy)
```bash
mypy app/ --ignore-missing-imports
```

### Run Quick Tests
```bash
pytest tests/ -x  # Stop on first failure
```

## Manual Pre-Commit Checklist

Before committing, verify:

- [ ] Code formatted with black and isort
- [ ] No flake8 violations
- [ ] All tests passing
- [ ] No debug print statements or commented code
- [ ] No hardcoded secrets or tokens
- [ ] Docstrings added for new functions
- [ ] Type hints on function signatures
- [ ] Git commit message is descriptive

## Flake8 Configuration

Key rules (in `.flake8` or `setup.cfg`):
```ini
[flake8]
max-line-length = 100
exclude = .git,__pycache__,migrations,venv
ignore = E203, W503  # Black compatibility
```

## Black Configuration

In `pyproject.toml`:
```toml
[tool.black]
line-length = 100
target-version = ['py311']
exclude = '''
/(
    \.git
  | \.venv
  | migrations
)/
'''
```

## Isort Configuration

In `pyproject.toml` or `.isort.cfg`:
```toml
[tool.isort]
profile = "black"
line_length = 100
skip = [".git", ".venv", "migrations"]
```

## Git Hooks Setup (Optional)

Install pre-commit framework:
```bash
pip install pre-commit
```

Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
        args: [--line-length=100]
  
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: [--profile=black]
  
  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=100]
```

Install hooks:
```bash
pre-commit install
```

Now these checks run automatically before each commit.

## What to Do If Checks Fail

### Black/Isort Failures
```bash
# Just run the formatters - they fix issues automatically
black . --line-length 100
isort .
git add .
git commit
```

### Flake8 Failures
```bash
# Fix issues manually based on error messages
flake8 app/  # See what's wrong
# Fix the issues
git add .
git commit
```

### Test Failures
```bash
# Fix failing tests first
pytest tests/test_failing.py -v
# Fix the code or test
# Commit when green
```

## Skip Hooks (Use Sparingly)

Only in emergencies:
```bash
git commit --no-verify
```

**When to skip:**
- Work in progress commit (WIP)
- Hotfix that must be deployed immediately
- Known issue that will be fixed in next commit

**Never skip for:**
- "I don't want to fix formatting"
- "Tests take too long"
- "Flake8 is annoying"
