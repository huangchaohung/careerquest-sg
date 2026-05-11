"""
CareerQuest SG — Skill Ontology Migration

Purpose:
    Adds skill ontology columns to data/raw/skills.csv if missing:
    - skill_family
    - skill_level
    - transferability

Run from project root:
    python scripts/add_skill_ontology.py

Output:
    Updates data/raw/skills.csv in place
    Creates backup data/raw/skills_before_ontology_backup.csv
"""

from pathlib import Path
import shutil
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_PATH = PROJECT_ROOT / "data" / "raw" / "skills.csv"
BACKUP_PATH = PROJECT_ROOT / "data" / "raw" / "skills_before_ontology_backup.csv"


TECHNICAL_SKILLS = {
    "SQL", "Python", "Power BI", "Tableau", "Dashboarding", "Data Cleaning",
    "Data Visualization", "Machine Learning Basics", "Predictive Modelling",
    "ETL", "Database Design", "Data Warehousing", "APIs", "Git", "Cloud Basics",
    "Excel", "A/B Testing", "R", "Workflow Automation"
}

ANALYTICAL_SKILLS = {
    "Statistics", "KPI Design", "Business Requirements Gathering",
    "Labour Market Research", "Compensation Analysis", "Demand Forecasting",
    "Survey Design", "Qualitative Research", "Programme Evaluation",
    "Impact Assessment", "Cost-Benefit Analysis", "Problem Structuring",
    "Market Research", "Risk Analysis"
}

PROFESSIONAL_SKILLS = {
    "Communication", "Presentation", "Critical Thinking", "Stakeholder Management",
    "Stakeholder Consultation", "Public Communication", "Documentation",
    "Team Coordination", "Time Management", "Customer Service", "Interview Coordination",
    "Negotiation", "Change Management"
}

OPERATIONS_SKILLS = {
    "Process Mapping", "HRIS", "Workforce Planning", "Employee Engagement Analysis",
    "Training Needs Analysis", "Financial Reporting", "Budget Tracking",
    "Procurement", "Vendor Management", "Inventory Management",
    "Supply Chain Coordination", "Lean Six Sigma Basics", "Recruitment Operations",
    "Logistics Planning", "Payroll Processing", "Quality Control",
    "Grant Administration", "Public Sector Operations", "Service Design"
}

DOMAIN_SKILLS = {
    "Policy Analysis", "Regulatory Understanding"
}

ADVANCED_SKILLS = {
    "Machine Learning Basics", "Predictive Modelling", "Data Warehousing",
    "Programme Evaluation", "Impact Assessment", "Risk Analysis", "A/B Testing"
}

FOUNDATIONAL_SKILLS = {
    "Communication", "Presentation", "Critical Thinking", "Excel",
    "Time Management", "Customer Service", "Documentation", "Team Coordination"
}

LOW_TRANSFERABILITY_SKILLS = {
    "Payroll Processing", "Grant Administration", "Regulatory Understanding",
    "Policy Analysis", "HRIS"
}

MEDIUM_TRANSFERABILITY_SKILLS = {
    "Machine Learning Basics", "Predictive Modelling", "Programme Evaluation",
    "Impact Assessment", "Procurement", "Financial Reporting", "Supply Chain Coordination",
    "Public Sector Operations", "Service Design"
}


def infer_skill_family(name: str, category: str) -> str:
    if name in TECHNICAL_SKILLS:
        return "Technical"
    if name in ANALYTICAL_SKILLS:
        return "Analytical"
    if name in PROFESSIONAL_SKILLS:
        return "Professional"
    if name in OPERATIONS_SKILLS:
        return "Operations"
    if name in DOMAIN_SKILLS:
        return "Domain"

    category_lower = str(category).lower()
    if "technical" in category_lower or "data" in category_lower:
        return "Technical"
    if "soft" in category_lower or "professional" in category_lower:
        return "Professional"
    if "finance" in category_lower or "operations" in category_lower:
        return "Operations"
    if "business" in category_lower or "analytical" in category_lower:
        return "Analytical"

    return "Professional"


def infer_skill_level(name: str, family: str) -> str:
    if name in FOUNDATIONAL_SKILLS:
        return "Foundational"
    if name in ADVANCED_SKILLS:
        return "Advanced"
    if family == "Domain":
        return "Intermediate"
    if family == "Technical":
        return "Intermediate"
    return "Intermediate"


def infer_transferability(name: str, family: str) -> str:
    if name in LOW_TRANSFERABILITY_SKILLS:
        return "Low"
    if name in MEDIUM_TRANSFERABILITY_SKILLS:
        return "Medium"
    if family in {"Professional", "Technical", "Analytical"}:
        return "High"
    return "Medium"


def main():
    if not SKILLS_PATH.exists():
        raise FileNotFoundError(f"Cannot find {SKILLS_PATH}")

    df = pd.read_csv(SKILLS_PATH)

    required = {"skill_id", "name", "category"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"skills.csv missing required columns: {missing}")

    if not BACKUP_PATH.exists():
        shutil.copy2(SKILLS_PATH, BACKUP_PATH)
        print(f"Backup saved to: {BACKUP_PATH}")
    else:
        print(f"Backup already exists: {BACKUP_PATH}")

    if "skill_family" not in df.columns:
        df["skill_family"] = ""
    if "skill_level" not in df.columns:
        df["skill_level"] = ""
    if "transferability" not in df.columns:
        df["transferability"] = ""

    for idx, row in df.iterrows():
        name = str(row["name"]).strip()
        category = str(row["category"]).strip()

        if not str(row.get("skill_family", "")).strip():
            df.at[idx, "skill_family"] = infer_skill_family(name, category)

        if not str(row.get("skill_level", "")).strip():
            df.at[idx, "skill_level"] = infer_skill_level(name, df.at[idx, "skill_family"])

        if not str(row.get("transferability", "")).strip():
            df.at[idx, "transferability"] = infer_transferability(name, df.at[idx, "skill_family"])

    df.to_csv(SKILLS_PATH, index=False, encoding="utf-8-sig")

    print(f"Updated: {SKILLS_PATH}")
    print("\nSkill family distribution:")
    print(df["skill_family"].value_counts().to_string())

    print("\nSkill level distribution:")
    print(df["skill_level"].value_counts().to_string())

    print("\nTransferability distribution:")
    print(df["transferability"].value_counts().to_string())


if __name__ == "__main__":
    main()
