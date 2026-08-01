"""
app.py - Main Flask Application
College Placement Prediction System
"""

import csv
import io
import json
import os
from datetime import datetime, timedelta
from functools import wraps

import psycopg2
import psycopg2.errors
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, Response
)
from flask_wtf import CSRFProtect, FlaskForm
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename
from wtforms import StringField, PasswordField, BooleanField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length

from database.db import get_db, close_db, init_db
from utils.helpers import (
    create_user, get_model_info, get_user_by_email, get_user_by_id,
    get_user_by_username, generate_password_reset_token,
    hash_password, predict_placement, verify_password,
    verify_password_reset_token, extract_pdf_text, parse_resume,
    score_resume, skill_gap_analysis, recommend_careers,
    build_learning_roadmap, placement_readiness_score, PDF_SUPPORT
)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change_me_secure_2026')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.permanent_session_lifetime = timedelta(days=30)

csrf = CSRFProtect(app)

# ─── Upload folder ────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_local_upload_dir = os.path.join(BASE_DIR, 'static', 'uploads')

try:
    os.makedirs(_local_upload_dir, exist_ok=True)
    _test_file = os.path.join(_local_upload_dir, '.write_test')
    open(_test_file, 'w').close()
    os.remove(_test_file)
    UPLOAD_FOLDER = _local_upload_dir
except OSError:
    UPLOAD_FOLDER = '/tmp/uploads'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ─── Initialise PostgreSQL schema ─────────────────────────────
try:
    init_db()
    print("=" * 60)
    print("DATABASE: Supabase PostgreSQL (connected)")
    print("=" * 60)
except Exception as _init_err:
    print("=" * 60)
    print(f"DATABASE WARNING: {_init_err}")
    print("Set SUPABASE_DB_* env vars and restart.")
    print("=" * 60)

ALLOWED_RESUME_EXTENSIONS = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


# ─── WTFORMS CLASSES ─────────────────────────


class LoginForm(FlaskForm):
    identifier = StringField('Username or Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Login As', choices=[
        ('student', 'Student'),
        ('admin', 'Admin'),
        ('company', 'Company')
    ], default='student')
    remember_me = BooleanField('Remember Me')


class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    college = StringField('College')
    branch = StringField('Branch')
    year = SelectField('Year', choices=[('', 'Select Year'), ('1', '1st Year'), ('2', '2nd Year'), ('3', '3rd Year'), ('4', '4th Year')], default='')
    cgpa = StringField('CGPA')
    skills = StringField('Skills')
    phone = StringField('Phone')


class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])


class ProfileForm(FlaskForm):
    full_name = StringField('Full Name')
    college = StringField('College')
    branch = StringField('Branch')
    year = StringField('Year')
    cgpa = StringField('CGPA')
    skills = StringField('Skills')
    phone = StringField('Phone')
    profile_picture = FileField('Profile Picture', validators=[FileAllowed(ALLOWED_IMAGE_EXTENSIONS, 'Images only!')])
    resume = FileField('Resume', validators=[FileAllowed(ALLOWED_RESUME_EXTENSIONS, 'PDF only!')])


class CompanyProfileForm(FlaskForm):
    company_name = StringField('Company Name')
    company_address = TextAreaField('Company Address')
    company_website = StringField('Company Website')


class JobForm(FlaskForm):
    title = StringField('Job Title', validators=[DataRequired(), Length(min=3, max=120)])
    description = TextAreaField('Description', validators=[DataRequired()])
    requirements = TextAreaField('Requirements', validators=[DataRequired()])
    salary_min = StringField('Minimum Salary')
    salary_max = StringField('Maximum Salary')
    location = StringField('Location')
    job_type = SelectField('Job Type', choices=[
        ('full-time', 'Full Time'),
        ('internship', 'Internship'),
        ('contract', 'Contract'),
        ('part-time', 'Part Time'),
    ], default='full-time')


# ─── HELPER FUNCTIONS ────────────────────────


def login_required(role=None):
    """Decorator factory that restricts access to logged-in users with an optional role check."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('login'))
            if role and session.get('user_role') != role:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def resolve_redirect_by_role():
    """Return a redirect Response based on the current user's role stored in session."""
    user_role = session.get('user_role', 'student')
    if user_role == 'admin':
        return redirect(url_for('dashboard'))
    elif user_role == 'company':
        return redirect(url_for('company_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))


def _exec(conn, sql, params=()):
    """Execute a query and return the cursor (without closing it)."""
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


# ─── AUTH HELPERS ───────────────────────────

@app.route('/login', methods=['GET', 'POST'])
@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role=None):
    if 'user_id' in session:
        return resolve_redirect_by_role()

    form = LoginForm()

    # Pre-select role from URL parameter (e.g., /login/admin)
    if role and request.method == 'GET':
        form.role.data = role

    if form.validate_on_submit():

        identifier = form.identifier.data.strip()
        password = form.password.data

        db = get_db()

        # Search by username first
        user = get_user_by_username(db, identifier)

        # If not found, search by email
        if user is None:
            user = get_user_by_email(db, identifier)

        if user is None:
            close_db(db)
            flash("Invalid username/email or password.", "danger")
            return render_template("login.html", form=form)

        if not verify_password(password, user["password"]):
            close_db(db)
            flash("Invalid username/email or password.", "danger")
            return render_template("login.html", form=form)

        # Login Success — role comes from the database, not the dropdown
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["user_role"] = user["role"]
        session["full_name"] = user["full_name"] or user["username"]
        session.permanent = bool(form.remember_me.data)

        close_db(db)

        flash(f"Welcome {session['full_name']}!", "success")
        return resolve_redirect_by_role()

    return render_template("login.html", form=form)

# ─── PUBLIC ROUTES ───────────────────────────
@app.route('/')
def index():
    db = get_db()
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students')
    total = cur.fetchone()['cnt']
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students WHERE prediction=1')
    placed = cur.fetchone()['cnt']
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students WHERE prediction=0')
    not_placed = cur.fetchone()['cnt']
    close_db(db)
    return render_template('index.html', total=total, placed=placed, not_placed=not_placed)


@app.route('/predict', methods=['GET', 'POST'])
def predict():
    result = None
    form_data = {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            placed, prob = predict_placement(form_data)
            result = {
                'placed': placed,
                'probability': prob,
                'status': 'Likely To Be Placed' if placed else 'Needs Improvement',
                'color': 'success' if placed else 'danger'
            }
            db = get_db()
            try:
                _exec(db, '''
                    INSERT INTO students
                    (name, roll_no, email, branch, cgpa, tenth_percentage, twelfth_percentage,
                     aptitude_score, coding_score, communication_score, internship, projects, backlogs,
                     prediction, probability)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    form_data.get('name', ''), form_data.get('roll_no', ''),
                    form_data.get('email', ''), form_data.get('branch', ''),
                    float(form_data['cgpa']), float(form_data['tenth_percentage']),
                    float(form_data['twelfth_percentage']), int(form_data['aptitude_score']),
                    int(form_data['coding_score']), int(form_data['communication_score']),
                    int(form_data.get('internship', 0)), int(form_data.get('projects', 0)),
                    int(form_data.get('backlogs', 0)), placed, prob
                ))
                db.commit()
            except psycopg2.errors.UniqueViolation:
                db.rollback()
                _exec(db, '''
                    UPDATE students SET
                      name=%s, email=%s, branch=%s, cgpa=%s, tenth_percentage=%s, twelfth_percentage=%s,
                      aptitude_score=%s, coding_score=%s, communication_score=%s, internship=%s,
                      projects=%s, backlogs=%s, prediction=%s, probability=%s
                    WHERE roll_no=%s
                ''', (
                    form_data.get('name', ''), form_data.get('email', ''), form_data.get('branch', ''),
                    float(form_data['cgpa']), float(form_data['tenth_percentage']),
                    float(form_data['twelfth_percentage']), int(form_data['aptitude_score']),
                    int(form_data['coding_score']), int(form_data['communication_score']),
                    int(form_data.get('internship', 0)), int(form_data.get('projects', 0)),
                    int(form_data.get('backlogs', 0)), placed, prob,
                    form_data.get('roll_no', '')
                ))
                db.commit()
            close_db(db)
        except Exception as e:
            flash(f'Prediction error: {str(e)}', 'danger')
    return render_template('prediction.html', result=result, form_data=form_data)


@app.route('/statistics')
def statistics():
    db = get_db()
    model_info = get_model_info()
    cur = _exec(db, '''
        SELECT branch, COUNT(*) as total,
               SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) as placed,
               ROUND(AVG(cgpa)::numeric, 2) as avg_cgpa
        FROM students GROUP BY branch
    ''')
    branches = cur.fetchall()
    close_db(db)
    return render_template('statistics.html', model_info=model_info, branches=branches)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    reset_url = None
    if form.validate_on_submit():
        db = get_db()
        user = get_user_by_email(db, form.email.data)
        if user:
            token = generate_password_reset_token(user['username'])
            reset_url = url_for('reset_password', token=token, _external=True)
            flash('Password reset instructions have been generated.', 'info')
        else:
            flash('If that email exists, you will receive reset instructions shortly.', 'info')
        close_db(db)
    return render_template('forgot_password.html', form=form, reset_url=reset_url)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    username = verify_password_reset_token(token)
    if not username:
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        db = get_db()
        user = get_user_by_username(db, username)
        if user:
            if verify_password(form.password.data, user['password']):
                flash('New password cannot be the same as the old password.', 'warning')
            else:
                _exec(db, 'UPDATE users SET password=%s WHERE id=%s',
                      (hash_password(form.password.data), user['id']))
                db.commit()
                close_db(db)
                flash('Password has been reset. Please login.', 'success')
                return redirect(url_for('login'))
        else:
            flash('User not found.', 'danger')
        close_db(db)
    return render_template('reset_password.html', form=form)


@app.route('/student/profile', methods=['GET', 'POST'])
@login_required('student')
def student_profile():
    db = get_db()
    user = get_user_by_id(db, session['user_id'])
    form = ProfileForm()

    if request.method == 'GET' and user:
        form.full_name.data = user['full_name']
        form.college.data = user['college']
        form.branch.data = user['branch']
        form.year.data = user['year']
        form.cgpa.data = user['cgpa']
        form.skills.data = user['skills']
        form.phone.data = user['phone']

    if form.validate_on_submit():
        profile_picture = user['profile_picture'] if user else None
        resume_filename = user['resume_filename'] if user else None
        resume_uploaded_at = user['resume_uploaded_at'] if user else None

        picture = request.files.get('profile_picture')
        if picture and allowed_file(picture.filename, ALLOWED_IMAGE_EXTENSIONS):
            pic_name = secure_filename(f"{session['user_id']}_avatar_{picture.filename}")
            picture.save(os.path.join(app.config['UPLOAD_FOLDER'], pic_name))
            profile_picture = pic_name

        resume = request.files.get('resume')
        resume_text = user['resume_text'] if user else None
        resume_analysis = user['resume_analysis'] if user else None
        resume_score = user['resume_score'] if user else None
        readiness_score = user['readiness_score'] if user else None
        skill_gap = user['skill_gap'] if user else None
        career_recommendations = user['career_recommendations'] if user else None
        learning_roadmap = user['learning_roadmap'] if user else None

        new_resume_uploaded = bool(resume and resume.filename and allowed_file(resume.filename, ALLOWED_RESUME_EXTENSIONS))
        if new_resume_uploaded:
            resume_name = secure_filename(f"{session['user_id']}_resume_{resume.filename}")
            resume.save(os.path.join(app.config['UPLOAD_FOLDER'], resume_name))
            resume_filename = resume_name
            resume_uploaded_at = datetime.utcnow().isoformat()
            if PDF_SUPPORT:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
                resume_text = extract_pdf_text(file_path)
            else:
                resume_text = ''

        if resume_filename:
            if PDF_SUPPORT:
                if not new_resume_uploaded and not resume_text:
                    resume_text = user['resume_text'] or ''
                    if not resume_text:
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
                        if os.path.exists(file_path):
                            resume_text = extract_pdf_text(file_path)

                parsed = parse_resume(resume_text)
                resume_score, section_scores, suggestions = score_resume(parsed, resume_text)
                skill_gap_data = skill_gap_analysis(parsed, form.skills.data)

                updated_user = dict(user) if user else {}
                updated_user['cgpa'] = float(form.cgpa.data) if form.cgpa.data else (user['cgpa'] if user else 0.0)
                updated_user['skills'] = form.skills.data

                career_recommendations = json.dumps(recommend_careers(parsed, updated_user))
                learning_roadmap = json.dumps(build_learning_roadmap(skill_gap_data, json.loads(career_recommendations)))
                readiness_score, strengths, weaknesses, recs = placement_readiness_score(updated_user, resume_score, parsed, skill_gap_data)
                resume_analysis = json.dumps({
                    'parsed': parsed,
                    'section_scores': section_scores,
                    'suggestions': suggestions,
                    'strengths': strengths,
                    'weaknesses': weaknesses,
                    'recommendations': recs
                })
                skill_gap = json.dumps(skill_gap_data)
            else:
                resume_text = ''
                resume_analysis = json.dumps({'error': 'PDF parsing unavailable'})
                resume_score = 0
                readiness_score = 0
                skill_gap = json.dumps({})
                career_recommendations = json.dumps([])
                learning_roadmap = json.dumps([])

        _exec(db, '''
            UPDATE users SET
              full_name=%s, college=%s, branch=%s, year=%s, cgpa=%s, skills=%s, phone=%s,
              profile_picture=%s, resume_filename=%s, resume_uploaded_at=%s,
              resume_text=%s, resume_analysis=%s, resume_score=%s, readiness_score=%s,
              skill_gap=%s, career_recommendations=%s, learning_roadmap=%s
            WHERE id=%s
        ''', (
            form.full_name.data, form.college.data, form.branch.data,
            form.year.data, float(form.cgpa.data) if form.cgpa.data else None,
            form.skills.data, form.phone.data, profile_picture, resume_filename,
            resume_uploaded_at, resume_text, resume_analysis, resume_score,
            readiness_score, skill_gap, career_recommendations,
            learning_roadmap, session['user_id']
        ))
        db.commit()
        close_db(db)
        session['full_name'] = form.full_name.data or session.get('username')
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('student_profile'))

    close_db(db)
    return render_template('student_profile.html', user=user, form=form)


@app.route('/logout')
def logout():
    session_keys = ['user_id', 'username', 'user_role', 'full_name']
    for key in session_keys:
        session.pop(key, None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return resolve_redirect_by_role()
    form = RegisterForm()
    if form.validate_on_submit():
        db = get_db()
        if get_user_by_username(db, form.username.data):
            flash('Username already taken. Please choose another.', 'danger')
            close_db(db)
        elif get_user_by_email(db, form.email.data):
            flash('Email already registered.', 'danger')
            close_db(db)
        else:
            create_user(
                db,
                username=form.username.data.strip(),
                password=form.password.data,
                role='student',
                email=form.email.data,
                full_name=form.full_name.data,
                college=form.college.data,
                branch=form.branch.data,
                year=form.year.data,
                cgpa=float(form.cgpa.data) if form.cgpa.data else None,
                skills=form.skills.data,
                phone=form.phone.data
            )
            close_db(db)
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/company/register', methods=['GET', 'POST'])
def company_register():
    if 'user_id' in session:
        return resolve_redirect_by_role()
    form = RegisterForm()
    if form.validate_on_submit():
        db = get_db()
        if get_user_by_email(db, form.email.data):
            flash('Email already registered.', 'danger')
            close_db(db)
        else:
            create_user(
                db,
                username=form.email.data.strip(),
                password=form.password.data,
                role='company',
                email=form.email.data,
                full_name=form.full_name.data
            )
            close_db(db)
            flash('Company registration successful. Please login.', 'success')
            return redirect(url_for('login', role='company'))
    return render_template('register.html', form=form)


@app.route('/student/dashboard')
@login_required('student')
def student_dashboard():
    db = get_db()
    user = get_user_by_id(db, session['user_id'])

    student = None
    if user and user['email']:
        cur = _exec(db,
            'SELECT * FROM students WHERE email=%s ORDER BY created_at DESC LIMIT 1',
            (user['email'],))
        student = cur.fetchone()

    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students')
    total = cur.fetchone()['cnt']
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students WHERE prediction=1')
    placed = cur.fetchone()['cnt']
    not_placed = total - placed
    cur = _exec(db,
        'SELECT branch, COUNT(*) AS total, SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) AS placed FROM students GROUP BY branch')
    branch_stats = cur.fetchall()

    profile_fields = ['full_name', 'college', 'branch', 'year', 'cgpa', 'skills', 'phone']
    completion = round(sum(bool(user[f]) for f in profile_fields) / len(profile_fields) * 100) if user else 0
    resume_status = 'Uploaded' if user and user.get('resume_filename') else 'Pending'
    document_count = int(bool(user and user.get('profile_picture'))) + int(bool(user and user.get('resume_filename')))

    resume_analysis = {}
    if user and user.get('resume_analysis'):
        try:
            resume_analysis = json.loads(user['resume_analysis'])
        except Exception:
            resume_analysis = {}

    skill_gap = {}
    if user and user.get('skill_gap'):
        try:
            skill_gap = json.loads(user['skill_gap'])
        except Exception:
            skill_gap = {}

    career_recommendations = []
    if user and user.get('career_recommendations'):
        try:
            career_recommendations = json.loads(user['career_recommendations'])
        except Exception:
            career_recommendations = []

    learning_roadmap = []
    if user and user.get('learning_roadmap'):
        try:
            learning_roadmap = json.loads(user['learning_roadmap'])
        except Exception:
            learning_roadmap = []

    resume_score = user.get('resume_score') if (user and user.get('resume_score') is not None) else 0
    readiness_score = user.get('readiness_score') if (user and user.get('readiness_score') is not None) else 0

    close_db(db)

    return render_template('student_dashboard.html', user=user, student=student,
                           total=total, placed=placed, not_placed=not_placed,
                           branch_stats=branch_stats, completion=completion,
                           resume_status=resume_status, document_count=document_count,
                           resume_analysis=resume_analysis, skill_gap=skill_gap,
                           career_recommendations=career_recommendations,
                           learning_roadmap=learning_roadmap, resume_score=resume_score,
                           readiness_score=readiness_score)


@app.route('/student/files')
@login_required('student')
def student_files():
    db = get_db()
    user = get_user_by_id(db, session['user_id'])
    close_db(db)
    if not user:
        flash('User profile not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    return render_template('student_files.html', user=user)


@app.route('/student/ai-analysis')
@login_required('student')
def ai_analysis():
    db = get_db()
    user = get_user_by_id(db, session['user_id'])
    close_db(db)
    if not user:
        flash('User profile not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    # Load and parse AI fields
    resume_analysis = {}
    if user.get('resume_analysis'):
        try:
            resume_analysis = json.loads(user['resume_analysis'])
        except Exception:
            resume_analysis = {}

    skill_gap = {}
    if user.get('skill_gap'):
        try:
            skill_gap = json.loads(user['skill_gap'])
        except Exception:
            skill_gap = {}

    career_recommendations = []
    if user.get('career_recommendations'):
        try:
            career_recommendations = json.loads(user['career_recommendations'])
        except Exception:
            career_recommendations = []

    learning_roadmap = []
    if user.get('learning_roadmap'):
        try:
            learning_roadmap = json.loads(user['learning_roadmap'])
        except Exception:
            learning_roadmap = []

    resume_score = user.get('resume_score') if (user and user.get('resume_score') is not None) else 0
    readiness_score = user.get('readiness_score') if (user and user.get('readiness_score') is not None) else 0

    return render_template('ai_analysis.html', user=user,
                           resume_analysis=resume_analysis, skill_gap=skill_gap,
                           career_recommendations=career_recommendations,
                           learning_roadmap=learning_roadmap, resume_score=resume_score,
                           readiness_score=readiness_score)


@app.route('/student/re-analyze-resume', methods=['POST'])
@login_required('student')
def re_analyze_resume():
    db = get_db()
    user = get_user_by_id(db, session['user_id'])

    if not user:
        close_db(db)
        flash('User profile not found.', 'danger')
        return redirect(url_for('student_dashboard'))

    resume_filename = user.get('resume_filename')
    if not resume_filename:
        close_db(db)
        flash('No resume uploaded yet. Please upload your resume first.', 'warning')
        return redirect(url_for('student_profile'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
    if not os.path.exists(file_path):
        close_db(db)
        flash('Resume file not found on disk. Please upload again.', 'danger')
        return redirect(url_for('student_profile'))

    try:
        if PDF_SUPPORT:
            resume_text = extract_pdf_text(file_path)
            parsed = parse_resume(resume_text)
            resume_score, section_scores, suggestions = score_resume(parsed, resume_text)
            skill_gap_data = skill_gap_analysis(parsed, user.get('skills', ''))

            career_recommendations = json.dumps(recommend_careers(parsed, user))
            learning_roadmap = json.dumps(build_learning_roadmap(skill_gap_data, json.loads(career_recommendations)))
            readiness_score, strengths, weaknesses, recs = placement_readiness_score(user, resume_score, parsed, skill_gap_data)
            resume_analysis = json.dumps({
                'parsed': parsed,
                'section_scores': section_scores,
                'suggestions': suggestions,
                'strengths': strengths,
                'weaknesses': weaknesses,
                'recommendations': recs
            })
            skill_gap = json.dumps(skill_gap_data)

            _exec(db, '''
                UPDATE users SET
                  resume_text=%s, resume_analysis=%s, resume_score=%s, readiness_score=%s,
                  skill_gap=%s, career_recommendations=%s, learning_roadmap=%s
                WHERE id=%s
            ''', (
                resume_text, resume_analysis, resume_score, readiness_score,
                skill_gap, career_recommendations, learning_roadmap, session['user_id']
            ))
            db.commit()
            flash('Resume re-analyzed successfully using AI.', 'success')
        else:
            flash('PDF parsing is currently disabled or unavailable.', 'danger')
    except Exception as e:
        db.rollback()
        flash(f'An error occurred during resume analysis: {str(e)}', 'danger')
    finally:
        close_db(db)

    return redirect(url_for('ai_analysis'))


@app.route('/company/profile', methods=['GET', 'POST'])
@login_required('company')
def company_profile():
    db = get_db()
    user = get_user_by_id(db, session['user_id'])
    form = CompanyProfileForm()

    if request.method == 'GET' and user:
        form.company_name.data = user.get('company_name')
        form.company_address.data = user.get('company_address')
        form.company_website.data = user.get('company_website')

    if form.validate_on_submit():
        _exec(db, '''
            UPDATE users
            SET company_name=%s, company_address=%s, company_website=%s
            WHERE id=%s
        ''', (
            form.company_name.data.strip() if form.company_name.data else None,
            form.company_address.data.strip() if form.company_address.data else None,
            form.company_website.data.strip() if form.company_website.data else None,
            session['user_id']
        ))
        db.commit()
        close_db(db)
        session['full_name'] = form.company_name.data or session.get('username')
        flash('Company profile updated successfully.', 'success')
        return redirect(url_for('company_profile'))

    close_db(db)
    return render_template('company_profile.html', user=user, form=form)


@app.route('/company/jobs')
@login_required('company')
def company_jobs():
    db = get_db()
    q = request.args.get('q', '')
    job_type = request.args.get('job_type', '')
    location = request.args.get('location', '')

    query = '''
        SELECT j.*, u.company_name, u.company_website
        FROM jobs j
        JOIN users u ON u.id = j.company_id
        WHERE j.company_id=%s
    '''
    params = [session['user_id']]

    if q:
        query += ' AND (LOWER(j.title) LIKE LOWER(%s) OR LOWER(j.description) LIKE LOWER(%s))'
        params.extend([f'%{q}%', f'%{q}%'])
    if job_type:
        query += ' AND j.job_type=%s'
        params.append(job_type)
    if location:
        query += ' AND LOWER(j.location) LIKE LOWER(%s)'
        params.append(f'%{location}%')

    query += ' ORDER BY j.posted_at DESC'
    cur = _exec(db, query, params)
    jobs = cur.fetchall()
    close_db(db)
    return render_template('company_jobs.html', jobs=jobs, q=q, job_type=job_type, location=location)


@app.route('/company/jobs/new', methods=['GET', 'POST'])
@login_required('company')
def create_job():
    form = JobForm()
    if form.validate_on_submit():
        db = get_db()
        salary_min = float(form.salary_min.data) if form.salary_min.data else None
        salary_max = float(form.salary_max.data) if form.salary_max.data else None
        _exec(db, '''
            INSERT INTO jobs (company_id, title, description, requirements, salary_min, salary_max, location, job_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            session['user_id'],
            form.title.data.strip(),
            form.description.data.strip(),
            form.requirements.data.strip(),
            salary_min,
            salary_max,
            form.location.data.strip() if form.location.data else None,
            form.job_type.data,
        ))
        db.commit()
        close_db(db)
        flash('Job created successfully.', 'success')
        return redirect(url_for('company_jobs'))
    return render_template('job_form.html', form=form, title='Create Job', action='create')


@app.route('/company/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required('company')
def edit_job(job_id):
    db = get_db()
    cur = _exec(db, 'SELECT * FROM jobs WHERE id=%s AND company_id=%s', (job_id, session['user_id']))
    job = cur.fetchone()
    if not job:
        close_db(db)
        flash('Job not found.', 'danger')
        return redirect(url_for('company_jobs'))

    form = JobForm()
    if request.method == 'GET':
        form.title.data = job['title']
        form.description.data = job['description']
        form.requirements.data = job['requirements']
        form.salary_min.data = job['salary_min']
        form.salary_max.data = job['salary_max']
        form.location.data = job['location']
        form.job_type.data = job['job_type']

    if form.validate_on_submit():
        salary_min = float(form.salary_min.data) if form.salary_min.data else None
        salary_max = float(form.salary_max.data) if form.salary_max.data else None
        _exec(db, '''
            UPDATE jobs
            SET title=%s, description=%s, requirements=%s, salary_min=%s, salary_max=%s, location=%s, job_type=%s
            WHERE id=%s AND company_id=%s
        ''', (
            form.title.data.strip(),
            form.description.data.strip(),
            form.requirements.data.strip(),
            salary_min,
            salary_max,
            form.location.data.strip() if form.location.data else None,
            form.job_type.data,
            job_id,
            session['user_id']
        ))
        db.commit()
        close_db(db)
        flash('Job updated successfully.', 'success')
        return redirect(url_for('company_jobs'))

    close_db(db)
    return render_template('job_form.html', form=form, title='Edit Job', action='edit')


@app.route('/company/jobs/<int:job_id>/delete', methods=['POST'])
@login_required('company')
def delete_job(job_id):
    db = get_db()
    _exec(db, 'DELETE FROM jobs WHERE id=%s AND company_id=%s', (job_id, session['user_id']))
    db.commit()
    close_db(db)
    flash('Job deleted successfully.', 'info')
    return redirect(url_for('company_jobs'))


@app.route('/jobs')
def jobs():
    db = get_db()
    q = request.args.get('q', '')
    location = request.args.get('location', '')
    job_type = request.args.get('job_type', '')

    query = '''
        SELECT j.*, u.company_name, u.company_website
        FROM jobs j
        JOIN users u ON u.id = j.company_id
        WHERE 1=1
    '''
    params = []

    if q:
        query += ' AND (LOWER(j.title) LIKE LOWER(%s) OR LOWER(j.description) LIKE LOWER(%s))'
        params.extend([f'%{q}%', f'%{q}%'])
    if location:
        query += ' AND LOWER(j.location) LIKE LOWER(%s)'
        params.append(f'%{location}%')
    if job_type:
        query += ' AND j.job_type=%s'
        params.append(job_type)

    query += ' ORDER BY j.posted_at DESC'
    cur = _exec(db, query, params)
    jobs = cur.fetchall()
    close_db(db)
    return render_template('jobs.html', jobs=jobs, q=q, location=location, job_type=job_type)


@app.route('/jobs/<int:job_id>')
def job_details(job_id):
    db = get_db()
    cur = _exec(db, '''
        SELECT j.*, u.company_name, u.company_website, u.company_address
        FROM jobs j
        JOIN users u ON u.id = j.company_id
        WHERE j.id=%s
    ''', (job_id,))
    job = cur.fetchone()
    applied = False
    if job and session.get('user_role') == 'student':
        cur = _exec(db, 'SELECT id FROM applications WHERE student_id=%s AND job_id=%s', (session['user_id'], job_id))
        applied = cur.fetchone() is not None
    close_db(db)

    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('jobs'))

    return render_template('job_details.html', job=job, applied=applied)


@app.route('/jobs/<int:job_id>/apply', methods=['POST'])
@login_required('student')
def apply_job(job_id):
    db = get_db()
    user = get_user_by_id(db, session['user_id'])

    if not user or not user.get('resume_filename'):
        close_db(db)
        flash('Upload your resume before applying to jobs.', 'warning')
        return redirect(url_for('student_profile'))

    cur = _exec(db, 'SELECT * FROM jobs WHERE id=%s', (job_id,))
    job = cur.fetchone()
    if not job:
        close_db(db)
        flash('Job not found.', 'danger')
        return redirect(url_for('jobs'))

    cur = _exec(db, 'SELECT id FROM applications WHERE student_id=%s AND job_id=%s', (session['user_id'], job_id))
    exists = cur.fetchone()
    if exists:
        close_db(db)
        flash('You have already applied to this job.', 'warning')
        return redirect(url_for('job_details', job_id=job_id))

    _exec(db, '''
        INSERT INTO applications (student_id, job_id, company_id, status)
        VALUES (%s, %s, %s, %s)
    ''', (session['user_id'], job_id, job['company_id'], 'applied'))
    db.commit()
    close_db(db)
    flash('Application submitted successfully.', 'success')
    return redirect(url_for('job_details', job_id=job_id))


@app.route('/company/applications')
@login_required('company')
def company_applications():
    db = get_db()
    cur = _exec(db, '''
        SELECT a.id, a.status, a.applied_at,
               j.title, j.location, j.job_type,
               s.full_name AS student_name, s.email AS student_email, s.resume_filename
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN users s ON s.id = a.student_id
        WHERE a.company_id=%s
        ORDER BY a.applied_at DESC
    ''', (session['user_id'],))
    applications = cur.fetchall()
    close_db(db)
    return render_template('company_applications.html', applications=applications)


@app.route('/company/applications/<int:application_id>/status', methods=['POST'])
@login_required('company')
def update_application_status(application_id):
    new_status = request.form.get('status', '').strip().lower()
    allowed_statuses = {'applied', 'shortlisted', 'interview', 'selected', 'rejected'}
    if new_status not in allowed_statuses:
        flash('Invalid application status.', 'danger')
        return redirect(url_for('company_applications'))

    db = get_db()
    _exec(db, '''
        UPDATE applications
        SET status=%s
        WHERE id=%s AND company_id=%s
    ''', (new_status, application_id, session['user_id']))
    db.commit()
    close_db(db)
    flash('Application status updated successfully.', 'success')
    return redirect(url_for('company_applications'))


@app.route('/admin/applications')
@login_required('admin')
def admin_applications():
    db = get_db()
    cur = _exec(db, '''
        SELECT a.id, a.status, a.applied_at,
               j.title, j.location,
               s.full_name AS student_name, s.email AS student_email,
               c.company_name
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN users s ON s.id = a.student_id
        JOIN users c ON c.id = a.company_id
        ORDER BY a.applied_at DESC
    ''')
    applications = cur.fetchall()
    close_db(db)
    return render_template('admin_applications.html', applications=applications)


@app.route('/company/dashboard')
@login_required('company')
def company_dashboard():
    db = get_db()
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students')
    total = cur.fetchone()['cnt']
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students WHERE prediction=1')
    placed = cur.fetchone()['cnt']
    cur = _exec(db, '''
        SELECT branch, COUNT(*) AS total,
               SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) AS placed
        FROM students GROUP BY branch ORDER BY placed DESC LIMIT 5
    ''')
    top_branches = cur.fetchall()
    cur = _exec(db,
        'SELECT name, branch, prediction, probability, created_at FROM students ORDER BY created_at DESC LIMIT 5')
    recent = cur.fetchall()

    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM jobs WHERE company_id=%s', (session['user_id'],))
    jobs_total = cur.fetchone()['cnt']
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM applications WHERE company_id=%s', (session['user_id'],))
    app_total = cur.fetchone()['cnt']
    cur = _exec(db, '''
        SELECT a.id, a.status, a.applied_at, j.title, s.full_name AS student_name
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN users s ON s.id = a.student_id
        WHERE a.company_id=%s
        ORDER BY a.applied_at DESC LIMIT 5
    ''', (session['user_id'],))
    recent_applications = cur.fetchall()
    close_db(db)
    return render_template('company_dashboard.html', total=total, placed=placed,
                           top_branches=top_branches, recent=recent,
                           jobs_total=jobs_total, app_total=app_total,
                           recent_applications=recent_applications)


@app.route('/dashboard', endpoint='dashboard')
@login_required('admin')
def admin_dashboard():
    db = get_db()
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students')
    total = cur.fetchone()['cnt']
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students WHERE prediction=1')
    placed = cur.fetchone()['cnt']
    not_placed = total - placed
    cur = _exec(db, 'SELECT ROUND(AVG(cgpa)::numeric, 2) AS avg FROM students')
    avg_cgpa = cur.fetchone()['avg'] or 0
    cur = _exec(db, '''
        SELECT branch, COUNT(*) as total,
               SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) as placed
        FROM students GROUP BY branch ORDER BY total DESC
    ''')
    branches = cur.fetchall()
    cur = _exec(db, 'SELECT * FROM students ORDER BY created_at DESC LIMIT 5')
    recent = cur.fetchall()
    cur = _exec(db, '''
        SELECT
          CASE
            WHEN cgpa < 6 THEN \'Below 6\'
            WHEN cgpa < 7 THEN \'6-7\'
            WHEN cgpa < 8 THEN \'7-8\'
            WHEN cgpa < 9 THEN \'8-9\'
            ELSE \'9+\'
          END as range,
          COUNT(*) as cnt
        FROM students GROUP BY range ORDER BY range
    ''')
    cgpa_dist = cur.fetchall()
    close_db(db)
    return render_template('dashboard.html',
                           total=total, placed=placed, not_placed=not_placed,
                           avg_cgpa=avg_cgpa, branches=branches,
                           recent=recent, cgpa_dist=cgpa_dist)


@app.route('/admin/students')
@login_required('admin')
def students():
    q = request.args.get('q', '')
    branch = request.args.get('branch', '')
    placed = request.args.get('placed', '')
    db = get_db()
    query = 'SELECT * FROM students WHERE 1=1'
    params = []
    if q:
        query += ' AND (name ILIKE %s OR roll_no ILIKE %s OR email ILIKE %s)'
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%'])
    if branch:
        query += ' AND branch=%s'
        params.append(branch)
    if placed != '':
        query += ' AND prediction=%s'
        params.append(int(placed))
    query += ' ORDER BY created_at DESC'
    cur = _exec(db, query, params)
    student_list = cur.fetchall()
    cur = _exec(db, 'SELECT DISTINCT branch FROM students ORDER BY branch')
    branches = cur.fetchall()
    close_db(db)
    return render_template('students.html',
                           students=student_list, branches=branches,
                           q=q, sel_branch=branch, sel_placed=placed)


@app.route('/admin/students/add', methods=['GET', 'POST'])
@login_required('admin')
def add_student():
    if request.method == 'POST':
        fd = request.form
        try:
            placed, prob = predict_placement(fd)
            db = get_db()
            _exec(db, '''
                INSERT INTO students
                (name, roll_no, email, branch, cgpa, tenth_percentage, twelfth_percentage,
                 aptitude_score, coding_score, communication_score, internship, projects, backlogs,
                 prediction, probability)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (fd['name'], fd['roll_no'], fd['email'], fd['branch'],
                  float(fd['cgpa']), float(fd['tenth_percentage']), float(fd['twelfth_percentage']),
                  int(fd['aptitude_score']), int(fd['coding_score']), int(fd['communication_score']),
                  int(fd.get('internship', 0)), int(fd.get('projects', 0)), int(fd.get('backlogs', 0)),
                  placed, prob))
            db.commit()
            close_db(db)
            flash(f'Student {fd["name"]} added successfully!', 'success')
            return redirect(url_for('students'))
        except psycopg2.errors.UniqueViolation:
            db.rollback()
            close_db(db)
            flash('Roll number already exists.', 'danger')
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    return render_template('add_student.html')


@app.route('/admin/students/edit/<int:sid>', methods=['GET', 'POST'])
@login_required('admin')
def edit_student(sid):
    db = get_db()
    cur = _exec(db, 'SELECT * FROM students WHERE id=%s', (sid,))
    student = cur.fetchone()
    if not student:
        close_db(db)
        flash('Student not found.', 'danger')
        return redirect(url_for('students'))
    if request.method == 'POST':
        fd = request.form
        try:
            placed, prob = predict_placement(fd)
            _exec(db, '''
                UPDATE students SET
                  name=%s, roll_no=%s, email=%s, branch=%s,
                  cgpa=%s, tenth_percentage=%s, twelfth_percentage=%s,
                  aptitude_score=%s, coding_score=%s, communication_score=%s,
                  internship=%s, projects=%s, backlogs=%s,
                  prediction=%s, probability=%s
                WHERE id=%s
            ''', (fd['name'], fd['roll_no'], fd['email'], fd['branch'],
                  float(fd['cgpa']), float(fd['tenth_percentage']), float(fd['twelfth_percentage']),
                  int(fd['aptitude_score']), int(fd['coding_score']), int(fd['communication_score']),
                  int(fd.get('internship', 0)), int(fd.get('projects', 0)), int(fd.get('backlogs', 0)),
                  placed, prob, sid))
            db.commit()
            close_db(db)
            flash('Student updated successfully!', 'success')
            return redirect(url_for('students'))
        except Exception as e:
            db.rollback()
            flash(f'Error: {str(e)}', 'danger')
    close_db(db)
    return render_template('edit_student.html', student=student)


@app.route('/admin/students/delete/<int:sid>', methods=['POST'])
@login_required('admin')
def delete_student(sid):
    db = get_db()
    _exec(db, 'DELETE FROM students WHERE id=%s', (sid,))
    db.commit()
    close_db(db)
    flash('Student deleted.', 'info')
    return redirect(url_for('students'))


@app.route('/admin/export')
@login_required('admin')
def export_csv():
    db = get_db()
    cur = _exec(db, 'SELECT * FROM students ORDER BY created_at DESC')
    rows = cur.fetchall()
    close_db(db)
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


@app.route('/api/dashboard-data')
def api_dashboard_data():
    db = get_db()
    cur = _exec(db, '''
        SELECT branch, COUNT(*) as total,
               SUM(CASE WHEN prediction=1 THEN 1 ELSE 0 END) as placed
        FROM students GROUP BY branch
    ''')
    branches = cur.fetchall()
    cur = _exec(db, '''
        SELECT
          CASE WHEN cgpa<6 THEN \'Below 6\' WHEN cgpa<7 THEN \'6-7\'
               WHEN cgpa<8 THEN \'7-8\' WHEN cgpa<9 THEN \'8-9\' ELSE \'9+\'
          END as rng, COUNT(*) as cnt
        FROM students GROUP BY rng ORDER BY rng
    ''')
    cgpa_dist = cur.fetchall()
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students')
    total = cur.fetchone()['cnt']
    cur = _exec(db, 'SELECT COUNT(*) AS cnt FROM students WHERE prediction=1')
    placed = cur.fetchone()['cnt']
    close_db(db)
    return jsonify({
        'branches': [dict(r) for r in branches],
        'cgpa_dist': [dict(r) for r in cgpa_dist],
        'total': total,
        'placed': placed,
        'not_placed': total - placed
    })


if __name__ == "__main__":
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)), debug=debug_mode)