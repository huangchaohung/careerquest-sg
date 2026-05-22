from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRANSITIONS_PATH = PROJECT_ROOT / "data" / "raw" / "career_transitions.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "transition_confidence_report.csv"


def confidence_label(value: float) -> str:
    if value >= 0.75:
        return "High confidence"
    if value >= 0.50:
        return "Medium confidence"
    return "Exploratory"


def main():
    df = pd.read_csv(TRANSITIONS_PATH)

    if "transition_confidence" not in df.columns:
        raise ValueError("Missing transition_confidence column. Run scripts/add_transition_confidence.py first.")

    df["transition_confidence"] = pd.to_numeric(df["transition_confidence"], errors="coerce")

    invalid = df[
        df["transition_confidence"].isna()
        | (df["transition_confidence"] < 0)
        | (df["transition_confidence"] > 1)
    ]

    if not invalid.empty:
        print("Invalid confidence values found:")
        print(invalid.to_string(index=False))
        raise ValueError("Please fix invalid confidence values.")

    report = df.copy()
    report["confidence_label"] = report["transition_confidence"].apply(confidence_label)

    summary = (
        report.groupby(["transition_type", "confidence_label"])
        .size()
        .reset_index(name="count")
        .sort_values(["transition_type", "confidence_label"])
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")

    print("Transition confidence check passed.")
    print(f"Saved detailed report: {REPORT_PATH}")
    print("\nSummary by transition type:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
