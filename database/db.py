"""
database/db.py - PostgreSQL connection module (Supabase)
College Placement Prediction System
"""

import os
import psycopg2
import psycopg2.pool
import psycopg2.extras
import psycopg2.errors
from dotenv import load_dotenv

load_dotenv()

# ─── Credentials from environment ────────────────────────────
_HOST     = os.environ.get('SUPABASE_DB_HOST', '')
_PORT     = int(os.environ.get('SUPABASE_DB_PORT', 5432))
_DBNAME   = os.environ.get('SUPABASE_DB_NAME', 'postgres')
_USER     = os.environ.get('SUPABASE_DB_USER', 'postgres')
_PASSWORD = os.environ.get('SUPABASE_DB_PASSWORD', '')

# ─── Connection pool (min 1, max 10) ─────────────────────────
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return (or lazily create) the global connection pool."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=_HOST,
            port=_PORT,
            dbname=_DBNAME,
            user=_USER,
            password=_PASSWORD,
            sslmode='require',
            connect_timeout=10,
        )
    return _pool


def get_db() -> psycopg2.extensions.connection:
    """Borrow a connection from the pool. Use close_db() to return it."""
    pool = _get_pool()
    conn = pool.getconn()
    # RealDictCursor makes every row behave like a dict (replaces sqlite3.Row)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def close_db(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool."""
    try:
        _get_pool().putconn(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def _column_exists(cursor, table: str, column: str) -> bool:
    """Check whether a column already exists in a table."""
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


def init_db() -> None:
    """Create all tables and seed the default admin user."""
    from utils.helpers import hash_password  # local import to avoid circular dep

    conn = get_db()
    try:
        cur = conn.cursor()

        # ── students ──────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id                  SERIAL PRIMARY KEY,
                name                TEXT NOT NULL,
                roll_no             TEXT UNIQUE NOT NULL,
                email               TEXT,
                branch              TEXT,
                cgpa                REAL,
                tenth_percentage    REAL,
                twelfth_percentage  REAL,
                aptitude_score      INTEGER,
                coding_score        INTEGER,
                communication_score INTEGER,
                internship          INTEGER DEFAULT 0,
                projects            INTEGER DEFAULT 0,
                backlogs            INTEGER DEFAULT 0,
                prediction          INTEGER DEFAULT NULL,
                probability         REAL    DEFAULT NULL,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── users ─────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                    SERIAL PRIMARY KEY,
                username              TEXT UNIQUE NOT NULL,
                email                 TEXT UNIQUE,
                password              TEXT NOT NULL,
                role                  TEXT NOT NULL DEFAULT 'student',
                full_name             TEXT,
                college               TEXT,
                branch                TEXT,
                year                  TEXT,
                cgpa                  REAL,
                skills                TEXT,
                phone                 TEXT,
                profile_picture       TEXT,
                resume_filename       TEXT,
                resume_uploaded_at    TEXT,
                resume_text           TEXT,
                resume_analysis       TEXT,
                resume_score          REAL,
                readiness_score       REAL,
                skill_gap             TEXT,
                career_recommendations TEXT,
                learning_roadmap      TEXT,
                company_name          TEXT,
                company_address       TEXT,
                company_website       TEXT,
                created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── admins (legacy) ───────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id       SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        # ── jobs ──────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          SERIAL PRIMARY KEY,
                company_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title       TEXT NOT NULL,
                description TEXT,
                requirements TEXT,
                salary_min  REAL,
                salary_max  REAL,
                location    TEXT,
                job_type    TEXT,
                posted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── applications ──────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id         SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id     INTEGER NOT NULL REFERENCES jobs(id)  ON DELETE CASCADE,
                company_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status     TEXT DEFAULT 'applied',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Indexes ───────────────────────────────────────────
        cur.execute("CREATE INDEX IF NOT EXISTS idx_students_email   ON students(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_students_branch  ON students(branch)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role       ON users(role)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company     ON jobs(company_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_apps_student     ON applications(student_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_apps_job         ON applications(job_id)")

        # ── Seed default admin ────────────────────────────────
        cur.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO users (username, email, password, role, full_name)
                VALUES (%s, %s, %s, %s, %s)
                """,
                ('admin', 'admin@placeiq.local', hash_password('admin123'),
                 'admin', 'Platform Administrator'),
            )

        conn.commit()
        cur.close()
        print("[db] PostgreSQL schema initialised successfully.")
    except Exception as exc:
        conn.rollback()
        print(f"[db] init_db error: {exc}")
        raise
    finally:
        close_db(conn)


def ping() -> bool:
    """Return True if the database is reachable."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        close_db(conn)
        return True
    except Exception as exc:
        print(f"[db] ping failed: {exc}")
        return False
