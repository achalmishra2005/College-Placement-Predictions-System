"""
utils/helpers.py - Helper utilities
College Placement Prediction System
"""

import os
import pickle
import re
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from PyPDF2 import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PdfReader = None
    PDF_SUPPORT = False

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Model may be bundled in the project root, or copied to /tmp by a cold-start hook.
MODEL_PATH = os.environ.get('MODEL_PATH', os.path.join(ROOT_DIR, 'model.pkl'))
if not os.path.exists(MODEL_PATH):
    # Fallback: check /tmp (Vercel serverless writable area)
    _tmp_model = '/tmp/model.pkl'
    if os.path.exists(_tmp_model):
        MODEL_PATH = _tmp_model
SECRET_KEY = os.environ.get('SECRET_KEY', 'change_me_secure_2026')
SECURITY_SALT = os.environ.get('SECURITY_SALT', 'placement_salt_2026')
FEATURE_COLS = [
    'cgpa', 'tenth_percentage', 'twelfth_percentage',
    'aptitude_score', 'coding_score', 'communication_score',
    'internship', 'projects', 'backlogs',
    'academic_avg', 'skill_avg', 'experience_score'
]

PROGRAMMING_LANGUAGES = [
    'Python', 'Java', 'C++', 'C#', 'JavaScript', 'TypeScript', 'Ruby',
    'Go', 'Rust', 'Kotlin', 'Swift', 'SQL', 'R', 'MATLAB'
]
FRAMEWORKS = [
    'Django', 'Flask', 'React', 'Angular', 'Vue', 'Node.js', 'Express',
    'Spring', 'TensorFlow', 'PyTorch', 'Scikit-learn', 'FastAPI', 'Laravel'
]
DATABASES = ['MySQL', 'PostgreSQL', 'MongoDB', 'SQLite', 'Redis', 'Oracle', 'SQL Server']
CLOUD_PLATFORMS = ['AWS', 'Azure', 'GCP', 'Google Cloud', 'Heroku', 'Docker', 'Kubernetes']
CERTIFICATIONS = ['AWS Certified', 'Azure', 'Google Cloud', 'PMP', 'Cisco', 'CCNA', 'Scrum', 'Data Science', 'Machine Learning']
EDUCATION_TERMS = ['Bachelor', 'Master', 'B.Sc', 'M.Sc', 'B.Tech', 'M.Tech', 'PhD', 'High School', 'HSC', 'Diploma']
INDUSTRY_SKILLS = [
    'python', 'sql', 'machine learning', 'data analysis', 'data visualization',
    'deep learning', 'tensorflow', 'pytorch', 'pandas', 'numpy', 'scikit-learn',
    'aws', 'azure', 'docker', 'kubernetes', 'django', 'flask', 'react', 'node.js',
    'git', 'linux', 'api', 'rest'
]

PASSWORD_RESET_TIMEOUT = 7200


def find_terms(text: str, terms: list) -> list:
    found = []
    for term in terms:
        pattern = r'\b' + re.escape(term.lower()) + r'\b'
        if re.search(pattern, text.lower()):
            found.append(term)
    return sorted(set(found), key=str.lower)


def extract_pdf_text(file_path: str) -> str:
    try:
        reader = PdfReader(file_path)
        text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        return '\n'.join(text).strip()
    except Exception:
        return ''


def parse_resume(raw_text: str) -> dict:
    text = raw_text or ''
    normalized = text.lower()
    technical_skills = sorted(set(
        find_terms(normalized, PROGRAMMING_LANGUAGES) +
        find_terms(normalized, FRAMEWORKS) +
        find_terms(normalized, DATABASES) +
        find_terms(normalized, CLOUD_PLATFORMS)
    ), key=str.lower)

    certifications = sorted(set(find_terms(normalized, CERTIFICATIONS)), key=str.lower)
    education = sorted(set(find_terms(normalized, EDUCATION_TERMS)), key=str.lower)
    projects = []
    for line in text.splitlines():
        lower_line = line.strip().lower()
        if any(keyword in lower_line for keyword in ['project', 'developed', 'built', 'designed', 'implemented']):
            cleaned = line.strip()
            if cleaned and cleaned not in projects:
                projects.append(cleaned)
    if not projects and 'project' in normalized:
        projects.append('Project details detected in resume content.')

    experience = []
    if any(keyword in normalized for keyword in ['experience', 'internship', 'worked at', 'months', 'years']):
        experience.append('Professional experience details are present.')

    resume_sections = {
        'technical_skills': technical_skills,
        'programming_languages': find_terms(normalized, PROGRAMMING_LANGUAGES),
        'frameworks': find_terms(normalized, FRAMEWORKS),
        'databases': find_terms(normalized, DATABASES),
        'cloud_technologies': find_terms(normalized, CLOUD_PLATFORMS),
        'certifications': certifications,
        'projects': projects,
        'experience': experience,
        'education': education,
        'raw_text': raw_text
    }
    resume_sections['section_count'] = sum(bool(value) for key, value in resume_sections.items() if key != 'raw_text')
    return resume_sections


def score_resume(parsed: dict, raw_text: str) -> tuple:
    skills = parsed.get('technical_skills', [])
    projects = parsed.get('projects', [])
    certifications = parsed.get('certifications', [])
    education = parsed.get('education', [])

    skill_score = min(30, 10 + 4 * len(skills))
    project_score = min(20, 8 * len(projects))
    cert_score = min(15, 7 * len(certifications))
    education_score = 15 if education else 5
    completeness_score = min(15, parsed.get('section_count', 0) * 3 + min(10, len(raw_text) // 600))
    formatting_score = 10 if any(symbol in raw_text for symbol in ['•', '-', '•', '·', '*']) else 6

    total_score = min(100, round(skill_score + project_score + cert_score + education_score + completeness_score + formatting_score))
    section_scores = {
        'skills': int(skill_score),
        'projects': int(project_score),
        'certifications': int(cert_score),
        'education': int(education_score),
        'completeness': int(completeness_score),
        'formatting': int(formatting_score)
    }
    suggestions = []
    if len(skills) < 3:
        suggestions.append('Add more technical skills and keywords to showcase your strengths.')
    if not projects:
        suggestions.append('Include concrete project descriptions with technologies and outcomes.')
    if not certifications:
        suggestions.append('Add certifications or training credits to increase credibility.')
    if not education:
        suggestions.append('Mention your academic qualification clearly in the resume.')
    if parsed.get('section_count', 0) < 5:
        suggestions.append('Use well-defined sections like Summary, Skills, Projects, Education, and Experience.')
    return total_score, section_scores, suggestions


def skill_gap_analysis(parsed: dict, user_skills: str = '') -> dict:
    resume_skills = [skill.lower() for skill in parsed.get('technical_skills', [])]
    profile_skills = []
    if user_skills:
        profile_skills = [skill.strip().lower() for skill in re.split(r'[;,\n]+', user_skills) if skill.strip()]
    existing = sorted(set(resume_skills + profile_skills))
    mastered = [skill for skill in INDUSTRY_SKILLS if skill in existing]
    missing = [skill for skill in INDUSTRY_SKILLS if skill not in existing]
    recommendations = []
    for focus in ['python', 'sql', 'data analysis', 'machine learning', 'tensorflow', 'aws', 'docker']:
        if focus in missing:
            recommendations.append(focus)
    if not recommendations and missing:
        recommendations = missing[:5]
    learning_order = []
    for skill in ['python', 'sql', 'data analysis', 'machine learning', 'tensorflow', 'aws', 'docker', 'kubernetes']:
        if skill in missing:
            learning_order.append(skill)
    if not learning_order and missing:
        learning_order = missing[:5]
    return {
        'existing_skills': existing,
        'mastered_skills': mastered,
        'missing_skills': missing,
        'recommended_skills': recommendations,
        'learning_order': learning_order
    }


def recommend_careers(parsed: dict, user_data: Optional[dict] = None) -> list:
    skills = [skill.lower() for skill in parsed.get('technical_skills', [])]
    career_paths = []
    if 'python' in skills and any(item in skills for item in ['pandas', 'numpy', 'scikit-learn', 'machine learning']):
        career_paths.append('Data Scientist')
    if 'python' in skills and any(item in skills for item in ['tensorflow', 'pytorch']):
        career_paths.append('Machine Learning Engineer')
    if 'python' in skills and any(item in skills for item in ['flask', 'django', 'node.js', 'react', 'angular']):
        career_paths.append('Full Stack Developer')
    if 'sql' in skills and any(item in skills for item in ['data analysis', 'tableau', 'power bi']):
        career_paths.append('Data Analyst')
    if 'aws' in skills or 'azure' in skills or 'gcp' in skills:
        career_paths.append('AI Engineer')
    if 'django' in skills or 'flask' in skills:
        career_paths.append('Backend Developer')
    if 'python' in skills and not career_paths:
        career_paths.append('Python Developer')
    return sorted(dict.fromkeys(career_paths))[:3]


def build_learning_roadmap(skill_gap: dict, recommendations: list) -> list:
    missing = skill_gap.get('learning_order', [])
    roadmap = []
    weeks = [
        ('Week 1-2', ['Python fundamentals', 'Version control with Git']),
        ('Week 3-4', ['SQL and database design', 'Basic data analysis']),
        ('Week 5-6', ['Web development or machine learning basics']),
        ('Week 7-8', ['Frameworks and cloud fundamentals']),
        ('Week 9-10', ['Project building and portfolio work']),
        ('Week 11-12', ['Interview preparation and resume polishing'])
    ]
    for week, topics in weeks:
        selected = []
        for topic in topics:
            if any(keyword in topic.lower() for keyword in missing) or len(selected) < 1:
                selected.append(topic)
        roadmap.append({'week': week, 'topics': selected})
    if recommendations:
        roadmap.append({'week': 'Career Focus', 'topics': [f'{path} preparation' for path in recommendations]})
    return roadmap


def placement_readiness_score(user: dict, resume_score: int, parsed: dict, skill_gap: dict) -> tuple:
    cgpa = user.get('cgpa') or 0
    existing_skills = skill_gap.get('existing_skills', [])
    projects = parsed.get('projects', [])
    certifications = parsed.get('certifications', [])

    cgpa_component = min(20, (float(cgpa) / 10) * 20) if cgpa else 0
    resume_component = resume_score * 0.35
    skills_component = min(20, len(existing_skills) * 3)
    project_component = min(15, len(projects) * 5)
    certification_component = min(10, len(certifications) * 5)

    readiness = round(min(100, cgpa_component + resume_component + skills_component + project_component + certification_component))
    strengths = []
    weaknesses = []
    recommendations = []

    if cgpa >= 8.0:
        strengths.append('Strong academic performance')
    if resume_score >= 70:
        strengths.append('Resume has strong fundamentals')
    if len(existing_skills) >= 4:
        strengths.append('Solid technical skill coverage')
    if projects:
        strengths.append('Project experience included')
    if certifications:
        strengths.append('Certifications strengthen your profile')

    if cgpa < 6.5:
        weaknesses.append('CGPA below preferred placement benchmark')
    if resume_score < 60:
        weaknesses.append('Resume needs better structure and keywords')
    if not projects:
        weaknesses.append('Add at least one detailed project section')
    if not certifications:
        weaknesses.append('Consider adding certifications or training')
    if len(skill_gap.get('missing_skills', [])) > 5:
        weaknesses.append('Key industry skills are missing from your profile')

    if cgpa < 7.0:
        recommendations.append('Focus on academic consistency and CGPA strength.')
    if resume_score < 75:
        recommendations.append('Improve resume content, formatting and section coverage.')
    if skill_gap.get('recommended_skills'):
        recommendations.append('Learn: ' + ', '.join(skill_gap['recommended_skills'][:4]) + '.')
    if not projects:
        recommendations.append('Build one or two capstone projects with measurable outcomes.')

    return readiness, strengths[:3], weaknesses[:3], recommendations[:4]


def load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f'Trained model not found at {MODEL_PATH}. '
            'Run train_model.py to generate model.pkl, then redeploy.'
        )
    with open(MODEL_PATH, 'rb') as f:
        return pickle.load(f)


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return check_password_hash(hashed, password)


# ─── PostgreSQL user helpers ──────────────────────────────────
# All queries use %s placeholders (psycopg2 style).
# RealDictCursor is set on the connection in database/db.py,
# so every fetchone()/fetchall() returns plain dict / list[dict].

def get_user_by_username(conn, username: str):
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM users WHERE LOWER(username) = LOWER(%s)',
        (username.strip(),)
    )
    row = cur.fetchone()
    cur.close()
    return row


def get_user_by_email(conn, email: str):
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM users WHERE LOWER(email) = LOWER(%s)',
        (email.strip(),)
    )
    row = cur.fetchone()
    cur.close()
    return row


def get_user_by_id(conn, user_id: int):
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    row = cur.fetchone()
    cur.close()
    return row


def create_user(conn, username: str, password: str, role: str = 'student',
                email: str = None, full_name: str = None,
                college: str = None, branch: str = None, year: str = None,
                cgpa: float = None, skills: str = None, phone: str = None,
                profile_picture: str = None, resume_filename: str = None,
                resume_uploaded_at: str = None, resume_text: str = None,
                resume_analysis: str = None, resume_score: float = None,
                readiness_score: float = None, skill_gap: str = None,
                career_recommendations: str = None, learning_roadmap: str = None):
    hashed = hash_password(password)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (
            username, email, password, role, full_name,
            college, branch, year, cgpa, skills, phone,
            profile_picture, resume_filename, resume_uploaded_at,
            resume_text, resume_analysis, resume_score, readiness_score,
            skill_gap, career_recommendations, learning_roadmap
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
        )
        """,
        (
            username.strip(),
            email.strip() if email else None,
            hashed,
            role,
            full_name.strip() if full_name else None,
            college.strip() if college else None,
            branch.strip() if branch else None,
            year.strip() if year else None,
            float(cgpa) if cgpa is not None else None,
            skills.strip() if skills else None,
            phone.strip() if phone else None,
            profile_picture,
            resume_filename,
            resume_uploaded_at,
            resume_text,
            resume_analysis,
            resume_score,
            readiness_score,
            skill_gap,
            career_recommendations,
            learning_roadmap,
        )
    )
    conn.commit()
    cur.close()


def generate_password_reset_token(username: str) -> str:
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    return serializer.dumps(username, salt=SECURITY_SALT)


def verify_password_reset_token(token: str, max_age: int = PASSWORD_RESET_TIMEOUT):
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    try:
        return serializer.loads(token, salt=SECURITY_SALT, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None


def predict_placement(data: dict):
    model_data = load_model()
    pipeline = model_data['pipeline']

    try:
        cgpa = float(data.get('cgpa', 0))
        tenth = float(data.get('tenth_percentage', 0))
        twelfth = float(data.get('twelfth_percentage', 0))
        apt = float(data.get('aptitude_score', 0))
        code = float(data.get('coding_score', 0))
        comm = float(data.get('communication_score', 0))
        intern = int(data.get('internship', 0))
        proj = int(data.get('projects', 0))
        back = int(data.get('backlogs', 0))
    except ValueError as exc:
        raise ValueError('Please enter valid numeric values for all prediction fields.') from exc

    row = {
        'cgpa': cgpa,
        'tenth_percentage': tenth,
        'twelfth_percentage': twelfth,
        'aptitude_score': apt,
        'coding_score': code,
        'communication_score': comm,
        'internship': intern,
        'projects': proj,
        'backlogs': back,
        'academic_avg': (cgpa * 10 + tenth + twelfth) / 3,
        'skill_avg': (apt + code + comm) / 3,
        'experience_score': intern * 10 + proj * 5,
    }
    X = pd.DataFrame([row], columns=FEATURE_COLS)

    probabilities = pipeline.predict_proba(X)[0]
    placed = int(pipeline.predict(X)[0])
    return placed, round(float(probabilities[1]) * 100, 2)


def get_model_info():
    model_data = load_model()
    info = {
        'model_name': model_data['model_name'],
        'accuracy': round(model_data['accuracy'] * 100, 2),
        'precision': round(model_data['precision'] * 100, 2),
        'recall': round(model_data['recall'] * 100, 2),
        'f1': round(model_data['f1'] * 100, 2),
        'feature_importance': model_data.get('feature_importance', {}),
        'all_results': {
            k: {m: round(v * 100, 2) for m, v in r.items()}
            for k, r in model_data['all_results'].items()
        }
    }
    return info


def init_db(db_path: str = None):
    """
    Compatibility shim — delegates to database.db.init_db() which uses PostgreSQL.
    The db_path argument is accepted but ignored (kept for backward-compat call sites).
    """
    from database.db import init_db as pg_init_db
    pg_init_db()
