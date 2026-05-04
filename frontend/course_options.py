
from __future__ import annotations

import hashlib
import pandas as pd
import streamlit as st

DIFFICULTY_ORDER = {
    "Beginner": 1,
    "Intermediate": 2,
    "Advanced": 3,
    "Unspecified": 4,
    "": 4,
    None: 4,
}


def _difficulty_rank(value):
    return DIFFICULTY_ORDER.get(value, 4)


def _course_key(skill_name: str, title: str, provider: str) -> str:
    raw = f"{skill_name}|{title}|{provider}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def init_selected_courses_state():
    if "selected_courses" not in st.session_state:
        st.session_state.selected_courses = {}


def add_selected_course(skill_name: str, row: dict):
    init_selected_courses_state()

    key = _course_key(
        skill_name,
        str(row.get("title", "")),
        str(row.get("provider", "")),
    )

    st.session_state.selected_courses[key] = {
        "skill": skill_name,
        "title": row.get("title", "Untitled course"),
        "provider": row.get("provider", "Unknown provider"),
        "cost": row.get("cost"),
        "duration_hours": row.get("duration_hours"),
        "difficulty": row.get("difficulty", "Unspecified"),
    }


def remove_selected_course(key: str):
    init_selected_courses_state()
    st.session_state.selected_courses.pop(key, None)


def clear_selected_courses():
    st.session_state.selected_courses = {}


def get_selected_courses_df() -> pd.DataFrame:
    init_selected_courses_state()
    rows = []
    for key, value in st.session_state.selected_courses.items():
        row = dict(value)
        row["selection_key"] = key
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce")
    df["duration_hours"] = pd.to_numeric(df["duration_hours"], errors="coerce")
    return df


def render_selected_plan_summary(study_hours_per_week: float, context_key="default"):
    st.markdown("### Your Selected Course Plan")
    selected_df = get_selected_courses_df()

    if selected_df.empty:
        st.info("No courses selected yet. Choose courses below to build your plan.")
        return

    total_cost = selected_df["cost"].sum(skipna=True)
    total_hours = selected_df["duration_hours"].sum(skipna=True)
    estimated_weeks = total_hours / study_hours_per_week if study_hours_per_week else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Selected courses", f"{len(selected_df)}")
    col2.metric("Skills covered", f"{selected_df['skill'].nunique()}")
    col3.metric("Total cost", f"${total_cost:,.0f}")
    col4.metric("Study time", f"{estimated_weeks:.1f} weeks")

    st.caption(f"Total selected duration: {total_hours:.0f} hours at {study_hours_per_week:.0f} hours/week.")

    display_df = selected_df[["skill", "title", "provider", "cost", "duration_hours", "difficulty"]].copy()
    display_df = display_df.rename(columns={
        "skill": "Skill",
        "title": "Course",
        "provider": "Provider",
        "cost": "Cost",
        "duration_hours": "Duration (hours)",
        "difficulty": "Difficulty",
    })
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(display_df, use_container_width=True, height=260)

    with st.expander("Remove selected courses"):
        for idx, (key, row) in enumerate(st.session_state.selected_courses.items()):
            col_a, col_b = st.columns([5, 1])
            with col_a:
                st.write(f"**{row['skill']}** · {row['title']} · {row['provider']}")
            with col_b:
                ui_key = f"{context_key}_{idx}_{key}"
                if st.button("Remove", key=f"remove_{ui_key}"):
                    remove_selected_course(key)
                    st.rerun()

    if st.button("Clear selected plan", key=f"clear_selected_plan_{context_key}"):
        clear_selected_courses()
        st.rerun()


def get_courses_for_skill(conn, skill_name: str) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT c.title, c.provider, c.cost, c.duration_hours, c.difficulty, s.name AS skill
        FROM courses c
        JOIN skills s ON c.skill_id = s.skill_id
        WHERE s.name = ?
        """,
        (skill_name,),
    ).fetchall()

    df = pd.DataFrame([dict(row) for row in rows])
    if df.empty:
        return df

    df["cost"] = pd.to_numeric(df["cost"], errors="coerce")
    df["duration_hours"] = pd.to_numeric(df["duration_hours"], errors="coerce")
    df["provider"] = df["provider"].fillna("Unknown provider")
    df["difficulty"] = df["difficulty"].fillna("Unspecified")
    df["difficulty_rank"] = df["difficulty"].map(_difficulty_rank).fillna(4)
    df = df[df["title"].notna() & (df["title"].astype(str).str.strip() != "")]
    return df.reset_index(drop=True)


def filter_and_sort_courses(df, sort_by, max_cost, max_duration, difficulties, provider_keyword):
    if df.empty:
        return df

    filtered = df.copy()

    if max_cost is not None:
        filtered = filtered[(filtered["cost"].isna()) | (filtered["cost"] <= max_cost)]

    if max_duration is not None:
        filtered = filtered[(filtered["duration_hours"].isna()) | (filtered["duration_hours"] <= max_duration)]

    if difficulties:
        filtered = filtered[filtered["difficulty"].isin(difficulties)]

    if provider_keyword.strip():
        keyword = provider_keyword.strip().lower()
        filtered = filtered[filtered["provider"].astype(str).str.lower().str.contains(keyword, na=False)]

    if sort_by == "Lowest cost":
        sort_cols = ["cost", "duration_hours", "difficulty_rank"]
    elif sort_by == "Shortest duration":
        sort_cols = ["duration_hours", "cost", "difficulty_rank"]
    elif sort_by == "Easiest first":
        sort_cols = ["difficulty_rank", "cost", "duration_hours"]
    elif sort_by == "Provider A-Z":
        sort_cols = ["provider", "cost", "duration_hours"]
    elif sort_by == "Course title A-Z":
        sort_cols = ["title", "cost", "duration_hours"]
    else:
        sort_cols = ["difficulty_rank", "cost", "duration_hours"]

    return filtered.sort_values(sort_cols, na_position="last").reset_index(drop=True)


def render_course_card(row, study_hours_per_week: float, skill_name: str, rank: int | None = None, context_key="default",):
    init_selected_courses_state()
    title = row.get("title", "Untitled course")
    provider = row.get("provider", "Unknown provider")
    base_key = _course_key(skill_name, str(title), str(provider))
    ui_key = f"{context_key}_{base_key}"

    cost = row.get("cost")
    duration = row.get("duration_hours")
    cost_text = "Not listed" if pd.isna(cost) else f"${cost:,.0f}"
    duration_text = "Not listed" if pd.isna(duration) else f"{duration:.0f} hours"
    completion_text = "Estimated completion unavailable" if pd.isna(duration) else f"{duration / study_hours_per_week:.1f} weeks at {study_hours_per_week:.0f} hrs/week"
    prefix = f"{rank}. " if rank else ""

    st.markdown(
        f"""
        <div class="quest-card">
            <b>{prefix}{title}</b><br>
            <span class="small-muted">
                Provider: {provider}<br>
                Cost: {cost_text} · Duration: {duration_text} · Difficulty: {row.get("difficulty", "Unspecified")}<br>
                {completion_text}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if base_key in st.session_state.selected_courses:
        st.button("Selected ✓", key=f"selected_{ui_key}", disabled=True)
    else:
        if st.button("Select this course", key=f"select_{ui_key}"):
            add_selected_course(
                skill_name,
                row.to_dict() if hasattr(row, "to_dict") else dict(row)
            )
            st.rerun()


def render_skill_course_options(conn, skill, study_hours_per_week, top_n, sort_by, max_cost, max_duration, difficulties, provider_keyword, compact=False, context_key="default",):
    skill_name = skill["skill"]
    importance = skill.get("importance", "?")
    all_courses = get_courses_for_skill(conn, skill_name)
    filtered = filter_and_sort_courses(all_courses, sort_by, max_cost, max_duration, difficulties, provider_keyword)

    st.markdown(f"#### {skill_name} · importance {importance}/5")

    if all_courses.empty:
        st.info("No real course options found for this skill yet.")
        return

    st.caption(f"{len(filtered):,} matching options after filters · {len(all_courses):,} total options for this skill")

    if filtered.empty:
        st.warning("No courses match the current filters.")
        return

    for i, (_, row) in enumerate(filtered.head(top_n).iterrows(), start=1):
        render_course_card(row, study_hours_per_week, skill_name=skill_name, rank=i, context_key=context_key)

    if len(filtered) > top_n:
        with st.expander(f"See full list for {skill_name} ({len(filtered):,} courses)"):
            display_df = filtered[["title", "provider", "cost", "duration_hours", "difficulty"]].copy()
            display_df = display_df.rename(columns={
                "title": "Course",
                "provider": "Provider",
                "cost": "Cost",
                "duration_hours": "Duration (hours)",
                "difficulty": "Difficulty",
            })
            display_df.index = range(1, len(display_df) + 1)
            st.dataframe(display_df, use_container_width=True, height=360 if not compact else 260)
            st.caption("To select from the full list, sort/filter until your preferred course appears in the top options.")


def render_course_options_explorer(conn, missing_skills, study_hours_per_week, title="Recommended course options", compact=False, show_selected_plan=True, context_key="default",):
    init_selected_courses_state()
    st.markdown(f"### {title}")

    if show_selected_plan and context_key == "global":
        render_selected_plan_summary(study_hours_per_week, context_key=context_key)
        st.divider()

    if not missing_skills:
        st.success("No missing skills found, so no course quests are needed.")
        return

    with st.expander("Course filters and sorting", expanded=not compact):
        col1, col2, col3 = st.columns(3)

        with col1:
            top_n = st.slider("Top courses per skill", 3, 5, 3, key=f"top_n_{title}")
            sort_by = st.selectbox(
                "Sort course options by",
                ["Balanced recommendation", "Lowest cost", "Shortest duration", "Easiest first", "Provider A-Z", "Course title A-Z"],
                key=f"sort_by_{title}",
            )

        with col2:
            max_cost = None
            if st.checkbox("Set max cost", value=False, key=f"max_cost_enabled_{title}"):
                max_cost = st.number_input("Maximum cost", min_value=0.0, value=500.0, step=50.0, key=f"max_cost_{title}")

            max_duration = None
            if st.checkbox("Set max duration", value=False, key=f"max_duration_enabled_{title}"):
                max_duration = st.number_input("Maximum duration in hours", min_value=1.0, value=40.0, step=1.0, key=f"max_duration_{title}")

        with col3:
            difficulties = st.multiselect("Difficulty", ["Beginner", "Intermediate", "Advanced", "Unspecified"], default=[], key=f"difficulty_{title}")
            provider_keyword = st.text_input("Provider contains", value="", key=f"provider_keyword_{title}")

    st.caption("The course list uses real SkillsFuture course data. The default recommendation favours easier, lower-cost, shorter courses.")

    top_rows = []
    for skill in missing_skills:
        df = get_courses_for_skill(conn, skill["skill"])
        filtered = filter_and_sort_courses(df, sort_by, max_cost, max_duration, difficulties, provider_keyword)
        if not filtered.empty:
            top_rows.append(filtered.iloc[0].to_dict())

    if top_rows:
        top_df = pd.DataFrame(top_rows)
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Skills with course options", f"{len(top_df)}/{len(missing_skills)}")
        col_b.metric("Cost of top-option plan", f"${top_df['cost'].sum(skipna=True):,.0f}")
        col_c.metric("Duration of top-option plan", f"{top_df['duration_hours'].sum(skipna=True):.0f} hours")

    st.divider()

    if missing_skills:
        skill_names = [s["skill"] for s in missing_skills]
        skill_tabs = st.tabs(skill_names)
        missing_skills = sorted(
            missing_skills,
            key=lambda x: x.get("importance", 0),
            reverse=True
        )

        for tab, skill in zip(skill_tabs, missing_skills):
            with tab:
                render_skill_course_options(
                    conn=conn,
                    skill=skill,
                    study_hours_per_week=study_hours_per_week,
                    top_n=top_n,
                    sort_by=sort_by,
                    max_cost=max_cost,
                    max_duration=max_duration,
                    difficulties=difficulties,
                    provider_keyword=provider_keyword,
                    compact=compact,
                    context_key=context_key,
                )
