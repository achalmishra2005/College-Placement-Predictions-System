# 🎓 College Placement Prediction System

<div align="center">

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.5-F7931E?logo=scikitlearn)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite)

**An AI-powered web application that predicts whether a student is likely to get placed based on academic and skill parameters.**

</div>

---

## ✨ Features

- 🤖 **ML Prediction** — Logistic Regression, Random Forest & Decision Tree; best model auto-selected
- 📊 **Interactive Dashboard** — Pie, Bar, Line & Doughnut charts using Chart.js
- 🔐 **Admin Panel** — Full CRUD, search, filter, and CSV export
- 🌙 **Dark / Light Mode** — Glassmorphism UI with animated gradients
- 📱 **Responsive** — Mobile-first Bootstrap 5 layout
- ⚡ **Real-time Probability** — Shows placement chance as a percentage with visual ring

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js |
| Backend | Python 3, Flask |
| Database | SQLite |
| ML | scikit-learn, pandas, numpy, pickle |

## 🚀 Installation

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/college-placement-prediction.git
cd college-placement-prediction

# 2. Install dependencies
pip install -r requirements.txt

# 3. Train the model & generate dataset
python train_model.py

# 4. Run the app
python app.py
```

Open **http://localhost:5000** in your browser.

**Admin login:** `admin` / `admin123`

## 📁 Project Structure

```
College-Placement-Prediction-System/
├── app.py              # Flask routes & API
├── train_model.py      # Dataset generation & ML training
├── dataset.csv         # Generated training data
├── model.pkl           # Trained model (auto-generated)
├── requirements.txt
├── database/
│   └── placement.db    # SQLite database
├── static/
│   ├── css/style.css
│   └── js/script.js
├── templates/          # Jinja2 HTML templates
└── utils/helpers.py    # Prediction & DB helpers
```

## 🧠 ML Model Performance

| Model | Accuracy |
|-------|----------|
| Logistic Regression | ~85% |
| Random Forest | ~83% |
| Decision Tree | ~76% |

## 🔮 Future Scope

- Deep learning model (Neural Network)
- Resume parser integration
- Email notifications on prediction
- Student self-registration portal
- Docker deployment

## 👤 Author

**CSE Mini Project** — 3rd Year Computer Science Engineering  
Built with Flask + scikit-learn + Bootstrap 5
