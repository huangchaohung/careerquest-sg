"""
CareerQuest SG — Step 7: SkillsFuture Course ETL

Purpose:
    Fetch the real MySkillsFuture Course Directory dataset from data.gov.sg,
    filter it for CareerQuest-relevant courses, map courses to skills, and
    export a clean `courses_real.csv`.

Dataset:
    MySkillsFuture Course Directory
    Publisher: SkillsFuture Singapore (SSG)
    Dataset ID: d_b5802b76f409764c16dde4bf2feb19cd

How to run from project root:
    python scripts/fetch_skillsfuture_courses.py

Outputs:
    data/raw_external/myskillsfuture_course_directory.xlsx
    data/processed/courses_real.csv
    data/processed/courses_real_review.csv

Notes:
    - This script does NOT overwrite your existing data/raw/courses.csv.
    - Review courses_real_review.csv first.
    - Later, we will merge approved rows into the app database.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_ID = "d_b5802b76f409764c16dde4bf2feb19cd"
POLL_DOWNLOAD_URL = (
    "https://api-open.data.gov.sg/v1/public/api/datasets/"
    f"{DATASET_ID}/poll-download"
)

RAW_DIR = PROJECT_ROOT / "data" / "raw_external"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

RAW_XLSX_PATH = RAW_DIR / "myskillsfuture_course_directory.xlsx"
COURSES_REAL_PATH = PROCESSED_DIR / "courses_real.csv"
COURSES_REVIEW_PATH = PROCESSED_DIR / "courses_real_review.csv"


# Map CareerQuest skill names to course-search keywords.
# You can edit this mapping as your skill taxonomy grows.
SKILL_KEYWORDS: Dict[str, List[str]] = {
    "SQL": ["sql", "database query", "structured query"],
    "Python": ["python", "pandas", "numpy"],
    "Statistics": ["statistics", "statistical", "data analysis"],
    "Data Cleaning": ["data cleaning", "data preparation", "data wrangling", "data quality"],
    "Data Visualization": ["data visualisation", "data visualization", "visual analytics", "storytelling with data"],
    "Dashboarding": ["dashboard", "dashboarding", "business dashboard"],
    "Power BI": ["power bi", "microsoft power bi"],
    "Tableau": ["tableau"],
    "Machine Learning Basics": ["machine learning", "artificial intelligence", "predictive analytics", "deep learning", "neural network"],
    "Predictive Modelling": ["predictive modelling", "predictive modeling", "forecasting model", "machine learning"],
    "ETL": ["etl", "data pipeline", "data engineering"],
    "Database Design": ["database design", "relational database"],
    "Data Warehousing": ["data warehouse", "data warehousing"],
    "APIs": ["api", "application programming interface"],
    "Git": ["git", "github", "version control"],
    "Cloud Basics": ["cloud", "aws", "azure", "google cloud"],
    "Business Requirements Gathering": ["business analysis", "requirements gathering", "requirements analysis"],
    "Stakeholder Management": ["stakeholder management", "stakeholder engagement"],
    "Process Mapping": ["process mapping", "business process", "bpmn"],
    "KPI Design": ["kpi", "performance indicator", "performance measurement"],
    "Reporting": ["business reporting", "management reporting", "report writing"],
    "Project Management": ["project management", "scrum", "agile"],
    "HRIS": ["hris", "human resource information system"],
    "Workforce Planning": ["workforce planning", "manpower planning"],
    "Employee Engagement Analysis": ["employee engagement", "people analytics"],
    "Training Needs Analysis": ["training needs", "learning needs"],
    "Labour Market Research": ["labour market", "labor market", "workforce analytics"],
    "Compensation Analysis": ["compensation", "salary analysis", "payroll analytics"],
    "Financial Reporting": ["financial reporting", "financial analysis"],
    "Budget Tracking": ["budget", "budgeting"],
    "Procurement": ["procurement", "sourcing"],
    "Vendor Management": ["vendor management", "supplier management"],
    "Inventory Management": ["inventory management"],
    "Demand Forecasting": ["demand forecasting", "forecasting"],
    "Supply Chain Coordination": ["supply chain", "logistics"],
    "Lean Six Sigma Basics": ["lean six sigma", "six sigma", "process improvement"],
    "Communication": ["communication", "business communication"],
    "Presentation": ["presentation", "presenting", "storytelling"],
    "Critical Thinking": ["critical thinking", "problem solving"],
}

PUBLIC_POLICY_KEYWORDS = {

    "Policy Analysis": [
        "policy",
        "public policy",
        "policy analysis",
        "policy development",
        "governance",
        "regulation",
        "regulatory",
        "policy writing"
    ],

    "Programme Evaluation": [
        "programme evaluation",
        "program evaluation",
        "impact evaluation",
        "monitoring and evaluation",
        "evaluation framework",
        "outcome evaluation"
    ],

    "Impact Assessment": [
        "impact assessment",
        "social impact",
        "outcome assessment",
        "impact measurement",
        "evaluation"
    ],

    "Stakeholder Consultation": [
        "stakeholder engagement",
        "stakeholder management",
        "consultation",
        "public engagement",
        "community engagement"
    ],

    "Public Communication": [
        "public communication",
        "media communication",
        "campaign communication",
        "corporate communication",
        "communications"
    ],

    "Service Design": [
        "service design",
        "customer journey",
        "design thinking",
        "service improvement"
    ],

    "Public Sector Operations": [
        "public sector",
        "government operations",
        "service delivery",
        "operations management"
    ],

    "Regulatory Understanding": [
        "regulation",
        "regulatory",
        "compliance",
        "governance",
        "risk and compliance"
    ],

    "Report Writing": [
        "report writing",
        "business writing",
        "professional writing",
        "technical writing"
    ]
}

SKILL_KEYWORDS.update(PUBLIC_POLICY_KEYWORDS)

# Difficulty guess based on course title. This is only a display field.
DIFFICULTY_RULES = [
    ("Advanced", ["advanced", "masterclass", "expert"]),
    ("Intermediate", ["intermediate", "applied", "practical", "professional"]),
    ("Beginner", ["foundation", "foundations", "fundamental", "fundamentals", "basic", "beginner", "intro"]),
]


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def fetch_download_url() -> str:
    response = requests.get(POLL_DOWNLOAD_URL, timeout=60)
    response.raise_for_status()
    payload = response.json()

    if payload.get("code") != 0:
        raise RuntimeError(f"data.gov.sg API error: {payload.get('errMsg')}")

    return payload["data"]["url"]


def download_dataset(download_url: str, output_path: Path) -> None:
    response = requests.get(download_url, timeout=120)
    response.raise_for_status()

    output_path.write_bytes(response.content)


def normalize_column_name(col: str) -> str:
    col = str(col).strip().lower()
    col = re.sub(r"[^a-z0-9]+", "_", col)
    col = re.sub(r"_+", "_", col).strip("_")
    return col


def load_raw_xlsx(path: Path) -> pd.DataFrame:
    # Read first sheet by default.
    df = pd.read_excel(path)
    df.columns = [normalize_column_name(c) for c in df.columns]
    return df


def find_first_existing_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    columns = set(df.columns)
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def infer_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    return {
        "title": find_first_existing_column(
            df,
            [
                "coursetitle",
                "course_title",
                "course_name",
                "title",
                "course",
                "programme_title",
                "program_title",
            ],
        ),
        "provider": find_first_existing_column(
            df,
            [
                "trainingprovideralias",
                "training_provider",
                "provider",
                "organisation",
                "organization",
                "training_provider_name",
                "course_provider",
            ],
        ),
        "description": find_first_existing_column(
            df,
            [
                "about_this_course",
                "what_you_learn",
                "course_description",
                "description",
                "synopsis",
                "course_synopsis",
                "objectives",
            ],
        ),
        "url": find_first_existing_column(
            df,
            [
                "course_url",
                "url",
                "course_link",
                "link",
                "course_detail_url",
            ],
        ),
        "duration": find_first_existing_column(
            df,
            [
                "number_of_hours",
                "duration",
                "course_duration",
                "training_duration",
                "duration_hours",
                "total_training_duration",
            ],
        ),
        "fee": find_first_existing_column(
            df,
            [
                "course_fee_after_subsidies",
                "full_course_fee",
                "course_fee",
                "fee",
                "full_fee",
                "net_fee",
                "course_fees",
                "fees",
            ],
        ),
    }


def safe_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def parse_numeric(value) -> Optional[float]:
    if pd.isna(value):
        return None

    text = str(value)
    numbers = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))

    if not numbers:
        return None

    return float(numbers[0])


def guess_difficulty(title: str, description: str) -> str:
    text = f"{title} {description}".lower()

    for difficulty, keywords in DIFFICULTY_RULES:
        if any(keyword in text for keyword in keywords):
            return difficulty

    return "Unspecified"


def match_skill(title: str, description: str) -> Optional[str]:
    text = f"{title} {description}".lower()

    # Prefer longer/more specific keywords first.
    matches = []
    for skill, keywords in SKILL_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                matches.append((len(keyword), skill))
                break

    if not matches:
        return None

    matches.sort(reverse=True)
    return matches[0][1]


def build_clean_courses(df: pd.DataFrame) -> pd.DataFrame:
    columns = infer_columns(df)

    if columns["title"] is None:
        raise ValueError(
            "Could not infer course title column. "
            f"Available columns: {list(df.columns)}"
        )

    rows = []

    for _, row in df.iterrows():
        title = safe_text(row.get(columns["title"]))
        provider = safe_text(row.get(columns["provider"])) if columns["provider"] else ""
        description = safe_text(row.get(columns["description"])) if columns["description"] else ""
        url = safe_text(row.get(columns["url"])) if columns["url"] else ""
        duration_hours = parse_numeric(row.get(columns["duration"])) if columns["duration"] else None
        cost = parse_numeric(row.get(columns["fee"])) if columns["fee"] else None

        if not title.strip():
            continue

        skill = match_skill(title, description)
        if skill is None:
            continue

        rows.append(
            {
                "title": title.strip(),
                "provider": provider.strip(),
                "mapped_skill": skill,
                "cost": cost,
                "duration_hours": duration_hours,
                "difficulty": guess_difficulty(title, description),
                "source_url": url.strip(),
                "description_preview": description[:300].replace("\n", " ").strip(),
            }
        )

    clean = pd.DataFrame(rows)

    if clean.empty:
        return clean

    # Remove duplicate title/provider/skill rows.
    clean = clean.drop_duplicates(subset=["title", "provider", "mapped_skill"])

    # Prefer rows with duration/cost/url if duplicates-like exist.
    clean["has_duration"] = clean["duration_hours"].notna()
    clean["has_cost"] = clean["cost"].notna()
    clean["has_url"] = clean["source_url"].astype(str).str.len() > 0

    clean = clean.sort_values(
        by=["mapped_skill", "has_url", "has_duration", "has_cost", "title"],
        ascending=[True, False, False, False, True],
    )

    clean = clean.drop(columns=["has_duration", "has_cost", "has_url"]).reset_index(drop=True)

    # Add stable local IDs.
    clean.insert(0, "course_id", range(1, len(clean) + 1))

    return clean


def create_review_sample(clean: pd.DataFrame, max_per_skill: int = 10) -> pd.DataFrame:
    if clean.empty:
        return clean

    return (
        clean.groupby("mapped_skill", group_keys=False)
        .head(max_per_skill)
        .reset_index(drop=True)
    )


def main() -> None:
    ensure_dirs()

    if RAW_XLSX_PATH.exists():
        print(f"Using existing raw file: {RAW_XLSX_PATH}")
    else:
        print("Fetching data.gov.sg download URL...")
        download_url = fetch_download_url()

        print("Downloading MySkillsFuture Course Directory...")
        download_dataset(download_url, RAW_XLSX_PATH)
        print(f"Saved raw file: {RAW_XLSX_PATH}")

    print("Reading XLSX...")
    raw_df = load_raw_xlsx(RAW_XLSX_PATH)
    print(f"Raw rows: {len(raw_df):,}")
    print(f"Raw columns: {list(raw_df.columns)}")

    print("Filtering and mapping courses...")
    clean_df = build_clean_courses(raw_df)

    if clean_df.empty:
        print("No matched courses found. You may need to update SKILL_KEYWORDS.")
        return

    review_df = create_review_sample(clean_df, max_per_skill=10)

    clean_df.to_csv(COURSES_REAL_PATH, index=False, encoding="utf-8-sig")
    review_df.to_csv(COURSES_REVIEW_PATH, index=False, encoding="utf-8-sig")

    print(f"Matched rows: {len(clean_df):,}")
    print(f"Skills covered: {clean_df['mapped_skill'].nunique():,}")
    print(f"Saved full processed file: {COURSES_REAL_PATH}")
    print(f"Saved review sample: {COURSES_REVIEW_PATH}")

    print("\nTop mapped skills:")
    print(clean_df["mapped_skill"].value_counts().head(20).to_string())


if __name__ == "__main__":
    main()
