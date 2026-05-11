# App Link 
https://careerquest-sg-eogw2nrbmmcbjnvd5v5wws.streamlit.app/

# CareerQuest SG

CareerQuest SG is a career pathway intelligence prototype that helps users explore realistic career transitions in Singapore.

It combines:
- graph-based career transition modelling
- skill-gap analysis
- real SkillsFuture course recommendations
- MOM labour-demand signals
- route confidence and explainability
- personalised learning-plan generation
- interactive career-path visualisation

## Live Demo

Add your deployed Streamlit link here:

```text
https://your-app-name.streamlit.app
```

## What the App Does

CareerQuest SG lets users:
1. Select a current role or fresh graduate profile
2. Select a target occupation
3. Edit their current skill profile
4. View skill gaps for the target role
5. Compare fastest, cheapest, easiest, and balanced routes
6. Explore real SkillsFuture course options
7. Build a personalised learning plan
8. View an interactive career graph

## Data Sources

- MySkillsFuture Course Directory from data.gov.sg
- MOM job vacancy data from data.gov.sg
- Custom career transition graph
- Custom occupation-skill mappings

## Tech Stack

Python, Streamlit, SQLite, Pandas, Altair, PyVis, OpenPyXL

## Project Structure

```text
careerquest-sg/
├─ frontend/
│  ├─ app.py
│  ├─ course_options.py
│  └─ graph_viz.py
├─ scripts/
├─ data/
│  ├─ raw/
│  ├─ processed/
│  ├─ planning/
│  └─ raw_external/
├─ database/
│  └─ schema.sql
├─ requirements.txt
├─ README.md
└─ .gitignore
```

## How to Run Locally

```bash
pip install -r requirements.txt
python -m streamlit run frontend/app.py
```

## Deployment

Recommended platform: Streamlit Community Cloud.

Deployment settings:

```text
Repository: your GitHub repository
Branch: main
Main file path: frontend/app.py
```

## Notes and Limitations

This is a decision-support prototype, not an official labour-market prediction system.

The score outputs are structured indicators, not guaranteed probabilities. Course availability is used as a training pathway signal, not as a direct measure of job demand.

## Resume Bullet

Built CareerQuest SG, a Streamlit-based career pathway intelligence prototype integrating MOM labour-demand data, SkillsFuture course data, graph-based career transitions, explainable scoring, route confidence, and interactive learning-plan generation.

## Author

Chao Hung Huang
