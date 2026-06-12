"""
train_model.py - Dataset Generation & ML Model Training
College Placement Prediction System

Trains and compares multiple classifiers, computes a full metric suite
(accuracy / precision / recall / F1 / ROC-AUC / cross-validated accuracy +
confusion matrix), automatically selects the best model and persists it with
joblib. A human-readable summary is written to model_metrics.json.
"""

import json
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (GradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings('ignore')

# XGBoost is optional: it produces strong results but is a heavy dependency.
try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_XGB = False


def generate_dataset(n=600, random_state=42):
    np.random.seed(random_state)
    branches = ['CSE', 'ECE', 'ME', 'CE', 'EEE', 'IT']
    branch_factor = {'CSE': 0.20, 'IT': 0.15, 'ECE': 0.10, 'EEE': 0.05, 'ME': -0.05, 'CE': -0.10}

    branch_list = np.random.choice(branches, n)
    cgpa = np.clip(np.random.normal(7.2, 1.0, n), 4.0, 10.0).round(2)
    tenth = np.clip(np.random.normal(75, 12, n), 40, 99).round(2)
    twelfth = np.clip(np.random.normal(72, 12, n), 40, 99).round(2)
    aptitude = np.random.randint(30, 100, n)
    coding = np.random.randint(20, 100, n)
    communication = np.random.randint(30, 100, n)
    internship = np.random.randint(0, 3, n)
    projects = np.random.randint(0, 6, n)
    backlogs = np.random.randint(0, 5, n)

    score = (
        (cgpa - 4) / 6 * 30 +
        tenth / 100 * 10 +
        twelfth / 100 * 10 +
        aptitude / 100 * 15 +
        coding / 100 * 15 +
        communication / 100 * 10 +
        internship / 2 * 5 +
        projects / 5 * 5 +
        np.array([branch_factor.get(b, 0) for b in branch_list]) * 10 -
        backlogs * 3
    )
    noise = np.random.normal(0, 5, n)
    prob = 1 / (1 + np.exp(-(score + noise - 50) / 10))
    placed = (prob > 0.5).astype(int)

    df = pd.DataFrame({
        'name': [f"Student_{i:03d}" for i in range(1, n + 1)],
        'roll_no': [f"ROLL{i:04d}" for i in range(1, n + 1)],
        'email': [f"student{i:03d}@college.edu" for i in range(1, n + 1)],
        'branch': branch_list,
        'cgpa': cgpa,
        'tenth_percentage': tenth,
        'twelfth_percentage': twelfth,
        'aptitude_score': aptitude,
        'coding_score': coding,
        'communication_score': communication,
        'internship': internship,
        'projects': projects,
        'backlogs': backlogs,
        'placed': placed
    })
    return df


def prepare_features(df):
    feature_cols = [
        'cgpa', 'tenth_percentage', 'twelfth_percentage',
        'aptitude_score', 'coding_score', 'communication_score',
        'internship', 'projects', 'backlogs'
    ]
    X = df[feature_cols].copy()
    y = df['placed'].copy()
    X['academic_avg'] = (X['cgpa'] * 10 + X['tenth_percentage'] + X['twelfth_percentage']) / 3
    X['skill_avg'] = (X['aptitude_score'] + X['coding_score'] + X['communication_score']) / 3
    X['experience_score'] = X['internship'] * 10 + X['projects'] * 5
    return X, y


def build_models():
    models = {
        'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42),
        'Random Forest': RandomForestClassifier(n_estimators=200, random_state=42),
        'Gradient Boosting': GradientBoostingClassifier(random_state=42),
        'Decision Tree': DecisionTreeClassifier(max_depth=6, random_state=42),
        'SVM': SVC(probability=True, random_state=42),
    }
    if _HAS_XGB:
        models['XGBoost'] = XGBClassifier(
            n_estimators=200, learning_rate=0.1, max_depth=4,
            eval_metric='logloss', random_state=42,
        )
    return models


def train_and_evaluate(X, y, X_train, X_test, y_train, y_test):
    results = {}
    best_name, best_score, best_pipeline = None, -1.0, None

    for name, clf in build_models().items():
        pipeline = Pipeline([('scaler', StandardScaler()), ('clf', clf)])
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        y_proba = pipeline.predict_proba(X_test)[:, 1]

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        roc = roc_auc_score(y_test, y_proba)
        cv = cross_val_score(pipeline, X, y, cv=5, scoring='accuracy').mean()
        cm = confusion_matrix(y_test, y_pred).tolist()

        results[name] = {
            'accuracy': acc, 'precision': prec, 'recall': rec, 'f1': f1,
            'roc_auc': roc, 'cv_accuracy': cv, 'confusion_matrix': cm,
            'pipeline': pipeline,
        }
        print(f"{name:20s} Acc={acc:.4f} Prec={prec:.4f} Rec={rec:.4f} "
              f"F1={f1:.4f} ROC-AUC={roc:.4f} CV={cv:.4f}")

        if f1 > best_score:
            best_score, best_name, best_pipeline = f1, name, pipeline

    return results, best_name, best_pipeline


def main():
    print("Generating dataset...")
    df = generate_dataset()
    df.to_csv('dataset.csv', index=False)
    print(f"Saved dataset.csv ({len(df)} records)")

    X, y = prepare_features(df)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    print("\nTraining models...")
    results, best_name, best_pipeline = train_and_evaluate(
        X, y, X_train, X_test, y_train, y_test)

    best = results[best_name]
    serializable_results = {
        k: {m: v for m, v in r.items() if m != 'pipeline'}
        for k, r in results.items()
    }

    model_data = {
        'pipeline': best_pipeline,
        'model_name': best_name,
        'accuracy': best['accuracy'],
        'precision': best['precision'],
        'recall': best['recall'],
        'f1': best['f1'],
        'roc_auc': best['roc_auc'],
        'cv_accuracy': best['cv_accuracy'],
        'confusion_matrix': best['confusion_matrix'],
        'all_results': {
            k: {m: v for m, v in r.items() if m != 'confusion_matrix'}
            for k, r in serializable_results.items()
        },
    }
    joblib.dump(model_data, 'model.pkl')

    with open('model_metrics.json', 'w') as f:
        json.dump({
            'best_model': best_name,
            'metrics': serializable_results,
        }, f, indent=2)

    print(f"\nBest model: {best_name} (F1: {best['f1']:.4f}, Acc: {best['accuracy']:.4f})")
    print("Saved model.pkl and model_metrics.json")


if __name__ == '__main__':
    main()
