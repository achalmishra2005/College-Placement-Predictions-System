"""
Script to generate a realistic college placement dataset
Run once to create dataset.csv
"""

import pandas as pd
import numpy as np

np.random.seed(42)

branches = ['CSE', 'ECE', 'EEE', 'MECH', 'CIVIL', 'IT', 'AIDS', 'AIML']
n = 1000

# Generate correlated features for realism
cgpa = np.round(np.random.normal(7.5, 1.0, n).clip(5.0, 10.0), 2)
tenth = np.round((cgpa * 8 + np.random.normal(0, 5, n)).clip(50, 100), 2)
twelfth = np.round((cgpa * 7.5 + np.random.normal(0, 6, n)).clip(50, 100), 2)
aptitude = np.round((cgpa * 7 + np.random.normal(0, 8, n)).clip(20, 100), 2)
coding = np.round((cgpa * 6.5 + np.random.normal(0, 10, n)).clip(10, 100), 2)
communication = np.random.randint(1, 11, n)
internship = np.random.choice([0, 1], n, p=[0.45, 0.55])
projects = np.random.randint(0, 8, n)
backlogs = np.random.choice([0, 1, 2, 3, 4], n, p=[0.55, 0.20, 0.12, 0.08, 0.05])

# Placement logic: higher scores → more likely placed
score = (
    (cgpa - 5) / 5 * 30 +
    aptitude / 100 * 20 +
    coding / 100 * 20 +
    communication / 10 * 10 +
    internship * 10 +
    projects * 1.5 -
    backlogs * 8 +
    (tenth - 50) / 50 * 5 +
    (twelfth - 50) / 50 * 5
)
prob = 1 / (1 + np.exp(-(score - 50) / 10))
placed = (np.random.random(n) < prob).astype(int)

df = pd.DataFrame({
    'cgpa': cgpa,
    'tenth_percentage': tenth,
    'twelfth_percentage': twelfth,
    'aptitude_score': aptitude,
    'coding_score': coding,
    'communication_score': communication,
    'internship': internship,
    'projects': projects,
    'backlogs': backlogs,
    'branch': np.random.choice(branches, n),
    'placed': placed
})

df.to_csv('dataset.csv', index=False)
print(f"Dataset created: {n} rows, placement rate: {placed.mean():.2%}")
