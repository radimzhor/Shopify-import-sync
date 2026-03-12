#!/usr/bin/env bash
# Startup script for Render: runs migrations then starts gunicorn

set -e

echo "Running database migrations..."
export FLASK_APP=main.py
flask db upgrade || echo "Migration failed or no migrations to run"

echo "Starting gunicorn..."
exec gunicorn main:app --workers 2 --threads 4 --bind 0.0.0.0:$PORT --timeout 300 --log-level info
