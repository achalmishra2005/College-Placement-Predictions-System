"""
train_model.py - Dataset Generation & ML Model Training
College Placement Prediction System
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.pipeline import Pipeline
import xgboost as xgb
import pickle
import warnings
warnings.filterwarnings('ignore')

def generate_dataset(n=600, random_state=42):
    np.random.seed(random_state)
    branches = ['CSE', 'ECE', 'ME', 'CE', 'EEE', 'IT']
    branch_factor = {'CSE': 0.20, 'IT': 0.15, 'ECE': 0.10, 'EEE': 0.05, 'ME': -0.05, 'CE': -0.10}

    branch_list  = np.random.choice(branches, n)
    cgpa         = np.clip(np.random.normal(7.2, 1.0, n), 4.0, 10.0).round(2)
    tenth        = np.clip(np.random.normal(75, 12, n), 40, 99).round(2)
    twelfth      = np.clip(np.random.normal(72, 12, n), 40, 99).round(2)
    aptitude     = np.random.randint(30, 100, n)
    coding       = np.random.randint(20, 100, n)
    communication= np.random.randint(30, 100, n)
    internship   = np.random.randint(0, 3, n)
    projects     = np.random.randint(0, 6, n)
    backlogs     = np.random.randint(0, 5, n)

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
    noise  = np.random.normal(0, 5, n)
    prob   = 1 / (1 + np.exp(-(score + noise - 50) / 10))
    placed = (prob > 0.5).astype(int)

    df = pd.DataFrame({
        'name': [f"Student_{i:03d}" for i in range(1, n+1)],
        'roll_no': [f"ROLL{i:04d}" for i in range(1, n+1)],
        'email': [f"student{i:03d}@college.edu" for i in range(1, n+1)],
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
    X['academic_avg']    = (X['cgpa'] * 10 + X['tenth_percentage'] + X['twelfth_percentage']) / 3
    X['skill_avg']       = (X['aptitude_score'] + X['coding_score'] + X['communication_score']) / 3
    X['experience_score']= X['internship'] * 10 + X['projects'] * 5
    return X, y

def train_and_evaluate(X_train, X_test, y_train, y_test):
    models = {
        'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42),
        'Random Forest':       RandomForestClassifier(n_estimators=150, random_state=42),
        'Gradient Boosting':   GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, random_state=42),
        'XGBoost':             xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss', random_state=42),
        'Decision Tree':       DecisionTreeClassifier(max_depth=6, random_state=42),
    }
    results = {}
    best_name, best_score, best_pipeline = None, 0, None

    for name, clf in models.items():
        pipeline = Pipeline([('scaler', StandardScaler()), ('clf', clf)])
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        acc  = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred)
        rec  = recall_score(y_test, y_pred)
        f1   = f1_score(y_test, y_pred)
        results[name] = {'accuracy': acc, 'precision': prec, 'recall': rec, 'f1': f1, 'pipeline': pipeline}
        print(f"\n{name}: Acc={acc:.4f} Prec={prec:.4f} Rec={rec:.4f} F1={f1:.4f}")
        if acc > best_score:
            best_score, best_name, best_pipeline = acc, name, pipeline

    return results, best_name, best_pipeline

def main():
    print("Generating dataset...")
    df = generate_dataset()
    df.to_csv('dataset.csv', index=False)
    print(f"Saved dataset.csv ({len(df)} records)")

    X, y = prepare_features(df)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print("Training models...")
    results, best_name, best_pipeline = train_and_evaluate(X_train, X_test, y_train, y_test)

    importance = {}
    best_clf = best_pipeline.named_steps['clf']
    if hasattr(best_clf, 'feature_importances_'):
        importance = dict(zip(X_train.columns, best_clf.feature_importances_))
    elif hasattr(best_clf, 'coef_'):
        importance = dict(zip(X_train.columns, abs(best_clf.coef_[0]).tolist()))

    model_data = {
        'pipeline': best_pipeline,
        'model_name': best_name,
        'accuracy': results[best_name]['accuracy'],
        'precision': results[best_name]['precision'],
        'recall': results[best_name]['recall'],
        'f1': results[best_name]['f1'],
        'feature_importance': importance,
        'all_results': {k: {m: v for m, v in r.items() if m != 'pipeline'} for k, r in results.items()}
    }
    with open('model.pkl', 'wb') as f:
        pickle.dump(model_data, f)
    print(f"\nBest model: {best_name} (Accuracy: {results[best_name]['accuracy']:.4f})")
    print('Saved model.pkl')

if __name__ == '__main__':
    main()
