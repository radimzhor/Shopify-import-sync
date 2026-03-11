# Shopify Import & Sync - Claude Context

## Purpose

**Mergado Shopify Import & Sync** is a Flask-based extension for the Mergado Store platform that:
- Imports products from Mergado projects (Shopify CSV feeds) into Shopify stores via Keychain Proxy
- Writes Shopify product/variant IDs back to Mergado using batch rewriting rules
- Synchronizes stock quantities and prices from Mergado to Shopify on a schedule

**Target Users**: Mergado merchants who want to manage product data in Mergado and sync to Shopify.

**Key Constraint**: All Shopify API calls go through Mergado's Keychain Proxy. No direct Shopify authentication.

## Repo Map

```
Shopify_connector-main/
├── CLAUDE.md                   # You are here (north star)
├── .claude/
│   ├── skills/                 # Reusable workflows
│   └── hooks/                  # Guardrails
├── app/
│   ├── __init__.py
│   ├── auth/
│   │   ├── CLAUDE.md           # OAuth gotchas
│   │   └── oauth.py            # Mergado OAuth2 flow
│   ├── models/
│   │   └── CLAUDE.md           # Database schema rules
│   ├── routes/
│   │   └── main.py             # Web routes
│   ├── services/
│   │   ├── CLAUDE.md           # API client patterns
│   │   ├── mergado_client.py   # Mergado API wrapper
│   │   └── shopify_proxy.py    # Shopify via Keychain Proxy
│   ├── middleware/
│   │   ├── CLAUDE.md           # Request lifecycle
│   │   ├── logging.py
│   │   └── error_handlers.py
│   └── templates/              # Jinja2 templates (use MUS components)
├── tests/                      # Pytest suite
├── docs/
│   ├── architecture.md         # System diagrams
│   ├── adr/                    # Architecture Decision Records
│   ├── api/                    # API integration guides
│   ├── mergado.apib            # Mergado API Blueprint
│   └── Shopify csv template.csv
├── config.py                   # Flask app factory
├── settings.py                 # Pydantic settings
├── main.py                     # Entry point
└── requirements.txt
```

## Tech Stack

- **Backend**: Flask 2.3.3, Python 3.11
- **Database**: PostgreSQL (via SQLAlchemy + Alembic)
- **Frontend**: Jinja2 + Mergado UI System (MUS) components
- **APIs**: Mergado API + Shopify (via Keychain Proxy)
- **Auth**: OAuth 2.0 (Mergado)
- **Deployment**: Docker + Render.com

## Core Rules

### Code Quality
- **Formatting**: Use `black` (line length 100), `isort`, `flake8`
- **Type Hints**: Full type annotations on all functions
- **Testing**: 80%+ coverage (pytest), run tests before commits
- **Docstrings**: Required for services, models, and complex functions

### API Integration
- **Mergado API**: Use `MergadoClient` service (see `.claude/skills/api-integration.md`)
- **Shopify API**: Always via `/shops/{id}/shopify/proxy/{path}` (never direct)
- **Error Handling**: Retry with exponential backoff (429, 502, 503, 504 status codes)
- **Rate Limiting**: Shopify REST = 2 req/sec, respect `Retry-After` headers

### Database
- **Migrations**: Use Alembic (see `.claude/skills/database-migration.md`)
- **Models**: Keep in `app/models/`, use SQLAlchemy ORM
- **Naming**: snake_case for tables/columns, PascalCase for model classes

### Security
- **OAuth Tokens**: Stored in localStorage (client-side) for MVP, never log tokens
- **Input Validation**: Pydantic models for request/response validation
- **Protected Paths**: Get approval before editing `app/auth/`, `migrations/`, deployment configs
- **Security Note**: Can improve OAuth security post-MVP (HttpOnly cookies, server sessions)

### Frontend
- **Components**: Use Mergado UI System (https://mus.mergado.com/)
- **Templates**: Extend `base.html`, keep logic minimal
- **JavaScript**: Vanilla JS for interactions, SSE for progress updates

## Common Commands

### Development
```bash
# Setup
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run
python main.py  # Dev server on http://localhost:5000

# Format code
black . --line-length 100
isort .
flake8 app/ tests/

# Tests
pytest --cov=app --cov-report=html
open htmlcov/index.html  # View coverage

# Database migrations
flask db init  # One-time setup
flask db migrate -m "Description"
flask db upgrade
```

### Docker
```bash
docker build -t shopify-connector .
docker run -p 5000:5000 --env-file .env shopify-connector
```

### Deployment
```bash
# Render.com auto-deploys on push to main
# Manual deploy: see .claude/skills/deployment.md
```

## Key Workflows

- **Adding API Integration**: See `.claude/skills/api-integration.md`
- **Database Changes**: See `.claude/skills/database-migration.md`
- **Testing**: See `.claude/skills/testing-workflow.md`
- **Deployment**: See `.claude/skills/deployment.md`

## Architecture Decision Records

Key technical decisions documented in `docs/adr/`:
- `001-batch-rewriting-for-shopify-ids.md` - Why batch_rewriting rule type
- `002-mergado-ui-system-frontend.md` - Why MUS components
- `003-keychain-proxy-shopify-auth.md` - Why proxy instead of direct API

## Quick Reference

### OAuth Scopes Required
```
shop.read, shop.projects.read, shop.proxy.read, shop.proxy.write,
project.read, project.elements.read, project.elements.write,
project.products.read, project.rules.write, project.queries.write
```

### Key Mergado API Endpoints
- `GET /shops/{id}/projects/` - List projects
- `GET /projects/{id}/` - Get project details (includes output URL)
- `POST /projects/{id}/elements/` - Create element (e.g., shopify_id)
- `POST /projects/{id}/rules/` - Create batch_rewriting rule
- `GET /shops/{id}/shopify/proxy/{path}` - Proxy to Shopify API

### Shopify CSV Format
See `docs/Shopify csv template.csv` for exact column structure.
Required: Handle, Title, Variant SKU, Variant Price, Status, Published

---

**Last Updated**: 2026-03-04 (during initial setup)
