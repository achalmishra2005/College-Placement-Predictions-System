"""
config.py - Application configuration
Loads settings from environment variables with safe defaults so the app
works out-of-the-box in development but stays secure in production.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Core Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DEBUG = _as_bool(os.environ.get("FLASK_DEBUG"), default=False)

    # Paths
    DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "database" / "placement.db"))
    MODEL_PATH = os.environ.get("MODEL_PATH", str(BASE_DIR / "model.pkl"))

    # Default admin (used only when seeding an empty admins table)
    DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Sessions / security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _as_bool(os.environ.get("SESSION_COOKIE_SECURE"), default=False)

    # Optional LLM providers for AI modules (never hardcode keys).
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
