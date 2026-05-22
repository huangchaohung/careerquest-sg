from __future__ import annotations

from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OCCUPATIONS_PATH = PROJECT_ROOT / "data" / "raw" / "occupations.csv"
OCCUPATION_SKILLS_PATH = PROJECT_ROOT / "data" / "raw" / "occupation_skills.csv"
SKILLS_PATH = PROJECT_ROOT / "data" / "raw" / "skills.csv"
COURSES_REAL_PATH = PROJECT_ROOT / "data" / "processed" / "courses_real.csv"

BACKUP_PATH = PROJECT_ROOT / "data" / "raw" / "occupations_mom_demand_backup.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "occupation_refined_demand_report.csv"

MOM_WEIGHT = 0.70
COURSE_SIGNAL_WEIGHT = 0.30


def load_inputs():
    required_paths = [
        OCCUPATIONS_PATH,
        OCCUPATION_SKILLS_PATH,
        SKILLS_PATH,
        COURSES_REAL_PATH,
    ]

    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")

    occupations = pd.read_csv(OCCUPATIONS_PATH)
    occupation_skills = pd.read_csv(OCCUPATION_SKILLS_PATH)
    skills = pd.read_csv(SKILLS_PATH)
    courses = pd.read_csv(COURSES_REAL_PATH)

    return occupations, occupation_skills, skills, courses


def build_skill_course_signal(courses: pd.DataFrame) -> pd.DataFrame:
    """
    Count real SkillsFuture courses by mapped skill and normalize to 0-1.

    Uses log scaling so extremely common skills such as Communication or Git
    do not dominate too aggressively.
    """
    if "mapped_skill" not in courses.columns:
        raise ValueError("courses_real.csv must contain a mapped_skill column.")

    counts = (
        courses.groupby("mapped_skill")
        .size()
        .reset_index(name="course_count")
    )

    # log1p scaling
    counts["log_course_count"] = counts["course_count"].apply(lambda x: __import__("math").log1p(x))
    max_log = counts["log_course_count"].max()

    if max_log == 0:
        counts["skill_course_signal"] = 0.0
    else:
        counts["skill_course_signal"] = counts["log_course_count"] / max_log

    return counts[["mapped_skill", "course_count", "skill_course_signal"]]


def build_role_course_signal(
    occupations: pd.DataFrame,
    occupation_skills: pd.DataFrame,
    skills: pd.DataFrame,
    skill_signals: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute each role's course-supply signal as an importance-weighted average
    of the course signals for its required skills.
    """
    merged = (
        occupation_skills
        .merge(skills, on="skill_id", how="left")
        .merge(skill_signals, left_on="name", right_on="mapped_skill", how="left")
    )

    merged["course_count"] = merged["course_count"].fillna(0)
    merged["skill_course_signal"] = merged["skill_course_signal"].fillna(0.0)

    merged["weighted_signal"] = merged["importance"] * merged["skill_course_signal"]

    role_signal = (
        merged.groupby("occupation_id")
        .agg(
            total_importance=("importance", "sum"),
            weighted_course_signal=("weighted_signal", "sum"),
            total_course_count=("course_count", "sum"),
            mapped_skill_count=("mapped_skill", lambda x: x.notna().sum()),
        )
        .reset_index()
    )

    role_signal["role_course_signal"] = (
        role_signal["weighted_course_signal"] / role_signal["total_importance"]
    ).fillna(0.0)

    output = occupations[["occupation_id", "name", "demand_score"]].merge(
        role_signal,
        on="occupation_id",
        how="left",
    )

    output["role_course_signal"] = output["role_course_signal"].fillna(0.0)
    output["total_course_count"] = output["total_course_count"].fillna(0).astype(int)
    output["mapped_skill_count"] = output["mapped_skill_count"].fillna(0).astype(int)

    return output


def refine_demand(occupations: pd.DataFrame, role_signal: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    updated = occupations.copy()

    report = role_signal.copy()
    report = report.rename(columns={"demand_score": "mom_demand_score"})

    report["refined_demand_score"] = (
        MOM_WEIGHT * report["mom_demand_score"]
        + COURSE_SIGNAL_WEIGHT * report["role_course_signal"]
    ).clip(lower=0.05, upper=1.0)

    report["refined_demand_score"] = report["refined_demand_score"].round(3)
    report["mom_demand_score"] = report["mom_demand_score"].round(3)
    report["role_course_signal"] = report["role_course_signal"].round(3)

    score_lookup = dict(zip(report["occupation_id"], report["refined_demand_score"]))

    updated["demand_score"] = updated["occupation_id"].map(score_lookup).fillna(updated["demand_score"])
    updated["demand_score"] = updated["demand_score"].round(3)

    report = report[
        [
            "occupation_id",
            "name",
            "mom_demand_score",
            "role_course_signal",
            "refined_demand_score",
            "total_course_count",
            "mapped_skill_count",
        ]
    ].sort_values("refined_demand_score", ascending=False)

    return updated, report


def main():
    occupations, occupation_skills, skills, courses = load_inputs()

    if not BACKUP_PATH.exists():
        occupations.to_csv(BACKUP_PATH, index=False, encoding="utf-8-sig")
        print(f"Backed up MOM-demand occupations file to: {BACKUP_PATH}")
    else:
        print(f"Backup already exists, leaving unchanged: {BACKUP_PATH}")

    skill_signals = build_skill_course_signal(courses)
    role_signal = build_role_course_signal(occupations, occupation_skills, skills, skill_signals)
    updated, report = refine_demand(occupations, role_signal)

    updated.to_csv(OCCUPATIONS_PATH, index=False, encoding="utf-8-sig")
    report.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")

    print(f"Updated occupations.csv with refined demand scores: {OCCUPATIONS_PATH}")
    print(f"Saved refined demand report: {REPORT_PATH}")

    print("\nTop refined demand scores:")
    print(report.head(20).to_string(index=False))

    print("\nLowest refined demand scores:")
    print(report.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
