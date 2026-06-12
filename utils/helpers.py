"""
utils/helpers.py - Helper utilities
College Placement Prediction System
"""

import os
import sqlite3

import joblib
import pandas as pd
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config

MODEL_PATH = Config.MODEL_PATH

FEATURE_COLS = [
    'cgpa', 'tenth_percentage', 'twelfth_percentage',
    'aptitude_score', 'coding_score', 'communication_score',
    'internship', 'projects', 'backlogs',
    'academic_avg', 'skill_avg', 'experience_score'
]

_MODEL_CACHE = None


def load_model():
    """Load and cache the trained model bundle."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model file not found at {MODEL_PATH}. Run `python train_model.py` first."
            )
        _MODEL_CACHE = joblib.load(MODEL_PATH)
    return _MODEL_CACHE


def rows_to_dicts(rows):
    """Convert sqlite3.Row objects into plain dicts (JSON serializable)."""
    return [dict(r) for r in rows]


def predict_placement(data):
    """Run a placement prediction.

    Returns (placed: int, probability_percent: float).
    """
    model_data = load_model()
    pipeline = model_data['pipeline']

    cgpa = float(data['cgpa'])
    tenth = float(data['tenth_percentage'])
    twelfth = float(data['twelfth_percentage'])
    apt = float(data['aptitude_score'])
    code = float(data['coding_score'])
    comm = float(data['communication_score'])
    intern = int(data['internship'])
    proj = int(data['projects'])
    back = int(data['backlogs'])

    row = {
        'cgpa': cgpa, 'tenth_percentage': tenth, 'twelfth_percentage': twelfth,
        'aptitude_score': apt, 'coding_score': code, 'communication_score': comm,
        'internship': intern, 'projects': proj, 'backlogs': back,
        'academic_avg': (cgpa * 10 + tenth + twelfth) / 3,
        'skill_avg': (apt + code + comm) / 3,
        'experience_score': intern * 10 + proj * 5
    }
    X = pd.DataFrame([row], columns=FEATURE_COLS)

    prob = float(pipeline.predict_proba(X)[0][1])
    placed = int(pipeline.predict(X)[0])
    return placed, round(prob * 100, 2)


def get_model_info():
    model_data = load_model()
    return {
        'model_name': model_data['model_name'],
        'accuracy': round(model_data['accuracy'] * 100, 2),
        'precision': round(model_data['precision'] * 100, 2),
        'recall': round(model_data['recall'] * 100, 2),
        'f1': round(model_data['f1'] * 100, 2),
        'roc_auc': round(model_data.get('roc_auc', 0) * 100, 2),
        'cv_accuracy': round(model_data.get('cv_accuracy', 0) * 100, 2),
        'all_results': {
            k: {m: round(v * 100, 2) for m, v in r.items()}
            for k, r in model_data['all_results'].items()
        }
    }


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    return check_password_hash(stored_hash, password)


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            email TEXT,
            branch TEXT,
            cgpa REAL,
            tenth_percentage REAL,
            twelfth_percentage REAL,
            aptitude_score INTEGER,
            coding_score INTEGER,
            communication_score INTEGER,
            internship INTEGER DEFAULT 0,
            projects INTEGER DEFAULT 0,
            backlogs INTEGER DEFAULT 0,
            prediction INTEGER DEFAULT NULL,
            probability REAL DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    ''')
    conn.commit()

    # Seed a default admin with a *hashed* password if none exists.
    existing = c.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    if existing == 0:
        c.execute(
            "INSERT INTO admins (username, password) VALUES (?, ?)",
            (Config.DEFAULT_ADMIN_USERNAME, hash_password(Config.DEFAULT_ADMIN_PASSWORD)),
        )
        conn.commit()

    _migrate_plaintext_admins(conn)
    conn.close()


def _migrate_plaintext_admins(conn):
    """Upgrade any legacy plaintext admin passwords to hashes in place."""
    c = conn.cursor()
    for admin in c.execute("SELECT id, password FROM admins").fetchall():
        admin_id, pwd = admin[0], admin[1]
        if not str(pwd).startswith(("pbkdf2:", "scrypt:")):
            c.execute(
                "UPDATE admins SET password=? WHERE id=?",
                (hash_password(pwd), admin_id),
            )
    conn.commit()
