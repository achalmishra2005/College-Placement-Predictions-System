"""
app.py - Main Flask Application
College Placement Prediction System
"""

import csv
import io
import logging
import os
import sqlite3
from functools import wraps

from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError

from config import Config
from utils.helpers import (get_model_info, init_db, predict_placement,
                           rows_to_dicts, verify_password)
from utils.recommendations import generate_suggestions

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config["SECRET_KEY"]

csrf = CSRFProtect(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("placement")

DB_PATH = app.config["DB_PATH"]
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
init_db(DB_PATH)

# Numeric fields and their accepted ranges for validation.
NUMERIC_FIELDS = {
    "cgpa": (0, 10),
    "tenth_percentage": (0, 100),
    "twelfth_percentage": (0, 100),
    "aptitude_score": (0, 100),
    "coding_score": (0, 100),
    "communication_score": (0, 100),
    "internship": (0, 10),
    "projects": (0, 50),
    "backlogs": (0, 50),
}


# ─── DB helper ───────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Validation ──────────────────────────────
def validate_student_form(form):
    """Return (cleaned: dict, errors: list[str])."""
    errors = []
    cleaned = {}

    name = (form.get("name") or "").strip()
    roll_no = (form.get("roll_no") or "").strip()
    if not name:
        errors.append("Name is required.")
    if not roll_no:
        errors.append("Roll number is required.")
    cleaned["name"] = name
    cleaned["roll_no"] = roll_no
    cleaned["email"] = (form.get("email") or "").strip()
    cleaned["branch"] = (form.get("branch") or "").strip()

    for field, (lo, hi) in NUMERIC_FIELDS.items():
        raw = form.get(field)
        if raw is None or str(raw).strip() == "":
            errors.append(f"{field.replace('_', ' ').title()} is required.")
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{field.replace('_', ' ').title()} must be a number.")
            continue
        if not (lo <= val <= hi):
            errors.append(f"{field.replace('_', ' ').title()} must be between {lo} and {hi}.")
            continue
        cleaned[field] = val

    return cleaned, errors


# ─── Auth decorator ──────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─── Security headers ────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ─── PUBLIC ROUTES ───────────────────────────
@app.route('/')
def index():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    placed = db.execute("SELECT COUNT(*) FROM students WHERE prediction=1").fetchone()[0]
    not_placed = db.execute("SELECT COUNT(*) FROM students WHERE prediction=0").fetchone()[0]
    db.close()
    return render_template('index.html', total=total, placed=placed, not_placed=not_placed)


@app.route('/predict', methods=['GET', 'POST'])
def predict():
    result = None
    form_data = {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        cleaned, errors = validate_student_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('prediction.html', result=result, form_data=form_data)
        try:
            placed, prob = predict_placement(cleaned)
            result = {
                'placed': placed,
                'probability': prob,
                'status': 'Likely To Be Placed' if placed else 'Needs Improvement',
                'color': 'success' if placed else 'danger',
                'suggestions': generate_suggestions(cleaned),
            }
            _upsert_student(cleaned, placed, prob)
        except Exception as e:
            logger.exception("Prediction failed")
            flash(f'Prediction error: {str(e)}', 'danger')
    return render_template('prediction.html', result=result, form_data=form_data)


def _upsert_student(fd, placed, prob):
    db = get_db()
    try:
        db.execute('''
            INSERT INTO students
            (name,roll_no,email,branch,cgpa,tenth_percentage,twelfth_percentage,
             aptitude_score,coding_score,communication_score,internship,projects,backlogs,
             prediction,probability)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            fd.get('name', ''), fd.get('roll_no', ''), fd.get('email', ''), fd.get('branch', ''),
            fd['cgpa'], fd['tenth_percentage'], fd['twelfth_percentage'],
            fd['aptitude_score'], fd['coding_score'], fd['communication_score'],
            fd['internship'], fd['projects'], fd['backlogs'], placed, prob,
        ))
        db.commit()
    except sqlite3.IntegrityError:
        db.execute('''
            UPDATE students SET
              cgpa=?, tenth_percentage=?, twelfth_percentage=?,
              aptitude_score=?, coding_score=?, communication_score=?,
              internship=?, projects=?, backlogs=?,
              prediction=?, probability=?
            WHERE roll_no=?
        ''', (
            fd['cgpa'], fd['tenth_percentage'], fd['twelfth_percentage'],
            fd['aptitude_score'], fd['coding_score'], fd['communication_score'],
            fd['internship'], fd['projects'], fd['backlogs'], placed, prob,
            fd.get('roll_no', ''),
        ))
        db.commit()
    finally:
        db.close()


@app.route('/dashboard')
def dashboard():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    placed = db.execute("SELECT COUNT(*) FROM students WHERE prediction=1").fetchone()[0]
    not_placed = db.execute("SELECT COUNT(*) FROM students WHERE prediction=0").fetchone()[0]
    avg_cgpa = db.execute("SELECT ROUND(AVG(cgpa),2) FROM students").fetchone()[0] or 0
    max_cgpa = db.execute("SELECT MAX(cgpa) FROM students").fetchone()[0] or 0

    branches = db.execute('''
        SELECT branch,
               COUNT(*) as total,
               SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) as placed
        FROM students GROUP BY branch ORDER BY total DESC
    ''').fetchall()

    recent = db.execute(
        "SELECT * FROM students ORDER BY created_at DESC LIMIT 5"
    ).fetchall()

    cgpa_dist = db.execute('''
        SELECT
          CASE
            WHEN cgpa < 6 THEN "Below 6"
            WHEN cgpa < 7 THEN "6-7"
            WHEN cgpa < 8 THEN "7-8"
            WHEN cgpa < 9 THEN "8-9"
            ELSE "9+"
          END as range,
          COUNT(*) as cnt
        FROM students GROUP BY range ORDER BY range
    ''').fetchall()

    db.close()
    return render_template('dashboard.html',
        total=total, placed=placed, not_placed=not_placed,
        avg_cgpa=avg_cgpa, max_cgpa=max_cgpa,
        branches=rows_to_dicts(branches), recent=recent,
        cgpa_dist=rows_to_dicts(cgpa_dist)
    )


@app.route('/statistics')
def statistics():
    db = get_db()
    try:
        model_info = get_model_info()
    except FileNotFoundError:
        model_info = None
        flash('Model not trained yet. Run `python train_model.py`.', 'warning')
    branches = db.execute('''
        SELECT branch, COUNT(*) as total,
               SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) as placed,
               ROUND(AVG(cgpa),2) as avg_cgpa
        FROM students GROUP BY branch
    ''').fetchall()
    db.close()
    return render_template('statistics.html', model_info=model_info, branches=branches)


# ─── ADMIN AUTH ──────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin' in session:
        return redirect(url_for('students'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        db = get_db()
        admin = db.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        db.close()
        if admin and verify_password(admin['password'], password):
            session['admin'] = username
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('students'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


# ─── ADMIN STUDENT CRUD ───────────────────────
@app.route('/admin/students')
@login_required
def students():
    q = request.args.get('q', '')
    branch = request.args.get('branch', '')
    placed = request.args.get('placed', '')
    db = get_db()

    query = "SELECT * FROM students WHERE 1=1"
    params = []
    if q:
        query += " AND (name LIKE ? OR roll_no LIKE ? OR email LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%'])
    if branch:
        query += " AND branch=?"
        params.append(branch)
    if placed != '':
        try:
            params.append(int(placed))
            query += " AND prediction=?"
        except ValueError:
            pass
    query += " ORDER BY created_at DESC"

    student_list = db.execute(query, params).fetchall()
    branches = db.execute("SELECT DISTINCT branch FROM students ORDER BY branch").fetchall()
    db.close()
    return render_template('students.html',
        students=student_list, branches=branches,
        q=q, sel_branch=branch, sel_placed=placed
    )


@app.route('/admin/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        cleaned, errors = validate_student_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('add_student.html')
        try:
            placed, prob = predict_placement(cleaned)
            db = get_db()
            db.execute('''
                INSERT INTO students
                (name,roll_no,email,branch,cgpa,tenth_percentage,twelfth_percentage,
                 aptitude_score,coding_score,communication_score,internship,projects,backlogs,
                 prediction,probability)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (cleaned['name'], cleaned['roll_no'], cleaned['email'], cleaned['branch'],
                  cleaned['cgpa'], cleaned['tenth_percentage'], cleaned['twelfth_percentage'],
                  cleaned['aptitude_score'], cleaned['coding_score'], cleaned['communication_score'],
                  cleaned['internship'], cleaned['projects'], cleaned['backlogs'], placed, prob))
            db.commit()
            db.close()
            flash(f'Student {cleaned["name"]} added successfully!', 'success')
            return redirect(url_for('students'))
        except sqlite3.IntegrityError:
            flash('Roll number already exists.', 'danger')
        except Exception as e:
            logger.exception("Add student failed")
            flash(f'Error: {str(e)}', 'danger')
    return render_template('add_student.html')


@app.route('/admin/students/edit/<int:sid>', methods=['GET', 'POST'])
@login_required
def edit_student(sid):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if not student:
        db.close()
        flash('Student not found.', 'danger')
        return redirect(url_for('students'))

    if request.method == 'POST':
        cleaned, errors = validate_student_form(request.form)
        if errors:
            db.close()
            for e in errors:
                flash(e, 'danger')
            return render_template('edit_student.html', student=student)
        try:
            placed, prob = predict_placement(cleaned)
            db.execute('''
                UPDATE students SET
                  name=?, roll_no=?, email=?, branch=?,
                  cgpa=?, tenth_percentage=?, twelfth_percentage=?,
                  aptitude_score=?, coding_score=?, communication_score=?,
                  internship=?, projects=?, backlogs=?,
                  prediction=?, probability=?
                WHERE id=?
            ''', (cleaned['name'], cleaned['roll_no'], cleaned['email'], cleaned['branch'],
                  cleaned['cgpa'], cleaned['tenth_percentage'], cleaned['twelfth_percentage'],
                  cleaned['aptitude_score'], cleaned['coding_score'], cleaned['communication_score'],
                  cleaned['internship'], cleaned['projects'], cleaned['backlogs'], placed, prob, sid))
            db.commit()
            db.close()
            flash('Student updated successfully!', 'success')
            return redirect(url_for('students'))
        except sqlite3.IntegrityError:
            flash('Roll number already exists.', 'danger')
        except Exception as e:
            logger.exception("Edit student failed")
            flash(f'Error: {str(e)}', 'danger')
    db.close()
    return render_template('edit_student.html', student=student)


@app.route('/admin/students/delete/<int:sid>', methods=['POST'])
@login_required
def delete_student(sid):
    db = get_db()
    db.execute("DELETE FROM students WHERE id=?", (sid,))
    db.commit()
    db.close()
    flash('Student deleted.', 'info')
    return redirect(url_for('students'))


@app.route('/admin/export')
@login_required
def export_csv():
    db = get_db()
    rows = db.execute("SELECT * FROM students ORDER BY created_at DESC").fetchall()
    db.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Roll No', 'Email', 'Branch', 'CGPA',
                     '10th%', '12th%', 'Aptitude', 'Coding', 'Communication',
                     'Internship', 'Projects', 'Backlogs', 'Prediction', 'Probability', 'Created At'])
    for r in rows:
        pred = 'Placed' if r['prediction'] == 1 else ('Not Placed' if r['prediction'] == 0 else 'N/A')
        writer.writerow([
            r['id'], r['name'], r['roll_no'], r['email'], r['branch'],
            r['cgpa'], r['tenth_percentage'], r['twelfth_percentage'],
            r['aptitude_score'], r['coding_score'], r['communication_score'],
            r['internship'], r['projects'], r['backlogs'],
            pred, r['probability'], r['created_at']
        ])
    output.seek(0)
    return Response(output, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment;filename=students_export.csv'})


# ─── API ENDPOINTS ────────────────────────────
@app.route('/api/dashboard-data')
def api_dashboard_data():
    db = get_db()
    branches = db.execute('''
        SELECT branch, COUNT(*) as total,
               SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) as placed
        FROM students GROUP BY branch
    ''').fetchall()
    cgpa_dist = db.execute('''
        SELECT
          CASE WHEN cgpa<6 THEN "Below 6" WHEN cgpa<7 THEN "6-7"
               WHEN cgpa<8 THEN "7-8"    WHEN cgpa<9 THEN "8-9" ELSE "9+"
          END as rng, COUNT(*) as cnt
        FROM students GROUP BY rng ORDER BY rng
    ''').fetchall()
    total = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    placed = db.execute("SELECT COUNT(*) FROM students WHERE prediction=1").fetchone()[0]
    db.close()
    return jsonify({
        'branches': rows_to_dicts(branches),
        'cgpa_dist': rows_to_dicts(cgpa_dist),
        'total': total, 'placed': placed, 'not_placed': total - placed
    })


@app.route('/healthz')
def healthz():
    return jsonify({'status': 'ok'})


# ─── ERROR HANDLERS ──────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404,
                           message="Page not found."), 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Internal server error")
    return render_template('error.html', code=500,
                           message="Something went wrong on our end."), 500


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('Your session expired. Please try again.', 'warning')
    return redirect(request.referrer or url_for('index'))


if __name__ == '__main__':
    app.run(debug=app.config["DEBUG"], port=int(os.environ.get("PORT", 5000)))
