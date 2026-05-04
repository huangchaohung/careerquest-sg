# CareerQuest SG — Workforce Mobility Simulator

CareerQuest SG is a data-driven tool that helps users explore career transitions in a structured and explainable way.

Instead of guessing what to do next, it provides:
- career pathway simulation
- skill gap analysis
- real training recommendations
- demand-aware feasibility scoring

---

## What it does

Given a user's current profile and target role, the system:

- estimates how feasible the transition is
- shows multiple possible pathways
- highlights missing skills
- recommends real SkillsFuture courses
- explains why a pathway is easier or harder

---

## Key Features

- Interactive career graph (PyVis)
- Skill-based transition modelling
- Real SkillsFuture course integration
- Demand estimation using MOM job vacancy data
- Explainable scoring system
- Route comparison (fastest / cheapest / easiest)

---

## Tech Stack

- Python (ETL + logic)
- SQLite (data layer)
- Streamlit (frontend)
- Pandas (data processing)
- PyVis (graph visualisation)

---

## Data Sources

- data.gov.sg — MOM Job Vacancy Dataset
- SkillsFuture Course Directory

---

## Why I built this

I wanted to explore how data can be used to make career decisions more structured and transparent.

Most people rely on intuition when planning their careers. This project tries to turn that into something more systematic:
- what skills matter
- what paths exist
- what trade-offs are involved

---

## Limitations

This is a prototype for exploration, not a predictive system.

It does not account for:
- personal experience
- interviews
- company-specific hiring decisions

---

## Demo

Run locally:

```bash
python -m streamlit run frontend/app.py