# Quick Start Guide

Get your Mergado Shopify Import & Sync running in 5 minutes!

## Prerequisites

- Python 3.11+ installed
- Mergado account with OAuth application set up
- PostgreSQL installed (or use SQLite for quick testing)

## Setup Steps

### 1. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
# Required:
#   MERGADO_CLIENT_ID=your_client_id
#   MERGADO_CLIENT_SECRET=your_client_secret
#   MERGADO_REDIRECT_URI=http://localhost:5000/auth/callback
#   FLASK_SECRET_KEY=generate_with_python_secrets
```

### 2. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
# Set Flask app
export FLASK_APP=main.py

# Run migrations
flask db upgrade
```

### 4. Start Application

```bash
python main.py
```

Open browser: `http://localhost:5000`

## First Import Workflow

### Step 1: Authenticate
1. Visit `http://localhost:5000`
2. Click "Connect to Mergado"
3. Authorize the application

### Step 2: Select Project
1. Navigate to **Projects** page
2. Enter your Mergado Shop ID (find it in Mergado app URL)
3. Click "Load Projects"
4. Select your project

### Step 3: Import Products
1. Navigate to **Import** page
2. Click "Generate Preview"
3. Review what will be created/updated
4. Click "Start Import"
5. Watch real-time progress
6. Click "Write Back IDs" to sync Shopify IDs to Mergado

### Step 4: Configure Sync (Optional)
1. Navigate to **Sync** page
2. Enter your project ID
3. Enable stock and/or price sync
4. Set sync interval (minimum 15 minutes)
5. Click "Save Configuration"
6. Test with "Run Now" button

## Docker Quick Start

Even faster with Docker Compose:

```bash
# Set Mergado credentials in .env
cp .env.example .env
# Edit MERGADO_* variables

# Start services
docker-compose up --build

# In another terminal, run migrations
docker-compose exec web flask db upgrade

# Open: http://localhost:5000
```

## Troubleshooting

### Port 5000 Already in Use

```bash
# Change port in .env
PORT=8000

# Or kill existing process
lsof -ti:5000 | xargs kill
```

### Database Connection Failed

SQLite (quick test):
```bash
# .env
DATABASE_URL=sqlite:///mergado_app.db
```

PostgreSQL (production):
```bash
# Install and start PostgreSQL
brew install postgresql@15
brew services start postgresql@15

# Create database
createdb shopify_connector

# .env
DATABASE_URL=postgresql://localhost:5432/shopify_connector
```

### OAuth Callback Mismatch

Make sure your Mergado OAuth app redirect URI **exactly** matches how you run the app:

- **Running locally (no Docker):** `http://localhost:5000/auth/callback`
- **Running with Docker:** `http://localhost:5001/auth/callback` (app is on port 5001)

In Mergado’s developer dashboard, add the same URI to the app’s allowed redirect URIs. If it doesn’t match, Mergado can return **HTTP 500** or “unable to handle this request”.

### HTTP 500 from app.mergado.com

If you see “This page isn’t working – app.mergado.com is currently unable to handle this request – HTTP ERROR 500” when logging in:

1. **Redirect URI mismatch**  
   The redirect URI in your `.env` must match **both**:
   - The port you use in the browser (e.g. `http://localhost:5001/auth/callback` when using Docker).
   - The redirect URI configured in the Mergado app settings.

2. **Update Mergado app settings**  
   In the Mergado app (developer/oauth settings), set the redirect URI to exactly:
   - `http://localhost:5001/auth/callback` when using Docker, or  
   - `http://localhost:5000/auth/callback` when running with `python main.py` on port 5000.

3. **Restart after changing .env**  
   If you change `MERGADO_REDIRECT_URI` in `.env`, restart the app (e.g. `docker-compose restart web`).

### Import Stuck or Slow

- Large feeds can take time (monitor SSE progress)
- Check network connectivity to Mergado/Shopify
- Review logs at `/import/logs`

## Verify Installation

Check health endpoint:
```bash
curl http://localhost:5000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "mergado-shopify-import-sync",
  "checks": {
    "database": "healthy"
  }
}
```

## Next Steps

1. **Test Import**: Start with a small project (10-20 products)
2. **Review Logs**: Check import logs for any errors
3. **Configure Sync**: Enable automatic stock/price updates
4. **Monitor**: Keep an eye on `/health` and logs

## Need Help?

- Check full documentation in `README.md`
- Review architecture in `docs/architecture.md`
- See OAuth details in `docs/OAUTH_APPROACH.md`
- Read project guide in `CLAUDE.md`

---

**Ready to sync!** 🚀
