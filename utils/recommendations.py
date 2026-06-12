"""
utils/recommendations.py - Rule-based placement readiness suggestions.

This is a lightweight, dependency-free "AI improvement suggestions" engine.
It is intentionally modular so it can later be swapped for / augmented by an
LLM provider (OpenAI / Gemini / Ollama) without changing the call site.
"""


def _f(data, key, default=0.0):
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default


def generate_suggestions(data):
    """Return a list of actionable suggestions based on a student's profile."""
    suggestions = []

    cgpa = _f(data, 'cgpa')
    coding = _f(data, 'coding_score')
    aptitude = _f(data, 'aptitude_score')
    communication = _f(data, 'communication_score')
    internship = _f(data, 'internship')
    projects = _f(data, 'projects')
    backlogs = _f(data, 'backlogs')

    if cgpa < 7.0:
        suggestions.append("Work on raising your CGPA above 7.0 — many companies use it as a first filter.")
    if coding < 60:
        suggestions.append("Strengthen coding skills with consistent DSA practice (aim for a coding score of 70+).")
    if aptitude < 60:
        suggestions.append("Practice quantitative aptitude and logical reasoning to clear placement aptitude rounds.")
    if communication < 60:
        suggestions.append("Improve communication skills through mock interviews and group discussions.")
    if internship < 1:
        suggestions.append("Pursue at least one internship — real-world experience significantly boosts placement odds.")
    if projects < 2:
        suggestions.append("Build 2-3 strong portfolio projects to demonstrate practical skills to recruiters.")
    if backlogs > 0:
        suggestions.append("Clear pending backlogs as soon as possible — they are a common disqualifier.")

    if not suggestions:
        suggestions.append("Strong profile! Keep refining your interview skills and apply broadly.")

    return suggestions
