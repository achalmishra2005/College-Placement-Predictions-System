# College Placement Prediction System

An AI-powered Flask web app that predicts whether a student is likely to be
placed based on academic and skill parameters, with an admin panel, analytics
dashboard, and a multi-model ML pipeline.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.6-F7931E?logo=scikitlearn)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite)

---

## Features

- **ML Prediction** — Logistic Regression, Random Forest, Gradient Boosting,
  Decision Tree, SVM and (optional) XGBoost are trained and compared; the best
  model is auto-selected by F1 score.
- **Improvement Suggestions** — rule-based, modular engine that gives each
  student actionable feedback (ready to be upgraded to an LLM provider).
- **Analytics Dashboard** — Pie / Bar / Line / Doughnut charts (Chart.js).
- **Admin Panel** — full CRUD, search, filters, and CSV export.
- **Security** — hashed admin passwords, CSRF protection, secure session
  cookies, security headers, and server-side input validation.
- **Dark / Light Mode**, responsive Bootstrap 5 UI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js |
| Backend | Python 3, Flask, Flask-WTF |
| Database | SQLite |
| ML | scikit-learn, XGBoost, pandas, numpy, joblib |
| Serving | gunicorn, Docker |

## Quick Start

> **Note:** if you downloaded this as a ZIP, it may extract into a nested
> folder (`College-Placement-Prediction-System/College-Placement-Prediction-System/`).
> Make sure you `cd` into the folder that actually contains `app.py` before
> running any commands.

```bash
# 1. (optional) create a virtual environment
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. (optional) configure environment
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux

# 4. train the model & generate the dataset
python train_model.py

# 5. run the app
python app.py
```

Open **http://localhost:5000**.

**Default admin login:** `admin` / `admin123` (change via `.env`).
The default password is automatically **hashed** on first run, and any legacy
plaintext password in an existing database is upgraded to a hash automatically.

## Configuration

All settings are read from environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-change-me` | Flask session signing key (set a strong value in production) |
| `FLASK_DEBUG` | `false` | Enable debug mode |
| `PORT` | `5000` | Port to serve on |
| `DB_PATH` | `database/placement.db` | SQLite path |
| `MODEL_PATH` | `model.pkl` | Trained model path |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin123` | Seeded admin (first run only) |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | empty | Optional, for future LLM-backed AI modules |

## Deployment

**Docker:**
```bash
docker compose up --build
```

**Render / Railway:** a `render.yaml` and `Procfile` are included.
The production server runs via gunicorn: `gunicorn app:app`.

## ML Pipeline

`train_model.py` generates a synthetic dataset, engineers features
(`academic_avg`, `skill_avg`, `experience_score`), trains several classifiers
inside a `StandardScaler` pipeline, and reports a full metric suite — accuracy,
precision, recall, F1, ROC-AUC and 5-fold cross-validated accuracy plus a
confusion matrix. The best model (by F1) is saved to `model.pkl` and a summary
is written to `model_metrics.json`.

## Project Structure

```
College-Placement-Prediction-System/
├── app.py                 # Flask routes, validation, security, error handlers
├── config.py              # Env-driven configuration
├── train_model.py         # Dataset generation + multi-model training
├── requirements.txt
├── Dockerfile / docker-compose.yml / Procfile / render.yaml
├── .env.example
├── database/placement.db  # SQLite database (auto-created)
├── model.pkl              # Trained model (auto-generated)
├── model_metrics.json     # Metric summary (auto-generated)
├── static/css|js/
├── templates/             # Jinja2 templates
└── utils/
    ├── helpers.py         # Model loading, prediction, hashing, DB init
    └── recommendations.py # Rule-based improvement suggestions
```

## Roadmap

The AI suggestion engine in `utils/recommendations.py` is intentionally modular
so it can be backed by OpenAI / Gemini / Ollama / Hugging Face later. Planned:
resume parsing & scoring, skill-gap analysis, company recommendations, and a
career chatbot.
