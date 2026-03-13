#!/usr/bin/env bash
# Startup script for Render: runs migrations then starts gunicorn

set -e

echo "Running database migrations..."
export FLASK_APP=main.py
flask db upgrade

echo "Starting gunicorn..."
exec gunicorn main:app --workers 1 --threads 8 --bind 0.0.0.0:$PORT --timeout 120 --log-level info
