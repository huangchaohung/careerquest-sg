
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import altair as alt

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
DB_PATH = ROOT_DIR / "careerquest_seed.sqlite"
DEMAND_REPORT_PATH = ROOT_DIR / "data" / "processed" / "occupation_refined_demand_report.csv"

sys.path.append(str(SCRIPTS_DIR))

from strategy_modes import find_best_path_by_strategy, summarize_path
from chance_scoring import calculate_chance_score, score_to_label
from load_seed_data import init_db
from graph_viz import render_interactive_career_graph

st.set_page_config(page_title="CareerQuest SG", page_icon="🧭", layout="wide")


st.markdown("""
<style>
.path-card {
    background-color: white;
    padding: 1rem;
    border-radius: 1rem;
    border: 1px solid #e6eaf0;
    margin-bottom: 1rem;
}
.quest-card {
    background-color: #ffffff;
    padding: 0.9rem;
    border-radius: 0.8rem;
    border-left: 5px solid #4f6bed;
    margin-bottom: 0.7rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}
.small-muted {
    color: #687385;
    font-size: 0.9rem;
}
.route-pill {
    display: inline-block;
    background-color: #eef4ff;
    color: #2446a8;
    border: 1px solid #c8d7ff;
    padding: 0.18rem 0.55rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def initialize_database():
    init_db()
    return True


def get_connection():
    initialize_database()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data
def load_demand_report():
    if DEMAND_REPORT_PATH.exists():
        return pd.read_csv(DEMAND_REPORT_PATH)
    return pd.DataFrame()


def load_occupations(conn):
    rows = conn.execute(
        "SELECT name, sector, salary_median, demand_score FROM occupations ORDER BY sector, name"
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def load_all_skills(conn):
    rows = conn.execute(
        "SELECT skill_id, name, category FROM skills ORDER BY category, name"
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def get_required_skills_df(conn, occupation_name):
    rows = conn.execute("""
        SELECT s.name AS skill, s.category, os.importance
        FROM occupation_skills os
        JOIN occupations o ON os.occupation_id = o.occupation_id
        JOIN skills s ON os.skill_id = s.skill_id
        WHERE o.name = ?
        ORDER BY os.importance DESC, s.name ASC
    """, (occupation_name,)).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def get_default_skill_names(conn, occupation_name):
    df = get_required_skills_df(conn, occupation_name)
    if df.empty:
        return []
    return df["skill"].tolist()


def get_target_skill_rows(conn, target_occupation):
    rows = conn.execute("""
        SELECT s.skill_id, s.name AS skill, s.category, os.importance
        FROM occupation_skills os
        JOIN occupations o ON os.occupation_id = o.occupation_id
        JOIN skills s ON os.skill_id = s.skill_id
        WHERE o.name = ?
        ORDER BY os.importance DESC, s.name ASC
    """, (target_occupation,)).fetchall()
    return [dict(row) for row in rows]


def get_missing_skills_from_selected(conn, selected_skill_names, target_occupation):
    target_skills = get_target_skill_rows(conn, target_occupation)
    selected = set(selected_skill_names)
    missing = [skill for skill in target_skills if skill["skill"] not in selected]
    return sorted(missing, key=lambda x: (-x["importance"], x["skill"]))


def calculate_custom_skill_match(conn, selected_skill_names, target_occupation):
    target_skills = get_target_skill_rows(conn, target_occupation)
    if not target_skills:
        return 0.0
    selected = set(selected_skill_names)
    total_weight = sum(skill["importance"] for skill in target_skills)
    matched_weight = sum(skill["importance"] for skill in target_skills if skill["skill"] in selected)
    return matched_weight / total_weight if total_weight else 0.0


def qualification_rank(qualification):
    ranks = {
        "Secondary": 1,
        "ITE / Nitec": 2,
        "Diploma": 3,
        "Bachelor's Degree": 4,
        "Master's Degree": 5,
        "Other": 0,
    }
    return ranks.get(qualification, 0)


def get_min_qualification_for_role(role):
    role_lower = role.lower()
    if "manager" in role_lower or "senior" in role_lower or "machine learning engineer" in role_lower:
        return "Master's Degree"
    if role in {
        "Junior Data Scientist", "Data Engineer", "Data Analyst", "Business Intelligence Analyst",
        "Finance Analyst", "HR Analyst", "Supply Chain Analyst", "Business Analyst",
        "Operations Analyst", "Process Improvement Analyst", "Product Operations Associate",
    }:
        return "Bachelor's Degree"
    return "Diploma"


def add_fresh_grad_nodes_to_db(conn):
    existing = conn.execute("SELECT name FROM occupations").fetchall()
    existing_names = {row["name"] for row in existing}

    fresh_roles = [
        {
            "name": "Fresh Graduate — Data Science Bachelor's",
            "sector": "Fresh Graduate",
            "description": "Entry profile for a fresh graduate with a bachelor's degree in data science or a related field.",
            "salary_min": 3000, "salary_median": 3800, "salary_max": 4800, "demand_score": 0.70,
            "skills": ["Python", "Statistics", "Data Cleaning", "Data Visualization", "SQL", "Critical Thinking", "Presentation", "Communication"],
            "transitions": [
                ("Data Analyst", 4, 600, 2, "Data science graduates can enter data analyst roles by strengthening applied dashboarding and portfolio evidence."),
                ("Business Intelligence Analyst", 6, 900, 3, "Requires stronger dashboarding and business reporting exposure."),
                ("Junior Data Scientist", 8, 1400, 4, "Requires stronger modelling portfolio and applied machine learning evidence."),
            ],
        },
        {
            "name": "Fresh Graduate — Business Bachelor's",
            "sector": "Fresh Graduate",
            "description": "Entry profile for a fresh graduate with a bachelor's degree in business or management.",
            "salary_min": 2800, "salary_median": 3500, "salary_max": 4500, "demand_score": 0.65,
            "skills": ["Excel", "Business Requirements Gathering", "Stakeholder Management", "KPI Design", "Reporting", "Communication", "Presentation", "Critical Thinking"],
            "transitions": [
                ("Administrative Executive", 3, 300, 1, "Business graduates can enter administrative roles with minimal additional preparation."),
                ("Business Analyst", 7, 1000, 3, "Requires requirements analysis, process mapping, and project exposure."),
                ("Project Coordinator", 4, 500, 2, "Business graduates can enter project coordination through documentation and stakeholder coordination."),
            ],
        },
        {
            "name": "Fresh Graduate — Engineering Bachelor's",
            "sector": "Fresh Graduate",
            "description": "Entry profile for a fresh graduate with an engineering degree.",
            "salary_min": 3000, "salary_median": 3800, "salary_max": 5000, "demand_score": 0.68,
            "skills": ["Python", "Statistics", "Process Mapping", "Quality Control", "Problem Structuring", "Critical Thinking", "Documentation"],
            "transitions": [
                ("Operations Executive", 4, 400, 2, "Engineering graduates can enter operations roles through process and execution work."),
                ("Operations Analyst", 7, 900, 3, "Requires KPI, reporting, and operations analytics exposure."),
                ("Process Improvement Analyst", 8, 1200, 3, "Engineering background supports process improvement with added business analytics."),
            ],
        },
        {
            "name": "Fresh Graduate — Data Science Master's",
            "sector": "Fresh Graduate",
            "description": "Entry profile for a fresh graduate with a master's degree in data science or machine learning.",
            "salary_min": 4000, "salary_median": 5200, "salary_max": 7000, "demand_score": 0.72,
            "skills": ["Python", "SQL", "Statistics", "Machine Learning Basics", "Predictive Modelling", "Data Cleaning", "Data Visualization", "Critical Thinking", "Presentation"],
            "transitions": [
                ("Data Analyst", 3, 400, 1, "Master's graduates with data skills can enter data analyst roles with portfolio alignment."),
                ("Junior Data Scientist", 5, 800, 2, "Requires applied modelling portfolio and project evidence."),
                ("Machine Learning Engineer", 10, 1800, 4, "Requires deployment, software engineering, and production ML skills."),
            ],
        },
        {
            "name": "Fresh Graduate — Business Analytics Master's",
            "sector": "Fresh Graduate",
            "description": "Entry profile for a fresh graduate with a master's degree in business analytics.",
            "salary_min": 3800, "salary_median": 5000, "salary_max": 6800, "demand_score": 0.72,
            "skills": ["SQL", "Python", "Statistics", "Dashboarding", "Power BI", "KPI Design", "Reporting", "Business Requirements Gathering", "Presentation"],
            "transitions": [
                ("Business Analyst", 4, 500, 2, "Business analytics graduates can enter business analyst roles through requirements and stakeholder exposure."),
                ("Data Analyst", 4, 600, 2, "Requires data portfolio and practical analytics project evidence."),
                ("Business Intelligence Analyst", 5, 700, 2, "Requires dashboard and reporting system exposure."),
            ],
        },
    ]

    max_occ_id = conn.execute("SELECT COALESCE(MAX(occupation_id), 0) AS max_id FROM occupations").fetchone()["max_id"]
    next_occ_id = max_occ_id + 1
    max_transition_id = conn.execute("SELECT COALESCE(MAX(transition_id), 0) AS max_id FROM career_transitions").fetchone()["max_id"]
    next_transition_id = max_transition_id + 1

    skill_lookup = {row["name"]: row["skill_id"] for row in conn.execute("SELECT skill_id, name FROM skills").fetchall()}
    occupation_lookup = {row["name"]: row["occupation_id"] for row in conn.execute("SELECT occupation_id, name FROM occupations").fetchall()}

    for role in fresh_roles:
        if role["name"] not in existing_names:
            conn.execute("""
                INSERT INTO occupations (
                    occupation_id, name, sector, description, salary_min,
                    salary_median, salary_max, demand_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (next_occ_id, role["name"], role["sector"], role["description"], role["salary_min"], role["salary_median"], role["salary_max"], role["demand_score"]))
            fresh_occ_id = next_occ_id
            occupation_lookup[role["name"]] = fresh_occ_id
            next_occ_id += 1

            for skill_name in role["skills"]:
                skill_id = skill_lookup.get(skill_name)
                if skill_id is not None:
                    conn.execute("""
                        INSERT OR IGNORE INTO occupation_skills (occupation_id, skill_id, importance)
                        VALUES (?, ?, ?)
                    """, (fresh_occ_id, skill_id, 4))
        else:
            fresh_occ_id = occupation_lookup[role["name"]]

        for target_name, months, cost, difficulty, notes in role["transitions"]:
            target_id = occupation_lookup.get(target_name)
            if target_id is None:
                continue
            existing_edge = conn.execute("""
                SELECT 1 FROM career_transitions
                WHERE from_occupation_id = ? AND to_occupation_id = ?
            """, (fresh_occ_id, target_id)).fetchone()
            if existing_edge is None:
                conn.execute("""
                    INSERT INTO career_transitions (
                        transition_id, from_occupation_id, to_occupation_id,
                        transition_type, estimated_months, estimated_cost,
                        difficulty, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (next_transition_id, fresh_occ_id, target_id, "fresh_graduate_entry", months, cost, difficulty, notes))
                next_transition_id += 1
    conn.commit()


def calculate_custom_chance_score(conn, current_occupation, target_occupation, selected_skill_names, qualification):
    base_result = calculate_chance_score(conn, current_occupation, target_occupation)
    custom_skill_match = calculate_custom_skill_match(conn, selected_skill_names, target_occupation)

    weights = base_result["weights"]
    chance = (
        weights["skill_match"] * custom_skill_match
        + weights["demand"] * base_result["demand"]
        + weights["salary_feasibility"] * base_result["salary_feasibility"]
        + weights["path_difficulty"] * base_result["path_difficulty"]
    )

    requirement = get_min_qualification_for_role(target_occupation)
    meets_requirement = qualification_rank(qualification) >= qualification_rank(requirement)
    qualification_penalty = 0.0
    if not meets_requirement:
        qualification_penalty = 0.12
        chance -= qualification_penalty

    return {
        **base_result,
        "chance_score": max(0.0, min(chance, 1.0)),
        "skill_match": custom_skill_match,
        "qualification_requirement": requirement,
        "meets_qualification_requirement": meets_requirement,
        "qualification_penalty": qualification_penalty,
    }


def get_course_recommendations_df(conn, missing_skills):
    rows = []
    for skill in missing_skills:
        course = conn.execute("""
            SELECT c.title, c.provider, c.cost, c.duration_hours, c.difficulty, s.name AS skill
            FROM courses c
            JOIN skills s ON c.skill_id = s.skill_id
            WHERE s.name = ?
            ORDER BY c.cost ASC, c.duration_hours ASC
            LIMIT 1
        """, (skill["skill"],)).fetchone()
        if course:
            row = dict(course)
            row["importance"] = skill["importance"]
            rows.append(row)
    return pd.DataFrame(rows)


def get_strategy_summary(conn, start, target, strategy):
    path, score = find_best_path_by_strategy(conn, start, target, strategy)
    summary = summarize_path(start, path)
    if summary is None:
        return None
    summary["strategy_score"] = score
    return summary


def get_route_skill_gap(conn, selected_skill_names, summary):
    if summary is None:
        return []
    selected = set(selected_skill_names)
    required = {}
    for role in summary["path_names"][1:]:
        for skill in get_target_skill_rows(conn, role):
            current = required.get(skill["skill"])
            if current is None or skill["importance"] > current["importance"]:
                required[skill["skill"]] = skill
    missing = [skill for skill in required.values() if skill["skill"] not in selected]
    return sorted(missing, key=lambda x: (-x["importance"], x["skill"]))


def render_path_card(strategy_label, summary):
    if summary is None:
        st.warning(f"No route found for {strategy_label}.")
        return
    path_text = " → ".join(summary["path_names"])
    st.markdown(
        f"""
        <div class="path-card">
            <span class="route-pill">{strategy_label}</span>
            <h4>{path_text}</h4>
            <p class="small-muted">
                {summary["total_months"]} months ·
                ${summary["total_cost"]:,.0f} estimated cost ·
                avg difficulty {summary["avg_difficulty"]:.1f}/5 ·
                hardest step {summary["max_difficulty"]}/5
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_skill_gap(missing_skills):
    if not missing_skills:
        st.success("No major missing skills found based on your edited skill profile.")
        return
    for skill in missing_skills:
        st.write(f"**{skill['skill']}** · importance {skill['importance']}/5")
        st.progress(int(skill["importance"]) / 5)


def render_course_quests(courses_df, study_hours_per_week):
    if courses_df.empty:
        st.info("No course quests found yet.")
        return

    total_cost = courses_df["cost"].sum()
    total_hours = courses_df["duration_hours"].sum()
    estimated_weeks = total_hours / study_hours_per_week
    estimated_months = estimated_weeks / 4.345

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total course cost", f"${total_cost:,.0f}")
    col2.metric("Total course duration", f"{total_hours:.0f} hours")
    col3.metric("Study pace", f"{study_hours_per_week:.0f} hrs/week")
    col4.metric("Estimated study time", f"{estimated_weeks:.1f} weeks")
    st.caption(f"At this pace, the course plan is approximately {estimated_months:.1f} months of part-time study.")
    st.divider()

    for _, row in courses_df.iterrows():
        course_weeks = row["duration_hours"] / study_hours_per_week
        st.markdown(f"""
        <div class="quest-card">
            <b>{row["title"]}</b><br>
            <span class="small-muted">
                Unlocks: {row["skill"]} · Importance {row["importance"]}/5<br>
                Provider: {row["provider"]} · Cost: ${row["cost"]:,.0f} ·
                Duration: {row["duration_hours"]:.0f} hours · Difficulty: {row["difficulty"]}<br>
                Estimated completion: {course_weeks:.1f} weeks at {study_hours_per_week:.0f} hrs/week
            </span>
        </div>
        """, unsafe_allow_html=True)


def display_clean_table(df):
    clean_df = df.copy()
    if "skill_id" in clean_df.columns:
        clean_df = clean_df.drop(columns=["skill_id"])
    if "importance" in clean_df.columns:
        clean_df["importance"] = clean_df["importance"].astype(str)
    clean_df.index = range(1, len(clean_df) + 1)
    st.dataframe(clean_df, use_container_width=True)


def render_score_breakdown_chart(chance_result):
    st.markdown("### Score Breakdown")
    with st.expander("What do these scores mean?"):
        st.markdown("""
        These bars are **component scores between 0 and 100**. They are **not separate probabilities of success**.

        - **Skill match**: how much your edited skill profile overlaps with the target role's required skills, weighted by importance.
        - **Target demand**: the target role's demand score in the current dataset.
        - **Salary feasibility**: how manageable the salary jump is from the starting profile to the target role.
        - **Path support**: how manageable the easiest available career route is in the current graph.

        The final chance score combines these components using the model weights.
        """)

    breakdown_df = pd.DataFrame({
        "Component": ["Skill match", "Target demand", "Salary feasibility", "Path support"],
        "Score": [
            chance_result["skill_match"] * 100,
            chance_result["demand"] * 100,
            chance_result["salary_feasibility"] * 100,
            chance_result["path_difficulty"] * 100,
        ],
    })

    chart = (
        alt.Chart(breakdown_df)
        .mark_bar()
        .encode(
            x=alt.X("Component:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)),
            y=alt.Y("Score:Q", title="Score (0–100)", scale=alt.Scale(domain=[0, 100])),
            tooltip=[alt.Tooltip("Component:N"), alt.Tooltip("Score:Q", format=".1f")],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)


def render_demand_explanation(target_occupation, chance_result):
    st.markdown("### Demand Explanation")
    demand_report = load_demand_report()

    if demand_report.empty:
        st.info("No refined demand report found yet. Run `scripts/refine_demand_with_course_signal.py` to generate it.")
        st.metric("Target demand score", f"{chance_result['demand'] * 100:.1f}%")
        return

    row = demand_report[demand_report["name"] == target_occupation]

    if row.empty:
        st.info("No detailed demand explanation found for this role.")
        st.metric("Target demand score", f"{chance_result['demand'] * 100:.1f}%")
        return

    row = row.iloc[0]

    mom_score = float(row.get("mom_demand_score", 0))
    course_signal = float(row.get("role_course_signal", 0))
    refined_score = float(row.get("refined_demand_score", chance_result["demand"]))
    course_count = int(row.get("total_course_count", 0))
    mapped_skill_count = int(row.get("mapped_skill_count", 0))

    col1, col2, col3 = st.columns(3)
    col1.metric("Target demand score", f"{refined_score * 100:.1f}%")
    col2.metric("MOM macro demand", f"{mom_score * 100:.1f}%")
    col3.metric("Course-supply signal", f"{course_signal * 100:.1f}%")

    st.caption(
        f"The course-supply signal is based on **{course_count:,}** SkillsFuture course matches "
        f"across **{mapped_skill_count}** mapped role skills."
    )

    with st.expander("How is demand calculated?"):
        st.markdown("""
        The demand score is an explainable modelling signal, not an official prediction.

        Current formula:

        ```text
        target demand = 0.70 × MOM macro demand + 0.30 × SkillsFuture course-supply signal
        ```

        - **MOM macro demand** comes from official job-vacancy data by occupation group.
        - **Course-supply signal** uses real SkillsFuture course availability for the role's required skills.
        - The course signal helps differentiate roles that fall into the same broad MOM occupation group.
        """)


def route_comparison_table(route_summaries):
    rows = []
    for label, summary in route_summaries.items():
        if summary:
            rows.append({
                "Route": label,
                "Path": " → ".join(summary["path_names"]),
                "Months": summary["total_months"],
                "Cost": f"${summary['total_cost']:,.0f}",
                "Avg difficulty": f"{summary['avg_difficulty']:.1f}/5",
                "Hardest step": f"{summary['max_difficulty']}/5",
            })
    df = pd.DataFrame(rows)
    df.index = range(1, len(df) + 1)
    st.dataframe(df, use_container_width=True)


def render_advisor_panel(current_occupation, target_occupation, label, chance_pct, blocker_text, study_hours_per_week, study_weeks, qualification_text, skill_advice):
    st.markdown("## Advisor Summary")
    with st.container(border=True):
        st.markdown("### 📌 Recommendation Board")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Overall assessment**")
            st.write(
                f"Moving from **{current_occupation}** to **{target_occupation}** is classified as "
                f"**{label}**, with an estimated chance score of **{chance_pct:.1f}%**."
            )
            st.markdown("**Main blockers**")
            st.write(blocker_text)
            st.markdown("**Course workload**")
            st.write(
                f"At **{study_hours_per_week} hours/week**, the final-target course quests take about "
                f"**{study_weeks:.1f} weeks**."
            )
        with col2:
            st.markdown("**Qualification check**")
            st.write(qualification_text)
            st.markdown("**Recommended focus**")
            st.write(skill_advice)


conn = get_connection()
add_fresh_grad_nodes_to_db(conn)

occupations_df = load_occupations(conn)
all_skills_df = load_all_skills(conn)
all_skill_names = all_skills_df["name"].tolist()

st.title("🧭 CareerQuest SG — Workforce Mobility Simulator")
st.subheader("An explainable tool for exploring career transitions, skill gaps, and workforce pathways")
st.markdown("This prototype estimates career transition feasibility, compares pathways, and recommends skill-building quests.")

with st.sidebar:
    st.header("User Profile")
    education = st.selectbox(
        "Highest qualification",
        ["Secondary", "ITE / Nitec", "Diploma", "Bachelor's Degree", "Master's Degree", "Other"],
        index=3,
        help="Used to check whether you meet the target role's minimum qualification requirement.",
    )
    study_hours_per_week = st.slider(
        "Study hours available per week",
        min_value=1,
        max_value=25,
        value=6,
        step=1,
        help="Used to estimate how long the recommended course quests will take.",
    )

    occupation_names = occupations_df["name"].tolist()
    non_fresh_roles = [role for role in occupation_names if not role.startswith("Fresh Graduate")]

    current_occupation = st.selectbox(
        "Current / starting profile",
        occupation_names,
        index=occupation_names.index("Fresh Graduate — Data Science Bachelor's")
        if "Fresh Graduate — Data Science Bachelor's" in occupation_names
        else occupation_names.index("Administrative Executive"),
    )

    target_occupation = st.selectbox(
        "Target occupation",
        non_fresh_roles,
        index=non_fresh_roles.index("Data Analyst"),
    )

    st.caption("V1 uses seeded public-sector-style sample data for demonstration.")

    st.sidebar.header("Quick Demo Scenarios")

    demo_choice = st.sidebar.radio(
        "Try an example:",
        [
            "Custom",
            "Admin → Data Analyst",
            "Fresh Grad → Data Scientist",
            "HR → Supply Chain Analyst",
        ]
    )
    if demo_choice == "Admin → Data Analyst":
        current_occupation = "Administrative Executive"
        target_occupation = "Data Analyst"
        selected_skills = get_default_skill_names(conn, current_occupation)

    elif demo_choice == "Fresh Grad → Data Scientist":
        current_occupation = "Fresh Graduate — Data Science Bachelor's"
        target_occupation = "Junior Data Scientist"
        selected_skills = get_default_skill_names(conn, current_occupation)

    elif demo_choice == "HR → Supply Chain Analyst":
        current_occupation = "HR Executive"
        target_occupation = "Supply Chain Analyst"
        selected_skills = get_default_skill_names(conn, current_occupation)


st.divider()

main_tab, about_tab = st.tabs(["Career Simulator", "About This Model"])
with main_tab:
    st.markdown("## Editable Skill Profile")
    st.caption("Default skills are pre-selected based on your starting profile. You can remove skills you do not have and add extra skills you already possess.")

    default_skills = get_default_skill_names(conn, current_occupation)

    selected_skills = st.multiselect(
        "Your current skills",
        options=all_skill_names,
        default=[skill for skill in default_skills if skill in all_skill_names],
    )

    if not selected_skills:
        st.warning("Please select at least one current skill for a meaningful analysis.")

    if current_occupation == target_occupation:
        st.info("Current occupation and target occupation are the same. Choose a different target role.")
        st.stop()

    chance_result = calculate_custom_chance_score(conn, current_occupation, target_occupation, selected_skills, education)
    chance_pct = chance_result["chance_score"] * 100
    label = score_to_label(chance_result["chance_score"])
    missing_skills = get_missing_skills_from_selected(conn, selected_skills, target_occupation)

    left, right = st.columns([1, 2])

    with left:
        st.markdown("### Chance Score")
        st.metric("Estimated transition chance", f"{chance_pct:.1f}%")
        st.write(f"**Label:** {label}")
        st.progress(chance_result["chance_score"])
        requirement = chance_result["qualification_requirement"]
        if chance_result["meets_qualification_requirement"]:
            st.success(f"Qualification check: meets minimum requirement ({requirement}).")
        else:
            st.warning(
                f"Qualification check: target role usually requires at least {requirement}. "
                f"A requirement penalty of {chance_result['qualification_penalty'] * 100:.0f}% was applied."
            )

    with right:
        render_score_breakdown_chart(chance_result)
        st.caption("Qualification is treated as a requirement gate, not as a bonus for having a higher degree.")

    st.divider()
    render_demand_explanation(target_occupation, chance_result)


    st.divider()

    tab1, tab2, tab3 = st.tabs(["Target Skill Gap", "Target Course Quests", "Role Details"])

    with tab1:
        st.markdown(f"### Missing skills for final target: {target_occupation}")
        render_skill_gap(missing_skills)

    with tab2:
        st.markdown("### Recommended course quests for final target")
        target_courses_df = get_course_recommendations_df(conn, missing_skills)
        render_course_quests(target_courses_df, study_hours_per_week)

    with tab3:
        st.markdown("### Target role skill requirements")
        display_clean_table(get_required_skills_df(conn, target_occupation))

    top_blockers = missing_skills[:5]
    blocker_text = ", ".join([skill["skill"] for skill in top_blockers]) if top_blockers else "None"

    if chance_result["skill_match"] < 0.4:
        skill_advice = "Your current edited skill profile has a large skill gap. Focus on foundational target-role skills first."
    elif chance_result["skill_match"] < 0.7:
        skill_advice = "You already have some transferable skills. Focus on closing the highest-importance gaps."
    else:
        skill_advice = "Your edited skill profile is close to the target role. Focus on portfolio evidence and applications."

    total_hours = target_courses_df["duration_hours"].sum() if not target_courses_df.empty else 0
    study_weeks = total_hours / study_hours_per_week if study_hours_per_week else 0

    qualification_text = (
        f"You meet the current minimum qualification assumption for **{target_occupation}**."
        if chance_result["meets_qualification_requirement"]
        else f"The target role is currently assumed to require at least **{chance_result['qualification_requirement']}**, so qualification is a possible barrier."
    )

    st.divider()
    render_advisor_panel(
        current_occupation=current_occupation,
        target_occupation=target_occupation,
        label=label,
        chance_pct=chance_pct,
        blocker_text=blocker_text,
        study_hours_per_week=study_hours_per_week,
        study_weeks=study_weeks,
        qualification_text=qualification_text,
        skill_advice=skill_advice,
    )


    st.divider()
    st.markdown("## Career Path Strategy Comparison")

    strategy_map = {
        "Fastest route": "fastest",
        "Cheapest route": "cheapest",
        "Easiest route": "easiest",
        "Balanced route": "balanced",
    }

    route_summaries = {
        label_name: get_strategy_summary(conn, current_occupation, target_occupation, strategy_key)
        for label_name, strategy_key in strategy_map.items()
    }

    cols = st.columns(2)
    for i, (label_name, summary) in enumerate(route_summaries.items()):
        with cols[i % 2]:
            render_path_card(label_name, summary)

    st.markdown("### Route comparison table")
    route_comparison_table(route_summaries)

    st.markdown("### Interactive career graph")
    with st.expander("Open career graph", expanded=True):
        render_interactive_career_graph(
            conn,
            current_occupation=current_occupation,
            target_occupation=target_occupation,
            route_summaries=route_summaries,)

    st.markdown("### Route-specific course quest comparison")
    selected_routes = st.multiselect(
        "Select routes to compare",
        options=list(route_summaries.keys()),
        default=["Fastest route", "Easiest route"],
    )

    if selected_routes:
        route_tabs = st.tabs(selected_routes)
        for tab, route_name in zip(route_tabs, selected_routes):
            with tab:
                summary = route_summaries.get(route_name)
                if summary is None:
                    st.info("No route found.")
                else:
                    st.markdown(f"#### {route_name}")
                    st.write(f"**Path:** {' → '.join(summary['path_names'])}")
                    route_missing_skills = get_route_skill_gap(conn, selected_skills, summary)
                    st.write(f"**Route-specific missing skills:** {len(route_missing_skills)}")
                    if route_missing_skills:
                        st.caption("These are missing skills required by roles along this route, not only the final target role.")
                        courses_df = get_course_recommendations_df(conn, route_missing_skills)
                        render_course_quests(courses_df, study_hours_per_week)
                    else:
                        st.success("Your edited skill profile covers the major skill requirements along this route.")
    else:
        st.info("Select at least one route to compare course quests.")

    st.caption("Note: This is an explainable prototype model for portfolio demonstration, not an official labour-market prediction tool.")

with about_tab:
    st.title("About CareerQuest SG")

    st.markdown("""
### What this tool does

CareerQuest SG helps you explore **career transitions in a structured way**.

Instead of guessing what to do next, it:
- estimates how feasible a career move is
- shows possible paths to get there
- highlights the skills you are missing
- suggests real courses you can take

---

### How the scoring works

The “chance score” is **not a probability**, but a structured indicator combining:

- **Skill match** → how close your current skills are to the target role  
- **Target demand** → how in-demand the role is (based on MOM data)  
- **Path feasibility** → how difficult the transition path is  
- **Salary feasibility** → how big the jump is  

---

### Data sources

- MOM job vacancy dataset (data.gov.sg) → labour demand  
- SkillsFuture course directory → training pathways  
- Custom career transition graph → pathway modelling  

---

### Limitations (important)

This is a **decision-support prototype**, not a prediction model.

It does NOT account for:
- personal experience / internships
- interview performance
- company-specific hiring criteria
- real-time hiring trends

Course availability is used as a **proxy signal**, not actual demand.

---

### Why this exists

This project explores how data can be used to make career decisions more transparent, structured, and explainable.
""")
    
    st.markdown("""
## Who this tool is useful for

### 🧑‍🎓 Fresh graduates
- “What roles can I realistically enter?”
- “What should I learn first?”

---

### 🔄 Career switchers
- “Can I move from HR → Data?”
- “How long will it take?”

---

### 🏛 Workforce / policy perspective
- Identify skill gaps across roles  
- Understand realistic transition pathways  
- Explore training needs  

---

### 🧠 Personal planning
- Compare multiple career strategies  
- See cost vs time trade-offs  
- Build a structured learning plan  
""")