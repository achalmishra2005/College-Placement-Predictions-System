"""validate_deploy.py — Pre-deployment validation script."""
import sys
import os
import ast

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

errors = []
warnings = []

# ─── 1. Syntax checks ────────────────────────────────────────────────────────
print("=" * 60)
print("1. SYNTAX CHECKS")
for fname in ['app.py', 'utils/helpers.py', 'api/index.py']:
    try:
        ast.parse(open(fname, encoding='utf-8').read())
        print(f"   [PASS] {fname}")
    except SyntaxError as e:
        errors.append(f"Syntax error in {fname}: {e}")
        print(f"   [FAIL] {fname}: {e}")

# ─── 2. Import checks ─────────────────────────────────────────────────────────
print("\n2. IMPORT CHECKS")
try:
    import app as flask_app
    routes = list(flask_app.app.url_map.iter_rules())
    print(f"   [PASS] app.py — {len(routes)} routes loaded")
except Exception as e:
    errors.append(f"Import error in app.py: {e}")
    print(f"   [FAIL] app.py: {e}")
    sys.exit(1)

try:
    from utils.helpers import (
        predict_placement, init_db, parse_resume, score_resume,
        skill_gap_analysis, recommend_careers, build_learning_roadmap,
        placement_readiness_score, PDF_SUPPORT, MODEL_PATH
    )
    print(f"   [PASS] utils/helpers.py — PDF_SUPPORT={PDF_SUPPORT}")
    print(f"   [INFO] MODEL_PATH = {MODEL_PATH}")
    if not os.path.exists(MODEL_PATH):
        warnings.append(f"model.pkl not found at {MODEL_PATH} — prediction will fail until retrained")
        print(f"   [WARN] model.pkl missing at {MODEL_PATH}")
    else:
        print(f"   [PASS] model.pkl found ({os.path.getsize(MODEL_PATH)} bytes)")
except Exception as e:
    errors.append(f"Import error in utils/helpers.py: {e}")
    print(f"   [FAIL] utils/helpers.py: {e}")

# ─── 3. Route audit ───────────────────────────────────────────────────────────
print("\n3. ROUTE AUDIT")
route_info = sorted(
    [(r.rule, sorted(r.methods - {'HEAD', 'OPTIONS'})) for r in routes],
    key=lambda x: x[0]
)
for rule, methods in route_info:
    print(f"   {rule:55s} {methods}")

# ─── 4. ML model test ─────────────────────────────────────────────────────────
print("\n4. ML MODEL VALIDATION")
test_cases = [
    ('High performer', {'cgpa': '9.2', 'tenth_percentage': '90',
                        'twelfth_percentage': '88', 'aptitude_score': '85',
                        'coding_score': '90', 'communication_score': '80',
                        'internship': '2', 'projects': '3', 'backlogs': '0'}),
    ('Low performer',  {'cgpa': '5.5', 'tenth_percentage': '55',
                        'twelfth_percentage': '52', 'aptitude_score': '40',
                        'coding_score': '35', 'communication_score': '45',
                        'internship': '0', 'projects': '0', 'backlogs': '3'}),
]
for label, data in test_cases:
    try:
        placed, prob = predict_placement(data)
        print(f"   [PASS] {label}: placed={placed}, prob={prob}%")
    except Exception as e:
        errors.append(f"Prediction failed for {label}: {e}")
        print(f"   [FAIL] {label}: {e}")

# ─── 5. DB connection (PostgreSQL) ───────────────────────────────────────────
print("\n5. DATABASE CONNECTION")
try:
    from database.db import ping, init_db, get_db, close_db
    if ping():
        db = get_db()
        cur = db.cursor()
        required_tables = {'students', 'users', 'jobs', 'applications'}
        found_tables = set()
        for tbl in required_tables:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                (tbl,)
            )
            if cur.fetchone():
                found_tables.add(tbl)
        cur.close()
        close_db(db)
        missing_tables = required_tables - found_tables
        if missing_tables:
            errors.append(f"Missing DB tables: {missing_tables}")
            print(f"   [FAIL] Missing tables: {missing_tables}")
        else:
            print(f"   [PASS] PostgreSQL connected — all tables present: {sorted(found_tables)}")
    else:
        warnings.append("PostgreSQL ping failed — set SUPABASE_DB_* env vars")
        print("   [WARN] PostgreSQL unreachable (no .env configured yet — expected locally)")
except Exception as e:
    warnings.append(f"DB check skipped: {e}")
    print(f"   [WARN] DB check skipped: {e}")

# ─── 6. AI helpers smoke test ─────────────────────────────────────────────────
print("\n6. AI HELPERS SMOKE TEST")
try:
    sample_text = "Python SQL Docker AWS Flask B.Tech project developed machine learning"
    parsed   = parse_resume(sample_text)
    score, breakdown, suggestions = score_resume(parsed, sample_text)
    gap      = skill_gap_analysis(parsed, "Python, SQL, React")
    careers  = recommend_careers(parsed, {"cgpa": 8.5})
    roadmap  = build_learning_roadmap(gap, careers)
    readiness, strengths, weaknesses, recs = placement_readiness_score(
        {"cgpa": 8.5, "skills": "Python, SQL"}, score, parsed, gap
    )
    print(f"   [PASS] parse_resume — {len(parsed['technical_skills'])} skills detected")
    print(f"   [PASS] score_resume — {score}/100")
    print(f"   [PASS] skill_gap_analysis — {len(gap['missing_skills'])} missing skills")
    print(f"   [PASS] recommend_careers — {careers}")
    print(f"   [PASS] build_learning_roadmap — {len(roadmap)} weeks")
    print(f"   [PASS] placement_readiness_score — {readiness}/100")
except Exception as e:
    errors.append(f"AI helpers failed: {e}")
    print(f"   [FAIL] {e}")

# ─── 7. Required files check ──────────────────────────────────────────────────
print("\n7. REQUIRED FILES CHECK")
required_files = [
    'app.py', 'requirements.txt', 'vercel.json', 'api/index.py',
    'model.pkl', 'utils/helpers.py', 'utils/__init__.py',
    'templates/base.html', 'static/css/style.css', 'static/js/script.js',
    '.gitignore', '.env.example',
]
for fpath in required_files:
    exists = os.path.exists(fpath)
    status = 'PASS' if exists else 'WARN'
    if not exists and fpath not in ['utils/__init__.py']:
        warnings.append(f"Missing file: {fpath}")
    print(f"   [{status}] {fpath}")

# Check utils/__init__.py separately (critical for Vercel imports)
if not os.path.exists('utils/__init__.py'):
    errors.append("Missing utils/__init__.py — required for Python package imports on Vercel")
    print("   [FAIL] utils/__init__.py — MISSING (will break Vercel imports)")

# ─── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("DEPLOYMENT READINESS SUMMARY")
print("=" * 60)
if errors:
    print(f"\n[ERRORS] {len(errors)} critical error(s):")
    for e in errors:
        print(f"  [ERR] {e}")
else:
    print("\n[ERRORS] None — zero critical errors found!")

if warnings:
    print(f"\n[WARNINGS] {len(warnings)} warning(s):")
    for w in warnings:
        print(f"  [WARN] {w}")
else:
    print("[WARNINGS] None")

score = max(0, 100 - len(errors) * 20 - len(warnings) * 5)
print(f"\nVercel Readiness Score: {score}/100")
print()
sys.exit(1 if errors else 0)
