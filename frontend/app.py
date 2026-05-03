
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
DB_PATH = ROOT_DIR / "careerquest_seed.sqlite"

sys.path.append(str(SCRIPTS_DIR))

from strategy_modes import find_best_path_by_strategy, summarize_path
from chance_scoring import (
    calculate_chance_score,
    score_to_label,
    get_missing_high_importance_skills,
)
from load_seed_data import init_db


st.set_page_config(
    page_title="CareerQuest SG",
    page_icon="🧭",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main {
        background-color: #f7f9fc;
    }
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
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def initialize_database():
    init_db()
    return True


def get_connection():
    initialize_database()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def load_occupations(conn):
    rows = conn.execute(
        "SELECT name, sector, salary_median, demand_score FROM occupations ORDER BY sector, name"
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def get_required_skills_df(conn, occupation_name):
    rows = conn.execute(
        """
        SELECT
            s.name AS skill,
            s.category,
            os.importance
        FROM occupation_skills os
        JOIN occupations o ON os.occupation_id = o.occupation_id
        JOIN skills s ON os.skill_id = s.skill_id
        WHERE o.name = ?
        ORDER BY os.importance DESC, s.name ASC
        """,
        (occupation_name,),
    ).fetchall()

    return pd.DataFrame([dict(row) for row in rows])


def get_course_recommendations_df(conn, current_occupation, target_occupation):
    missing_skills = get_missing_high_importance_skills(
        conn,
        current_occupation,
        target_occupation,
    )

    rows = []
    for skill in missing_skills:
        course = conn.execute(
            """
            SELECT
                c.title,
                c.provider,
                c.cost,
                c.duration_hours,
                c.difficulty,
                s.name AS skill
            FROM courses c
            JOIN skills s ON c.skill_id = s.skill_id
            WHERE c.skill_id = ?
            ORDER BY c.cost ASC, c.duration_hours ASC
            LIMIT 1
            """,
            (skill["skill_id"],),
        ).fetchone()

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


def render_path_card(strategy_label, summary):
    if summary is None:
        st.warning(f"No route found for {strategy_label}.")
        return

    path_text = " → ".join(summary["path_names"])

    st.markdown(
        f"""
        <div class="path-card">
            <h4>{strategy_label}</h4>
            <p><b>{path_text}</b></p>
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


def render_skill_gap(conn, current_occupation, target_occupation):
    missing_skills = get_missing_high_importance_skills(
        conn,
        current_occupation,
        target_occupation,
    )

    if not missing_skills:
        st.success("No major missing skills found based on the current V1 mapping.")
        return

    for skill in missing_skills:
        progress_value = int(skill["importance"]) / 5
        st.write(f"**{skill['skill']}** · importance {skill['importance']}/5")
        st.progress(progress_value)


def render_course_quests(courses_df):
    if courses_df.empty:
        st.info("No course quests found yet.")
        return

    total_cost = courses_df["cost"].sum()
    total_hours = courses_df["duration_hours"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total course cost", f"${total_cost:,.0f}")
    col2.metric("Total course duration", f"{total_hours:.0f} hours")
    col3.metric("Part-time study estimate", f"{total_hours / 6:.1f} weeks")

    st.divider()

    for _, row in courses_df.iterrows():
        st.markdown(
            f"""
            <div class="quest-card">
                <b>{row["title"]}</b><br>
                <span class="small-muted">
                    Unlocks: {row["skill"]} · Importance {row["importance"]}/5<br>
                    Provider: {row["provider"]} · Cost: ${row["cost"]:,.0f} · 
                    Duration: {row["duration_hours"]:.0f} hours · Difficulty: {row["difficulty"]}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )


conn = get_connection()
occupations_df = load_occupations(conn)

st.title("🧭 CareerQuest SG")
st.subheader("A workforce mobility and career pathway simulator")

st.markdown(
    """
    This prototype estimates career transition feasibility, compares possible pathways,
    and recommends skill-building “quests” using a graph-based career engine.
    """
)

with st.sidebar:
    st.header("User Profile")

    age = st.number_input("Age", min_value=16, max_value=70, value=27, step=1)
    education = st.selectbox(
        "Highest qualification",
        [
            "Secondary",
            "ITE / Nitec",
            "Diploma",
            "Bachelor's Degree",
            "Master's Degree",
            "Other",
        ],
        index=3,
    )

    occupation_names = occupations_df["name"].tolist()

    current_occupation = st.selectbox(
        "Current occupation",
        occupation_names,
        index=occupation_names.index("Administrative Executive"),
    )

    target_occupation = st.selectbox(
        "Target occupation",
        occupation_names,
        index=occupation_names.index("Data Analyst"),
    )

    strategy_preference = st.selectbox(
        "Preferred planning style",
        ["Balanced", "Fastest", "Cheapest", "Easiest"],
    )

    st.caption("V1 uses seeded public-sector-style sample data for demonstration.")


if current_occupation == target_occupation:
    st.info("Current occupation and target occupation are the same. Choose a different target role.")
    st.stop()


chance_result = calculate_chance_score(conn, current_occupation, target_occupation)
chance_pct = chance_result["chance_score"] * 100
label = score_to_label(chance_result["chance_score"])

st.divider()

left, right = st.columns([1, 2])

with left:
    st.markdown("### Chance Score")
    st.metric("Estimated transition chance", f"{chance_pct:.1f}%")
    st.write(f"**Label:** {label}")
    st.progress(chance_result["chance_score"])

with right:
    st.markdown("### Score Breakdown")

    breakdown_df = pd.DataFrame(
        {
            "Component": [
                "Skill match",
                "Target-role demand",
                "Salary feasibility",
                "Path difficulty support",
            ],
            "Score": [
                chance_result["skill_match"],
                chance_result["demand"],
                chance_result["salary_feasibility"],
                chance_result["path_difficulty"],
            ],
        }
    )

    st.bar_chart(
        breakdown_df.set_index("Component"),
        height=250,
    )


st.divider()
st.markdown("## Career Path Strategy Comparison")

strategy_map = {
    "Fastest route": "fastest",
    "Cheapest route": "cheapest",
    "Easiest route": "easiest",
    "Balanced route": "balanced",
}

cols = st.columns(2)
for i, (label_name, strategy_key) in enumerate(strategy_map.items()):
    with cols[i % 2]:
        summary = get_strategy_summary(
            conn,
            current_occupation,
            target_occupation,
            strategy_key,
        )
        render_path_card(label_name, summary)


st.divider()

tab1, tab2, tab3 = st.tabs(
    [
        "Skill Gap",
        "Course Quests",
        "Role Details",
    ]
)

with tab1:
    st.markdown(f"### Missing skills for {target_occupation}")
    render_skill_gap(conn, current_occupation, target_occupation)

with tab2:
    st.markdown("### Recommended course quests")
    courses_df = get_course_recommendations_df(
        conn,
        current_occupation,
        target_occupation,
    )
    render_course_quests(courses_df)

with tab3:
    st.markdown("### Target role skill requirements")
    target_skills_df = get_required_skills_df(conn, target_occupation)
    st.dataframe(target_skills_df, use_container_width=True)

    st.markdown("### Current role skill profile")
    current_skills_df = get_required_skills_df(conn, current_occupation)
    st.dataframe(current_skills_df, use_container_width=True)


st.divider()
st.markdown("## Advisor Summary")

top_blockers = get_missing_high_importance_skills(
    conn,
    current_occupation,
    target_occupation,
)[:5]

blocker_text = ", ".join([skill["skill"] for skill in top_blockers])

if chance_result["skill_match"] < 0.4:
    skill_advice = "Your current profile has a large skill gap. Focus on foundational technical skills first."
elif chance_result["skill_match"] < 0.7:
    skill_advice = "You already have some transferable skills. Focus on closing the highest-importance gaps."
else:
    skill_advice = "Your skill profile is close to the target role. Focus on portfolio evidence and applications."

st.write(
    f"""
    Based on the current V1 model, moving from **{current_occupation}** to
    **{target_occupation}** is classified as **{label}** with an estimated
    chance score of **{chance_pct:.1f}%**.

    The main blockers are: **{blocker_text}**.

    {skill_advice}
    """
)

st.caption(
    "Note: This is an explainable prototype model for portfolio demonstration, "
    "not an official labour-market prediction tool."
)
