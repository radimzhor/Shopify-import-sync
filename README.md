# Mergado Shopify Import & Sync

A production-ready Flask application for synchronizing products between Mergado and Shopify.

## Features

- **OAuth 2.0 Authentication**: Secure Mergado OAuth integration with localStorage token management
- **Product Import**: Import products from Mergado CSV feeds to Shopify with SKU-based matching
- **Real-time Progress**: Server-Sent Events (SSE) for live import progress tracking
- **Shopify ID Writeback**: Automatic writeback of Shopify IDs to Mergado via batch_rewriting rules
- **Stock & Price Sync**: Configurable automatic synchronization of inventory and prices
- **Import Logging**: Persistent import history with detailed logs and CSV export
- **Modern UI**: Built with Mergado UI System (MUS) components
- **Production Ready**: Docker support, health checks, rate limiting, and CI/CD

## Architecture

- **Backend**: Python 3.11, Flask 2.3.3, SQLAlchemy, PostgreSQL
- **Frontend**: Jinja2 templates, Mergado UI System (MUS), Bootstrap 5
- **Database**: PostgreSQL with Flask-Migrate (Alembic) migrations
- **Deployment**: Docker, Render.com, GitHub Actions CI/CD

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (or use SQLite for development)
- Mergado account with OAuth application credentials

### Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd Shopify_connector-main
```

2. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your Mergado OAuth credentials
```

5. Initialize database:
```bash
export FLASK_APP=main.py
flask db upgrade
```

6. Run the application:
```bash
python main.py
```

The application will be available at `http://localhost:5000`

### Docker Development

1. Start services with Docker Compose:
```bash
docker-compose up --build
```

2. Run migrations:
```bash
docker-compose exec web flask db upgrade
```

## Configuration

### Environment Variables

Required:
- `MERGADO_CLIENT_ID`: Your Mergado OAuth client ID
- `MERGADO_CLIENT_SECRET`: Your Mergado OAuth client secret
- `MERGADO_REDIRECT_URI`: OAuth callback URL (e.g., `http://localhost:5000/callback`)
- `FLASK_SECRET_KEY`: Secret key for Flask sessions (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

Optional:
- `DATABASE_URL`: Database connection string (default: SQLite)
- `FLASK_ENV`: Environment (development/production)
- `FLASK_DEBUG`: Enable debug mode (true/false)
- `LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `LOG_FORMAT`: Log format (json/text)

### Database Migrations

Create new migration:
```bash
flask db migrate -m "Description of changes"
```

Apply migrations:
```bash
flask db upgrade
```

Rollback migration:
```bash
flask db downgrade
```

## Usage

### 1. Select Project

Navigate to `/projects` and enter your Mergado Shop ID to load available projects.

### 2. Import Products

1. Go to `/import`
2. Generate preview to see what will be created/updated
3. Start import and monitor progress in real-time
4. Writeback Shopify IDs to Mergado

### 3. Configure Sync

1. Go to `/sync`
2. Enable stock and/or price synchronization
3. Set sync interval (minimum 15 minutes)
4. Run manual sync or let it run automatically

### 4. View Logs

Navigate to `/import/logs` to view import history and download CSV reports.

## API Endpoints

### Import
- `POST /api/import/preview` - Generate import preview
- `POST /api/import/start` - Start import job
- `GET /api/import/progress/<job_id>` - Stream import progress (SSE)
- `POST /api/import/writeback/<job_id>` - Writeback Shopify IDs
- `GET /api/import/history` - Get import job history
- `GET /api/import/logs/<job_id>` - Get detailed logs
- `GET /api/import/logs/<job_id>/download` - Download logs as CSV

### Sync
- `GET /api/sync/config` - Get sync configurations
- `POST /api/sync/config` - Create/update sync config
- `DELETE /api/sync/config/<config_id>` - Delete sync config
- `POST /api/sync/execute` - Execute sync immediately
- `GET /api/sync/logs` - Get sync execution logs

### Projects
- `GET /api/project/shops` - List shops
- `GET /api/project/shops/<shop_id>/projects` - List projects for shop
- `GET /api/project/<project_id>` - Get project details

## Testing

Run tests:
```bash
pytest tests/ -v
```

With coverage:
```bash
pytest tests/ -v --cov=app --cov-report=html
```

## Deployment

### Deploy for Mergado Store (GitHub + Render)

To use the app as a **Mergado Store extension**, it must be at a **public URL** (localhost is not usable from [store.mergado.com](https://store.mergado.com/)).

**Step-by-step:** See **[docs/DEPLOY_MERGADO_STORE.md](docs/DEPLOY_MERGADO_STORE.md)** for GitHub + Render setup, environment variables, running migrations, and configuring the redirect URI and app URL in Mergado.

### Render.com (summary)

1. Push the repo to GitHub and connect it to Render.
2. Use the **render.yaml** blueprint to create the Web Service and PostgreSQL database.
3. Set environment variables (especially `MERGADO_REDIRECT_URI=https://<your-app>.onrender.com/auth/callback`).
4. Run database migrations once via Render Shell: `flask db upgrade`.
5. In Mergado app settings, set the redirect URI and extension URL to your Render URL.

The application includes:
- Health check endpoint at `/health`
- Multi-worker Gunicorn configuration
- Request logging and error handling

### Docker Production

Build and run:
```bash
docker build -t shopify-connector .
docker run -p 5000:5000 \
  -e DATABASE_URL="postgresql://..." \
  -e MERGADO_CLIENT_ID="..." \
  -e MERGADO_CLIENT_SECRET="..." \
  -e FLASK_SECRET_KEY="..." \
  shopify-connector
```

## Development

### Code Quality

Format code:
```bash
black .
isort .
```

Lint code:
```bash
flake8 . --max-line-length=100
```

### Project Structure

```
.
├── app/
│   ├── __init__.py           # App initialization, db/migrate setup
│   ├── auth/                 # OAuth authentication
│   ├── middleware/           # Error handlers, logging, rate limiting
│   ├── models/              # SQLAlchemy database models
│   ├── routes/              # Flask blueprints and routes
│   ├── services/            # Business logic and API clients
│   └── templates/           # Jinja2 HTML templates
├── migrations/              # Alembic database migrations
├── tests/                   # Test suite
├── config.py               # Flask app configuration
├── main.py                 # Application entrypoint
├── settings.py             # Pydantic settings management
├── requirements.txt        # Python dependencies
├── Dockerfile              # Production container
├── docker-compose.yml      # Local development
└── render.yaml            # Render.com deployment config
```

## Documentation

- `/docs/architecture.md` - System architecture and data flows
- `/docs/OAUTH_APPROACH.md` - OAuth implementation details
- `/CLAUDE.md` - Project overview and development guide
- `.claude/skills/` - Reusable development workflows
- `docs/adr/` - Architectural decision records

## License

See LICENSE file for details.

## Support

For issues and questions, please open a GitHub issue.
