from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

skills_path = BASE_DIR / "data" / "raw" / "skills.csv"
occupation_skills_path = BASE_DIR / "data" / "raw" / "occupation_skills.csv"
courses_path = BASE_DIR / "data" / "raw" / "courses.csv"

output_path = BASE_DIR / "data" / "processed" / "skill_course_coverage_report.csv"

skills_df = pd.read_csv(skills_path)
occupation_skills_df = pd.read_csv(occupation_skills_path)
courses_df = pd.read_csv(courses_path)

# Build lookups
skill_lookup = dict(zip(skills_df["skill_id"], skills_df["name"]))

occupation_skills_df["skill_name"] = occupation_skills_df["skill_id"].map(skill_lookup)

# Count occupation usage
usage_counts = (
    occupation_skills_df
    .groupby("skill_name")
    .size()
    .reset_index(name="used_by_occupations")
)

# Count importance 5 usage
importance_5_counts = (
    occupation_skills_df[occupation_skills_df["importance"] == 5]
    .groupby("skill_name")
    .size()
    .reset_index(name="importance_5_count")
)

# Count courses
if "skill_id" in courses_df.columns:
    course_counts = (
        courses_df
        .groupby("skill_id")
        .size()
        .reset_index(name="course_count")
    )

    course_counts["skill_name"] = course_counts["skill_id"].map(skill_lookup)
    course_counts = course_counts[["skill_name", "course_count"]]
else:
    course_counts = pd.DataFrame(columns=["skill_name", "course_count"])

# Merge
report_df = (
    skills_df[["name"]]
    .rename(columns={"name": "skill_name"})
    .merge(usage_counts, on="skill_name", how="left")
    .merge(importance_5_counts, on="skill_name", how="left")
    .merge(course_counts, on="skill_name", how="left")
)

report_df = report_df.fillna(0)

report_df["used_by_occupations"] = report_df["used_by_occupations"].astype(int)
report_df["importance_5_count"] = report_df["importance_5_count"].astype(int)
report_df["course_count"] = report_df["course_count"].astype(int)

report_df["coverage_status"] = report_df["course_count"].apply(
    lambda x: "OK" if x > 0 else "MISSING"
)

report_df = report_df.sort_values(
    by=["coverage_status", "importance_5_count", "used_by_occupations"],
    ascending=[True, False, False]
)

report_df.to_csv(output_path, index=False, encoding="utf-8-sig")

print("Saved coverage report:")
print(output_path)

missing_df = report_df[report_df["coverage_status"] == "MISSING"]

print("\\nTop missing skills:")
print(
    missing_df[
        ["skill_name", "used_by_occupations", "importance_5_count"]
    ].head(20).to_string(index=False)
)
