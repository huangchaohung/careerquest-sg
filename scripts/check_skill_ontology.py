"""
CareerQuest SG — Skill Ontology Validation

Purpose:
    Validates skill ontology columns in data/raw/skills.csv.

Run:
    python scripts/check_skill_ontology.py

Output:
    data/processed/skill_ontology_report.csv
"""

from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_PATH = PROJECT_ROOT / "data" / "raw" / "skills.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "skill_ontology_report.csv"

ALLOWED_FAMILIES = {
    "Technical", "Analytical", "Professional", "Domain", "Operations", "Management"
}

ALLOWED_LEVELS = {
    "Foundational", "Intermediate", "Advanced", "Specialist"
}

ALLOWED_TRANSFERABILITY = {
    "High", "Medium", "Low"
}


def main():
    df = pd.read_csv(SKILLS_PATH)

    required_cols = {
        "skill_id", "name", "category",
        "skill_family", "skill_level", "transferability"
    }

    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"skills.csv missing columns: {missing_cols}")

    errors = []

    invalid_family = df[~df["skill_family"].isin(ALLOWED_FAMILIES)]
    invalid_level = df[~df["skill_level"].isin(ALLOWED_LEVELS)]
    invalid_transferability = df[~df["transferability"].isin(ALLOWED_TRANSFERABILITY)]

    if not invalid_family.empty:
        errors.append(("Invalid skill_family", invalid_family))
    if not invalid_level.empty:
        errors.append(("Invalid skill_level", invalid_level))
    if not invalid_transferability.empty:
        errors.append(("Invalid transferability", invalid_transferability))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")

    if errors:
        for label, bad_df in errors:
            print(f"\n{label}:")
            print(bad_df[["skill_id", "name", "skill_family", "skill_level", "transferability"]].to_string(index=False))
        raise ValueError("Skill ontology validation failed.")

    print("Skill ontology check passed.")
    print(f"Saved report: {REPORT_PATH}")

    print("\nSkill family distribution:")
    print(df["skill_family"].value_counts().to_string())

    print("\nSkill level distribution:")
    print(df["skill_level"].value_counts().to_string())

    print("\nTransferability distribution:")
    print(df["transferability"].value_counts().to_string())


if __name__ == "__main__":
    main()
