"""
api/index.py — Vercel serverless entrypoint.
Vercel's Python runtime discovers the WSGI app via the `app` variable in this file.
We simply import the Flask app from the project root.
"""
import sys
import os

# Ensure the project root (parent of api/) is on sys.path so `app` and `utils` are importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: F401 — Vercel needs this name

# Vercel calls this as a WSGI handler
handler = app
