"""
CareerQuest SG — Transition Confidence Migration

Purpose:
    Adds a transition_confidence column to data/raw/career_transitions.csv
    if it does not already exist.

Why:
    This helps the app distinguish between:
    - common/natural transitions
    - reasonable adjacent transitions
    - exploratory/difficult switches

Run from project root:
    python scripts/add_transition_confidence.py

Output:
    Updates data/raw/career_transitions.csv in place
    Creates backup data/raw/career_transitions_before_confidence_backup.csv
"""

from pathlib import Path
import shutil
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRANSITIONS_PATH = PROJECT_ROOT / "data" / "raw" / "career_transitions.csv"
BACKUP_PATH = PROJECT_ROOT / "data" / "raw" / "career_transitions_before_confidence_backup.csv"


def infer_confidence(row) -> float:
    transition_type = str(row.get("transition_type", "")).lower()
    difficulty = int(row.get("difficulty", 3))
    months = float(row.get("estimated_months", 12))

    # Explicit type-based rules first.
    if "fresh_graduate_entry" in transition_type:
        base = 0.75
    elif "similar" in transition_type:
        base = 0.90
    elif "adjacent" in transition_type:
        base = 0.75
    elif "analytical_upgrade" in transition_type:
        base = 0.65
    elif "specialisation" in transition_type or "specialization" in transition_type:
        base = 0.70
    elif "career_switch" in transition_type:
        base = 0.45
    else:
        # Generic fallback by difficulty.
        if difficulty <= 2:
            base = 0.80
        elif difficulty == 3:
            base = 0.65
        elif difficulty == 4:
            base = 0.45
        else:
            base = 0.30

    # Small penalty for long transitions.
    if months >= 18:
        base -= 0.10
    elif months >= 12:
        base -= 0.05

    # Small penalty for high difficulty.
    if difficulty >= 5:
        base -= 0.15
    elif difficulty == 4:
        base -= 0.08

    return round(max(0.20, min(base, 0.95)), 2)


def main():
    if not TRANSITIONS_PATH.exists():
        raise FileNotFoundError(f"Cannot find {TRANSITIONS_PATH}")

    df = pd.read_csv(TRANSITIONS_PATH)

    if "transition_confidence" in df.columns:
        print("transition_confidence already exists. No changes made.")
        print(df["transition_confidence"].describe())
        return

    if not BACKUP_PATH.exists():
        shutil.copy2(TRANSITIONS_PATH, BACKUP_PATH)
        print(f"Backup saved to: {BACKUP_PATH}")
    else:
        print(f"Backup already exists: {BACKUP_PATH}")

    df["transition_confidence"] = df.apply(infer_confidence, axis=1)
    df.to_csv(TRANSITIONS_PATH, index=False, encoding="utf-8-sig")

    print(f"Updated: {TRANSITIONS_PATH}")
    print("\nConfidence distribution:")
    print(df["transition_confidence"].describe())

    print("\nSample transitions:")
    preview_cols = [
        "transition_id",
        "from_occupation_id",
        "to_occupation_id",
        "transition_type",
        "difficulty",
        "estimated_months",
        "transition_confidence",
    ]
    print(df[preview_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
