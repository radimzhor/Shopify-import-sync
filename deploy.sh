#!/bin/bash
# Quick deployment script for Render.com

echo "🚀 Deploying bug fixes to Render.com..."

# Check if we're in a git repo
if [ ! -d .git ]; then
    echo "❌ Error: Not a git repository. Please initialize git first."
    exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --staged --quiet; then
    echo "📝 Committing changes..."
    git add app/routes/import_routes.py app/routes/project_routes.py BUGFIX_preview_failed.md
    git commit -m "fix: preview generation - project ID mismatch and missing output_url

- Accept both database ID and Mergado project ID in preview endpoint
- Fetch full project details including output URL when syncing projects
- Add detailed error logging and contextual error messages
- Improve error handling for missing project configuration

Fixes #1 - Preview failed error
"
    echo "✅ Changes committed"
else
    echo "ℹ️  No changes to commit"
fi

# Push to main branch (triggers auto-deploy on Render)
echo "📤 Pushing to main branch..."
git push origin main

echo ""
echo "✅ Deployment triggered!"
echo ""
echo "📊 Monitor deployment at: https://dashboard.render.com/"
echo "📝 Check logs for: 'Fetched project {id} details'"
echo ""
echo "🧪 After deployment, test by:"
echo "   1. Go to Projects page"
echo "   2. Load your projects (this will fetch output URLs)"
echo "   3. Select a project and generate preview"
