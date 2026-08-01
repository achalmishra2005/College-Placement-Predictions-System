"""
migrate_to_postgres.py
──────────────────────
One-time migration script: copies all data from the local SQLite database
(database/placement.db) into Supabase PostgreSQL.

Usage:
    1. Fill in your .env file with SUPABASE_DB_* credentials.
    2. Run:  python migrate_to_postgres.py

Safe to run multiple times — uses ON CONFLICT DO NOTHING for all inserts.
"""

import os
import sys
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# ── Make sure the project root is on the path ─────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import get_db, close_db, init_db

SQLITE_PATH = os.path.join(os.path.dirname(__file__), 'database', 'placement.db')


def get_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_students(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute('SELECT * FROM students').fetchall()
    if not rows:
        print('  [students] 0 rows — skipping.')
        return 0

    cur = pg_conn.cursor()
    inserted = 0
    for r in rows:
        cur.execute(
            """
            INSERT INTO students
              (name, roll_no, email, branch, cgpa,
               tenth_percentage, twelfth_percentage,
               aptitude_score, coding_score, communication_score,
               internship, projects, backlogs, prediction, probability, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (roll_no) DO NOTHING
            """,
            (
                r['name'], r['roll_no'], r['email'], r['branch'], r['cgpa'],
                r['tenth_percentage'], r['twelfth_percentage'],
                r['aptitude_score'], r['coding_score'], r['communication_score'],
                r['internship'], r['projects'], r['backlogs'],
                r['prediction'], r['probability'], r['created_at'],
            )
        )
        if cur.rowcount:
            inserted += 1
    pg_conn.commit()
    cur.close()
    print(f'  [students] {inserted}/{len(rows)} rows migrated.')
    return inserted


def migrate_users(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute('SELECT * FROM users').fetchall()
    if not rows:
        print('  [users] 0 rows — skipping.')
        return 0

    cur = pg_conn.cursor()
    inserted = 0
    for r in rows:
        cur.execute(
            """
            INSERT INTO users
              (username, email, password, role, full_name,
               college, branch, year, cgpa, skills, phone,
               profile_picture, resume_filename, resume_uploaded_at,
               resume_text, resume_analysis, resume_score, readiness_score,
               skill_gap, career_recommendations, learning_roadmap,
               company_name, company_address, company_website, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (username) DO NOTHING
            """,
            (
                r['username'], r['email'], r['password'], r['role'], r['full_name'],
                r['college'], r['branch'], r['year'], r['cgpa'], r['skills'], r['phone'],
                r['profile_picture'], r['resume_filename'], r['resume_uploaded_at'],
                r['resume_text'], r['resume_analysis'], r['resume_score'], r['readiness_score'],
                r['skill_gap'], r['career_recommendations'], r['learning_roadmap'],
                r['company_name'], r['company_address'], r['company_website'],
                r['created_at'],
            )
        )
        if cur.rowcount:
            inserted += 1
    pg_conn.commit()
    cur.close()
    print(f'  [users] {inserted}/{len(rows)} rows migrated.')
    return inserted


def migrate_admins(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute('SELECT * FROM admins').fetchall()
    if not rows:
        print('  [admins] 0 rows — skipping.')
        return 0

    cur = pg_conn.cursor()
    inserted = 0
    for r in rows:
        cur.execute(
            """
            INSERT INTO admins (username, password)
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            (r['username'], r['password'])
        )
        if cur.rowcount:
            inserted += 1
    pg_conn.commit()
    cur.close()
    print(f'  [admins] {inserted}/{len(rows)} rows migrated.')
    return inserted


def migrate_jobs(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute('SELECT * FROM jobs').fetchall()
    if not rows:
        print('  [jobs] 0 rows — skipping.')
        return 0

    cur = pg_conn.cursor()
    inserted = 0
    for r in rows:
        cur.execute(
            """
            INSERT INTO jobs
              (company_id, title, description, requirements,
               salary_min, salary_max, location, job_type, posted_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                r['company_id'], r['title'], r['description'], r['requirements'],
                r['salary_min'], r['salary_max'], r['location'], r['job_type'], r['posted_at'],
            )
        )
        if cur.rowcount:
            inserted += 1
    pg_conn.commit()
    cur.close()
    print(f'  [jobs] {inserted}/{len(rows)} rows migrated.')
    return inserted


def migrate_applications(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute('SELECT * FROM applications').fetchall()
    if not rows:
        print('  [applications] 0 rows — skipping.')
        return 0

    cur = pg_conn.cursor()
    inserted = 0
    for r in rows:
        cur.execute(
            """
            INSERT INTO applications
              (student_id, job_id, company_id, status, applied_at)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (r['student_id'], r['job_id'], r['company_id'], r['status'], r['applied_at'])
        )
        if cur.rowcount:
            inserted += 1
    pg_conn.commit()
    cur.close()
    print(f'  [applications] {inserted}/{len(rows)} rows migrated.')
    return inserted


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f'SQLite DB not found at: {SQLITE_PATH}')
        print('Nothing to migrate.')
        return

    print('=' * 60)
    print('SQLite → Supabase PostgreSQL Migration')
    print('=' * 60)

    # Ensure PostgreSQL schema exists
    print('\n[1] Initialising PostgreSQL schema...')
    try:
        init_db()
        print('    Schema ready.')
    except Exception as e:
        print(f'    ERROR: {e}')
        print('    Check your SUPABASE_DB_* environment variables in .env')
        sys.exit(1)

    # Open SQLite
    print(f'\n[2] Opening SQLite: {SQLITE_PATH}')
    sqlite_conn = get_sqlite()

    # Open PostgreSQL
    print('\n[3] Opening PostgreSQL connection...')
    pg_conn = get_db()

    print('\n[4] Migrating tables...')
    # Order matters: users before jobs/applications (FK constraints)
    migrate_users(sqlite_conn, pg_conn)
    migrate_admins(sqlite_conn, pg_conn)
    migrate_students(sqlite_conn, pg_conn)
    migrate_jobs(sqlite_conn, pg_conn)
    migrate_applications(sqlite_conn, pg_conn)

    sqlite_conn.close()
    close_db(pg_conn)

    print('\n' + '=' * 60)
    print('Migration complete!')
    print('Run python test_postgres.py to verify.')
    print('=' * 60)


if __name__ == '__main__':
    main()
