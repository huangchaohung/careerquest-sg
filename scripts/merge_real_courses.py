from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict, List

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

SKILLS_PATH = RAW_DIR / "skills.csv"
EXISTING_COURSES_PATH = RAW_DIR / "courses.csv"
BACKUP_COURSES_PATH = RAW_DIR / "courses_seed_backup.csv"
REAL_COURSES_PATH = PROCESSED_DIR / "courses_real.csv"
MERGED_COURSES_PATH = RAW_DIR / "courses.csv"
MERGE_REPORT_PATH = PROCESSED_DIR / "courses_merge_report.csv"
DROPPED_REVIEW_PATH = PROCESSED_DIR / "courses_dropped_review.csv"

MAX_COURSES_PER_SKILL = 25
MIN_DURATION_HOURS = 1
MAX_DURATION_HOURS = 500
MAX_COST = 20000

# Stricter relevance patterns used at merge time.
# These reduce obvious false positives from broad substring matching.
# Patterns are checked against title + description_preview.
RELEVANCE_PATTERNS: Dict[str, List[str]] = {
    "SQL": [r"\bsql\b", r"structured query", r"database query"],
    "Python": [r"\bpython\b", r"\bpandas\b", r"\bnumpy\b"],
    "Statistics": [r"\bstatistics\b", r"\bstatistical\b", r"data analysis"],
    "Data Cleaning": [r"data cleaning", r"data preparation", r"data wrangling", r"data quality"],
    "Data Visualization": [r"data visuali[sz]ation", r"visual analytics", r"storytelling with data"],
    "Dashboarding": [r"\bdashboard\b", r"dashboarding", r"business dashboard"],
    "Power BI": [r"power\s*bi", r"microsoft power bi"],
    "Tableau": [r"\btableau\b"],
    "Machine Learning Basics": [r"machine learning", r"artificial intelligence", r"predictive analytics", r"deep learning", r"neural network"],
    "Predictive Modelling": [r"predictive modell?ing", r"forecasting model", r"machine learning"],
    "ETL": [r"\betl\b", r"data pipeline", r"data engineering"],
    "Database Design": [r"database design", r"relational database"],
    "Data Warehousing": [r"data warehouse", r"data warehousing"],
    "APIs": [r"\bapi\b", r"\bapis\b", r"application programming interface"],
    "Git": [r"\bgit\b", r"\bgithub\b", r"version control"],
    "Cloud Basics": [r"\bcloud\b", r"\baws\b", r"\bazure\b", r"google cloud"],
    "Business Requirements Gathering": [r"business analysis", r"requirements gathering", r"requirements analysis"],
    "Stakeholder Management": [r"stakeholder management", r"stakeholder engagement"],
    "Process Mapping": [r"process mapping", r"business process", r"\bbpmn\b"],
    "KPI Design": [r"\bkpi\b", r"performance indicator", r"performance measurement"],
    "Reporting": [r"business reporting", r"management reporting", r"report writing"],
    "Project Management": [r"project management", r"\bscrum\b", r"\bagile\b"],
    "HRIS": [r"\bhris\b", r"human resource information system"],
    "Workforce Planning": [r"workforce planning", r"manpower planning"],
    "Employee Engagement Analysis": [r"employee engagement", r"people analytics"],
    "Training Needs Analysis": [r"training needs", r"learning needs"],
    "Labour Market Research": [r"labou?r market", r"workforce analytics"],
    "Compensation Analysis": [r"compensation", r"salary analysis", r"payroll analytics"],
    "Financial Reporting": [r"financial reporting", r"financial analysis"],
    "Budget Tracking": [r"\bbudget\b", r"budgeting"],
    "Procurement": [r"procurement", r"sourcing"],
    "Vendor Management": [r"vendor management", r"supplier management"],
    "Inventory Management": [r"inventory management"],
    "Demand Forecasting": [r"demand forecasting", r"\bforecasting\b"],
    "Supply Chain Coordination": [r"supply chain", r"logistics"],
    "Lean Six Sigma Basics": [r"lean six sigma", r"six sigma", r"process improvement"],
    "Communication": [r"business communication", r"workplace communication", r"professional communication"],
    "Presentation": [r"\bpresentation\b", r"presenting", r"storytelling"],
    "Critical Thinking": [r"critical thinking", r"problem solving"],
}

DIFFICULTY_ORDER = {
    "Beginner": 1,
    "Unspecified": 2,
    "Intermediate": 3,
    "Advanced": 4,
}


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_number(value, default: float) -> float:
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def relevance_score(row: pd.Series) -> int:
    skill = normalize_text(row.get("mapped_skill"))
    title = normalize_text(row.get("title"))
    description = normalize_text(row.get("description_preview"))
    combined = f"{title} {description}".lower()
    title_lower = title.lower()

    patterns = RELEVANCE_PATTERNS.get(skill, [])
    if not patterns:
        return 1

    score = 0
    for pattern in patterns:
        if re.search(pattern, title_lower, flags=re.IGNORECASE):
            score += 3
        elif re.search(pattern, combined, flags=re.IGNORECASE):
            score += 1

    return score


def quality_rank(row: pd.Series) -> float:
    """Lower is better."""
    relevance = row["relevance_score"]
    duration = parse_number(row.get("duration_hours"), 9999)
    cost = parse_number(row.get("cost"), 999999)
    difficulty = normalize_text(row.get("difficulty")) or "Unspecified"
    difficulty_rank = DIFFICULTY_ORDER.get(difficulty, 2)

    # Prefer relevant, shorter/moderate, lower-cost, beginner-friendly courses.
    return (
        -10 * relevance
        + 0.015 * cost
        + 0.08 * duration
        + 0.5 * difficulty_rank
    )


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not SKILLS_PATH.exists():
        raise FileNotFoundError(f"Missing skills file: {SKILLS_PATH}")
    if not REAL_COURSES_PATH.exists():
        raise FileNotFoundError(f"Missing real courses file: {REAL_COURSES_PATH}")

    skills = pd.read_csv(SKILLS_PATH)
    real_courses = pd.read_csv(REAL_COURSES_PATH)

    return skills, real_courses


def build_merged_courses(skills: pd.DataFrame, real_courses: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required_cols = {"title", "provider", "mapped_skill", "cost", "duration_hours", "difficulty", "source_url"}
    missing_cols = required_cols - set(real_courses.columns)
    if missing_cols:
        raise ValueError(f"courses_real.csv missing columns: {missing_cols}")

    skill_lookup = dict(zip(skills["name"], skills["skill_id"]))

    df = real_courses.copy()
    df["title"] = df["title"].map(normalize_text)
    df["provider"] = df["provider"].map(normalize_text)
    df["mapped_skill"] = df["mapped_skill"].map(normalize_text)
    df["difficulty"] = df["difficulty"].fillna("Unspecified").map(normalize_text)
    df["source_url"] = df["source_url"].fillna("").map(normalize_text)
    df["cost"] = df["cost"].apply(lambda x: parse_number(x, 0.0))
    df["duration_hours"] = df["duration_hours"].apply(lambda x: parse_number(x, 0.0))

    df["skill_id"] = df["mapped_skill"].map(skill_lookup)
    df["relevance_score"] = df.apply(relevance_score, axis=1)

    base_mask = (
        df["skill_id"].notna()
        & (df["title"].str.len() > 0)
        & (df["provider"].str.len() > 0)
        & (df["duration_hours"] >= MIN_DURATION_HOURS)
        & (df["duration_hours"] <= MAX_DURATION_HOURS)
        & (df["cost"] >= 0)
        & (df["cost"] <= MAX_COST)
        & (df["relevance_score"] > 0)
    )

    kept = df[base_mask].copy()
    dropped = df[~base_mask].copy()

    if kept.empty:
        raise ValueError("No real courses survived the merge filters. Loosen relevance filters or inspect courses_real.csv.")

    kept["quality_rank"] = kept.apply(quality_rank, axis=1)
    kept = kept.sort_values(["mapped_skill", "quality_rank", "title"])

    capped = (
        kept.groupby("mapped_skill", group_keys=False)
        .head(MAX_COURSES_PER_SKILL)
        .copy()
    )

    capped = capped.sort_values(["mapped_skill", "quality_rank", "title"]).reset_index(drop=True)
    capped.insert(0, "new_course_id", range(1, len(capped) + 1))

    merged = pd.DataFrame({
        "course_id": capped["new_course_id"].astype(int),
        "title": capped["title"],
        "provider": capped["provider"],
        "skill_id": capped["skill_id"].astype(int),
        "cost": capped["cost"].round(2),
        "duration_hours": capped["duration_hours"].round(2),
        "difficulty": capped["difficulty"].replace("", "Unspecified"),
        "source_url": capped["source_url"],
    })

    report = (
        kept.groupby("mapped_skill")
        .agg(
            kept_after_filter=("title", "count"),
            exported_to_app=("title", lambda s: min(len(s), MAX_COURSES_PER_SKILL)),
            median_cost=("cost", "median"),
            median_duration_hours=("duration_hours", "median"),
            max_relevance_score=("relevance_score", "max"),
        )
        .reset_index()
        .sort_values("exported_to_app", ascending=False)
    )

    return merged, report, dropped


def backup_existing_courses() -> None:
    if EXISTING_COURSES_PATH.exists() and not BACKUP_COURSES_PATH.exists():
        shutil.copy2(EXISTING_COURSES_PATH, BACKUP_COURSES_PATH)
        print(f"Backed up existing courses.csv to: {BACKUP_COURSES_PATH}")
    elif BACKUP_COURSES_PATH.exists():
        print(f"Backup already exists, not overwritten: {BACKUP_COURSES_PATH}")


def main() -> None:
    ensure_dirs()

    skills, real_courses = load_data()
    merged, report, dropped = build_merged_courses(skills, real_courses)

    backup_existing_courses()

    merged.to_csv(MERGED_COURSES_PATH, index=False, encoding="utf-8-sig")
    report.to_csv(MERGE_REPORT_PATH, index=False, encoding="utf-8-sig")
    dropped.head(1000).to_csv(DROPPED_REVIEW_PATH, index=False, encoding="utf-8-sig")

    print("Real SkillsFuture courses merged successfully.")
    print(f"Exported app-ready courses: {len(merged):,}")
    print(f"Skills covered in app-ready courses: {merged['skill_id'].nunique():,}")
    print(f"Saved: {MERGED_COURSES_PATH}")
    print(f"Saved report: {MERGE_REPORT_PATH}")
    print(f"Saved dropped review sample: {DROPPED_REVIEW_PATH}")

    print("\nTop exported skills:")
    display = report.head(20).copy()
    print(display.to_string(index=False))


if __name__ == "__main__":
    main()
