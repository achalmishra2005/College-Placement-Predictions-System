"""
test_postgres.py
────────────────
Automated test suite for the Supabase PostgreSQL migration.
Run after filling in your .env file:

    python test_postgres.py

Exit code 0 = all tests passed.
Exit code 1 = one or more failures.
"""

import os
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = '[PASS]'
FAIL = '[FAIL]'
results = []


def test(name, fn):
    try:
        fn()
        print(f'{PASS} {name}')
        results.append((name, True, None))
    except Exception as exc:
        print(f'{FAIL} {name}: {exc}')
        results.append((name, False, str(exc)))


# ── 1. DB connection ──────────────────────────────────────────
def test_connection():
    from database.db import ping
    assert ping(), 'ping() returned False — check SUPABASE_DB_* env vars'

test('DB connection / ping', test_connection)


# ── 2. All tables exist ───────────────────────────────────────
def test_tables():
    from database.db import get_db, close_db
    db = get_db()
    cur = db.cursor()
    for tbl in ('students', 'users', 'jobs', 'applications', 'admins'):
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (tbl,)
        )
        assert cur.fetchone(), f'Table "{tbl}" not found in PostgreSQL'
    cur.close()
    close_db(db)

test('All tables exist', test_tables)


# ── 3. Admin user seeded ──────────────────────────────────────
def test_admin_seeded():
    from database.db import get_db, close_db
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE username = 'admin' AND role = 'admin'")
    row = cur.fetchone()
    cur.close()
    close_db(db)
    assert row, 'Admin user not found — init_db() seeding may have failed'

test('Admin user seeded', test_admin_seeded)


# ── 4. Registration (insert user) ────────────────────────────
_TEST_USER = '__test_migration_user__'
_TEST_EMAIL = '__test@migration.local__'

def test_registration():
    from database.db import get_db, close_db
    from utils.helpers import create_user, get_user_by_username
    db = get_db()
    # Clean up any previous test run
    cur = db.cursor()
    cur.execute("DELETE FROM users WHERE username = %s", (_TEST_USER,))
    db.commit()
    cur.close()

    create_user(db, username=_TEST_USER, password='TestPass123',
                role='student', email=_TEST_EMAIL, full_name='Test User')

    user = get_user_by_username(db, _TEST_USER)
    close_db(db)
    assert user is not None, 'User not found after insert'
    assert user['email'] == _TEST_EMAIL

test('Registration (create_user)', test_registration)


# ── 5. Login — get_user_by_username ───────────────────────────
def test_login_username():
    from database.db import get_db, close_db
    from utils.helpers import get_user_by_username, verify_password
    db = get_db()
    user = get_user_by_username(db, _TEST_USER)
    close_db(db)
    assert user is not None, 'User lookup by username failed'
    assert verify_password('TestPass123', user['password']), 'Password verification failed'

test('Login via username', test_login_username)


# ── 6. Login — get_user_by_email ──────────────────────────────
def test_login_email():
    from database.db import get_db, close_db
    from utils.helpers import get_user_by_email, verify_password
    db = get_db()
    user = get_user_by_email(db, _TEST_EMAIL)
    close_db(db)
    assert user is not None, 'User lookup by email failed'
    assert verify_password('TestPass123', user['password']), 'Password verification failed'

test('Login via email', test_login_email)


# ── 7. Case-insensitive username lookup ───────────────────────
def test_case_insensitive():
    from database.db import get_db, close_db
    from utils.helpers import get_user_by_username
    db = get_db()
    user = get_user_by_username(db, _TEST_USER.upper())
    close_db(db)
    assert user is not None, 'Case-insensitive username lookup failed'

test('Case-insensitive user lookup', test_case_insensitive)


# ── 8. Student CRUD ───────────────────────────────────────────
_TEST_ROLL = 'TESTROLL999'

def test_student_crud():
    from database.db import get_db, close_db
    db = get_db()
    cur = db.cursor()

    # Clean up
    cur.execute("DELETE FROM students WHERE roll_no = %s", (_TEST_ROLL,))
    db.commit()

    # INSERT
    cur.execute("""
        INSERT INTO students (name, roll_no, email, branch, cgpa,
          tenth_percentage, twelfth_percentage, aptitude_score,
          coding_score, communication_score, prediction, probability)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, ('Test Student', _TEST_ROLL, 'test@test.com', 'CS', 8.5,
          90.0, 88.0, 85, 80, 75, 1, 92.5))
    db.commit()

    # READ
    cur.execute("SELECT * FROM students WHERE roll_no = %s", (_TEST_ROLL,))
    row = cur.fetchone()
    assert row is not None, 'Student not found after insert'
    assert row['cgpa'] == 8.5

    # UPDATE
    cur.execute("UPDATE students SET cgpa = %s WHERE roll_no = %s", (9.0, _TEST_ROLL))
    db.commit()
    cur.execute("SELECT cgpa FROM students WHERE roll_no = %s", (_TEST_ROLL,))
    updated = cur.fetchone()
    assert updated['cgpa'] == 9.0, 'Update did not persist'

    # DELETE
    cur.execute("DELETE FROM students WHERE roll_no = %s", (_TEST_ROLL,))
    db.commit()
    cur.execute("SELECT * FROM students WHERE roll_no = %s", (_TEST_ROLL,))
    assert cur.fetchone() is None, 'Delete failed'

    cur.close()
    close_db(db)

test('Student CRUD (insert/read/update/delete)', test_student_crud)


# ── 9. Flask app routes via test client ──────────────────────
def test_flask_routes():
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False

    with flask_app.test_client() as c:
        # Index
        r = c.get('/')
        assert r.status_code == 200, f'/ returned {r.status_code}'

        # Dashboard — requires admin login
        with c.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['user_role'] = 'admin'
            sess['full_name'] = 'Admin'

        r = c.get('/dashboard')
        assert r.status_code == 200, f'/dashboard returned {r.status_code}'

        r = c.get('/admin/students')
        assert r.status_code == 200, f'/admin/students returned {r.status_code}'

        r = c.get('/statistics')
        assert r.status_code == 200, f'/statistics returned {r.status_code}'

test('Flask routes (/, /dashboard, /admin/students, /statistics)', test_flask_routes)


# ── 10. API endpoint ─────────────────────────────────────────
def test_api():
    import json as _json
    from app import app as flask_app
    flask_app.config['TESTING'] = True

    with flask_app.test_client() as c:
        r = c.get('/api/dashboard-data')
        assert r.status_code == 200, f'/api/dashboard-data returned {r.status_code}'
        data = _json.loads(r.data)
        assert 'total' in data and 'branches' in data and 'cgpa_dist' in data

test('API /api/dashboard-data JSON', test_api)


# ── 11. Cleanup test user ────────────────────────────────────
def cleanup():
    from database.db import get_db, close_db
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM users WHERE username = %s", (_TEST_USER,))
    db.commit()
    cur.close()
    close_db(db)

test('Cleanup test data', cleanup)


# ── Summary ───────────────────────────────────────────────────
print()
print('=' * 60)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f'Results: {passed} passed, {failed} failed out of {len(results)} tests')
print('=' * 60)

if failed:
    print('\nFailed tests:')
    for name, ok, err in results:
        if not ok:
            print(f'  - {name}: {err}')
    sys.exit(1)
else:
    print('All tests passed! The migration is complete.')
    sys.exit(0)
