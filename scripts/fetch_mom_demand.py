from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_ID = "d_77a848ab5508fa38c5bbf72a956b3cf5"
DATASTORE_URL = "https://data.gov.sg/api/action/datastore_search"

RAW_OCCUPATIONS_PATH = PROJECT_ROOT / "data" / "raw" / "occupations.csv"
BACKUP_OCCUPATIONS_PATH = PROJECT_ROOT / "data" / "raw" / "occupations_manual_demand_backup.csv"

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MOM_RAW_OUTPUT_PATH = PROCESSED_DIR / "mom_job_vacancy_by_occupation.csv"
MAPPING_REPORT_PATH = PROCESSED_DIR / "occupation_demand_mapping_report.csv"


# CareerQuest role -> MOM broad occupation group.
# These categories come from the official dataset's occupation field.
ROLE_TO_MOM_GROUP: Dict[str, str] = {
    # Fresh graduate nodes are entry profiles, not official occupation groups.
    "Fresh Graduate — Data Science Bachelor's": "professionals, managers, executives and technicians",
    "Fresh Graduate — Business Bachelor's": "professionals, managers, executives and technicians",
    "Fresh Graduate — Engineering Bachelor's": "professionals, managers, executives and technicians",
    "Fresh Graduate — Data Science Master's": "professionals, managers, executives and technicians",
    "Fresh Graduate — Business Analytics Master's": "professionals, managers, executives and technicians",

    # Data / tech
    "Data Analyst": "professionals, managers, executives and technicians",
    "Business Intelligence Analyst": "professionals, managers, executives and technicians",
    "Junior Data Scientist": "professionals, managers, executives and technicians",
    "Data Engineer": "professionals, managers, executives and technicians",
    "Machine Learning Engineer": "professionals, managers, executives and technicians",

    # Business / admin
    "Administrative Executive": "clerical, sales and services workers",
    "Business Analyst": "professionals, managers, executives and technicians",
    "Project Coordinator": "professionals, managers, executives and technicians",
    "Operations Analyst": "professionals, managers, executives and technicians",
    "Product Operations Associate": "professionals, managers, executives and technicians",

    # HR / finance
    "HR Executive": "professionals, managers, executives and technicians",
    "Recruitment Coordinator": "clerical, sales and services workers",
    "HR Analyst": "professionals, managers, executives and technicians",
    "Payroll Executive": "clerical, sales and services workers",
    "Finance Analyst": "professionals, managers, executives and technicians",

    # Operations / logistics
    "Operations Executive": "clerical, sales and services workers",
    "Logistics Coordinator": "clerical, sales and services workers",
    "Supply Chain Analyst": "professionals, managers, executives and technicians",
    "Procurement Executive": "clerical, sales and services workers",
    "Process Improvement Analyst": "professionals, managers, executives and technicians",

    "Policy Analyst": "professionals, managers, executives and technicians",
    "Research Assistant": "professionals, managers, executives and technicians",
    "Programme Executive": "professionals, managers, executives and technicians",
    "Grants Officer": "professionals, managers, executives and technicians",
    "Public Communications Executive": "professionals, managers, executives and technicians",
    "Service Delivery Executive": "clerical, sales and services workers",
    "Evaluation Analyst": "professionals, managers, executives and technicians",
    "Operations Policy Analyst": "professionals, managers, executives and technicians",
}


def ensure_dirs() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def fetch_datastore_records(resource_id: str) -> pd.DataFrame:
    """
    Fetch all records from data.gov.sg datastore_search using pagination.
    """
    all_records = []
    limit = 500
    offset = 0

    while True:
        params = {
            "resource_id": resource_id,
            "limit": limit,
            "offset": offset,
        }

        response = requests.get(DATASTORE_URL, params=params, timeout=60)
        response.raise_for_status()

        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"data.gov.sg datastore error: {payload}")

        result = payload["result"]
        records = result["records"]
        all_records.extend(records)

        if offset + limit >= result["total"]:
            break

        offset += limit

    return pd.DataFrame(all_records)


def clean_mom_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize columns and types.
    """
    clean = df.copy()
    clean.columns = [col.lower().strip() for col in clean.columns]

    # Expected columns: year, occupation, job_vacancy
    required = {"year", "occupation", "job_vacancy"}
    missing = required - set(clean.columns)
    if missing:
        raise ValueError(f"Missing expected columns: {missing}. Found: {list(clean.columns)}")

    clean["year"] = pd.to_numeric(clean["year"], errors="coerce")
    clean["job_vacancy"] = (
        clean["job_vacancy"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )
    clean["occupation"] = clean["occupation"].astype(str).str.strip().str.lower()

    clean = clean.dropna(subset=["year", "occupation", "job_vacancy"])
    clean["year"] = clean["year"].astype(int)

    return clean[["year", "occupation", "job_vacancy"]]


def build_latest_demand_scores(mom_df: pd.DataFrame) -> pd.DataFrame:
    """
    Take the latest year and normalize job vacancy numbers into 0-1 demand scores.
    """
    latest_year = mom_df["year"].max()
    latest = mom_df[mom_df["year"] == latest_year].copy()

    max_vacancy = latest["job_vacancy"].max()
    min_vacancy = latest["job_vacancy"].min()

    if max_vacancy == min_vacancy:
        latest["demand_score"] = 0.5
    else:
        latest["demand_score"] = (
            (latest["job_vacancy"] - min_vacancy)
            / (max_vacancy - min_vacancy)
        )

    # Avoid exact zero because even lower-demand broad groups still have some demand.
    latest["demand_score"] = latest["demand_score"].clip(lower=0.15, upper=1.0)

    return latest[["year", "occupation", "job_vacancy", "demand_score"]]


def update_occupations_with_demand(occupations_df: pd.DataFrame, demand_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    demand_lookup = {
        row["occupation"]: {
            "year": row["year"],
            "job_vacancy": row["job_vacancy"],
            "demand_score": row["demand_score"],
        }
        for _, row in demand_df.iterrows()
    }

    updated = occupations_df.copy()
    report_rows = []

    for idx, row in updated.iterrows():
        role = row["name"]
        mapped_group = ROLE_TO_MOM_GROUP.get(role)

        if mapped_group is None:
            # Keep existing score if unmapped.
            report_rows.append({
                "occupation": role,
                "mapped_mom_group": None,
                "mom_year": None,
                "mom_job_vacancy": None,
                "old_demand_score": row.get("demand_score"),
                "new_demand_score": row.get("demand_score"),
                "status": "unmapped_keep_existing",
            })
            continue

        mom_info = demand_lookup.get(mapped_group.lower())

        if mom_info is None:
            report_rows.append({
                "occupation": role,
                "mapped_mom_group": mapped_group,
                "mom_year": None,
                "mom_job_vacancy": None,
                "old_demand_score": row.get("demand_score"),
                "new_demand_score": row.get("demand_score"),
                "status": "mapped_group_not_found_keep_existing",
            })
            continue

        old_score = row.get("demand_score")
        new_score = round(float(mom_info["demand_score"]), 3)
        updated.at[idx, "demand_score"] = new_score

        report_rows.append({
            "occupation": role,
            "mapped_mom_group": mapped_group,
            "mom_year": int(mom_info["year"]),
            "mom_job_vacancy": int(mom_info["job_vacancy"]),
            "old_demand_score": old_score,
            "new_demand_score": new_score,
            "status": "updated",
        })

    report = pd.DataFrame(report_rows)
    return updated, report


def main() -> None:
    ensure_dirs()

    if not RAW_OCCUPATIONS_PATH.exists():
        raise FileNotFoundError(f"Cannot find {RAW_OCCUPATIONS_PATH}")

    print("Fetching MOM job vacancy by occupation data from data.gov.sg...")
    raw_df = fetch_datastore_records(DATASET_ID)
    print(f"Fetched rows: {len(raw_df):,}")

    mom_df = clean_mom_data(raw_df)
    mom_df.to_csv(MOM_RAW_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"Saved processed MOM data: {MOM_RAW_OUTPUT_PATH}")

    demand_df = build_latest_demand_scores(mom_df)
    latest_year = demand_df["year"].max()
    print(f"Latest MOM year used: {latest_year}")

    print("\nLatest demand scores by MOM occupation group:")
    print(
        demand_df.sort_values("demand_score", ascending=False)
        .to_string(index=False)
    )

    occupations_df = pd.read_csv(RAW_OCCUPATIONS_PATH)

    if not BACKUP_OCCUPATIONS_PATH.exists():
        occupations_df.to_csv(BACKUP_OCCUPATIONS_PATH, index=False, encoding="utf-8-sig")
        print(f"\nBacked up original occupations.csv to: {BACKUP_OCCUPATIONS_PATH}")
    else:
        print(f"\nBackup already exists, leaving it unchanged: {BACKUP_OCCUPATIONS_PATH}")

    updated, report = update_occupations_with_demand(occupations_df, demand_df)

    updated.to_csv(RAW_OCCUPATIONS_PATH, index=False, encoding="utf-8-sig")
    report.to_csv(MAPPING_REPORT_PATH, index=False, encoding="utf-8-sig")

    print(f"Updated occupations.csv with MOM-based demand scores: {RAW_OCCUPATIONS_PATH}")
    print(f"Saved mapping report: {MAPPING_REPORT_PATH}")

    print("\nMapping report summary:")
    print(report["status"].value_counts().to_string())

    print("\nSample updated occupations:")
    sample_cols = ["name", "sector", "demand_score"]
    print(updated[sample_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
