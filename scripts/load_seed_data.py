import csv
import sqlite3
from pathlib import Path
from collections import defaultdict
import heapq
from itertools import count
from strategy_modes import print_strategy_comparison
from chance_scoring import print_chance_analysis

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "raw"
DB_PATH = BASE_DIR / "careerquest_seed.sqlite"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


def load_csv(conn, table_name, csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return

    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_names = ", ".join(columns)

    values = [[row[col] for col in columns] for row in rows]

    conn.executemany(
        f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",
        values,
    )


def init_db():
    if DB_PATH.exists():
        DB_PATH.unlink()   # delete old DB file

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)

    load_csv(conn, "occupations", DATA_DIR / "occupations.csv")
    load_csv(conn, "skills", DATA_DIR / "skills.csv")
    load_csv(conn, "occupation_skills", DATA_DIR / "occupation_skills.csv")
    load_csv(conn, "career_transitions", DATA_DIR / "career_transitions.csv")
    load_csv(conn, "courses", DATA_DIR / "courses.csv")

    conn.commit()
    return conn


def get_occupation_id(conn, occupation_name):
    row = conn.execute(
        "SELECT occupation_id FROM occupations WHERE name = ?",
        (occupation_name,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Occupation not found: {occupation_name}")

    return row["occupation_id"]


def get_required_skills(conn, occupation_name):
    query = """
    SELECT
        o.name AS occupation,
        s.skill_id,
        s.name AS skill,
        s.category,
        os.importance
    FROM occupation_skills os
    JOIN occupations o ON os.occupation_id = o.occupation_id
    JOIN skills s ON os.skill_id = s.skill_id
    WHERE o.name = ?
    ORDER BY os.importance DESC, s.name ASC
    """

    return conn.execute(query, (occupation_name,)).fetchall()


def print_required_skills(conn, occupation_name):
    rows = get_required_skills(conn, occupation_name)

    print(f"\n=== Query 1: What skills does {occupation_name} need? ===")
    print(f"{'occupation':<28} {'skill':<40} {'category':<25} {'importance'}")

    for row in rows:
        print(
            f"{row['occupation']:<28} "
            f"{row['skill']:<40} "
            f"{row['category']:<25} "
            f"{row['importance']}"
        )


def build_transition_graph(conn, weight_mode="estimated_months"):
    rows = conn.execute("""
        SELECT
            ct.*,
            source.name AS from_occupation,
            target.name AS to_occupation
        FROM career_transitions ct
        JOIN occupations source ON ct.from_occupation_id = source.occupation_id
        JOIN occupations target ON ct.to_occupation_id = target.occupation_id
    """).fetchall()

    graph = defaultdict(list)

    for row in rows:
        graph[row["from_occupation"]].append({
            "to": row["to_occupation"],
            "weight": row[weight_mode],
            "estimated_months": row["estimated_months"],
            "estimated_cost": row["estimated_cost"],
            "difficulty": row["difficulty"],
            "notes": row["notes"],
        })

    return graph


def shortest_path(conn, start, target, weight_mode="estimated_months"):
    graph = build_transition_graph(conn, weight_mode=weight_mode)

    counter = count()
    heap = [(0, next(counter), start, [])]
    visited = set()

    while heap:
        total_weight, _, current, path = heapq.heappop(heap)

        if current in visited:
            continue

        visited.add(current)

        if current == target:
            return path

        for edge in graph[current]:
            if edge["to"] not in visited:
                heapq.heappush(
                    heap,
                    (
                        total_weight + edge["weight"],
                        next(counter),
                        edge["to"],
                        path + [(current, edge)],
                    ),
                )

    return None


def print_path(conn, start, target):
    path = shortest_path(conn, start, target, weight_mode="estimated_months")

    print(f"\n=== Query 2: What path from {start} to {target}? ===")

    if not path:
        print("No path found.")
        return

    path_names = [start] + [edge["to"] for _, edge in path]
    total_months = sum(edge["estimated_months"] for _, edge in path)
    total_cost = sum(edge["estimated_cost"] for _, edge in path)
    total_difficulty = sum(edge["difficulty"] for _, edge in path)
    avg_difficulty = total_difficulty / len(path)

    print("Path:", " -> ".join(path_names))
    print(f"Total estimated months: {total_months}")
    print(f"Total estimated cost: ${total_cost:,.0f}")
    print(f"Average difficulty: {avg_difficulty:.1f}/5")

    print("\nSteps:")
    for i, (source, edge) in enumerate(path, start=1):
        print(f"{i}. {source} -> {edge['to']}")
        print(
            f"   Time: {edge['estimated_months']} months | "
            f"Cost: ${edge['estimated_cost']:,.0f} | "
            f"Difficulty: {edge['difficulty']}/5"
        )
        print(f"   Notes: {edge['notes']}")


def get_missing_skills(conn, current_occupation, target_occupation, minimum_importance=3):
    current_skills = get_required_skills(conn, current_occupation)
    target_skills = get_required_skills(conn, target_occupation)

    current_skill_ids = {row["skill_id"] for row in current_skills}

    missing = [
        row for row in target_skills
        if row["skill_id"] not in current_skill_ids
        and row["importance"] >= minimum_importance
    ]

    return missing


def recommend_courses_for_missing_skills(conn, missing_skills, max_courses_per_skill=1):
    recommendations = []

    for skill in missing_skills:
        rows = conn.execute("""
            SELECT
                c.course_id,
                c.title,
                c.provider,
                c.cost,
                c.duration_hours,
                c.difficulty,
                c.source_url,
                s.name AS skill
            FROM courses c
            JOIN skills s ON c.skill_id = s.skill_id
            WHERE c.skill_id = ?
            ORDER BY c.cost ASC, c.duration_hours ASC
            LIMIT ?
        """, (skill["skill_id"], max_courses_per_skill)).fetchall()

        for row in rows:
            recommendations.append({
                "skill": row["skill"],
                "importance": skill["importance"],
                "title": row["title"],
                "provider": row["provider"],
                "cost": row["cost"],
                "duration_hours": row["duration_hours"],
                "difficulty": row["difficulty"],
                "source_url": row["source_url"],
            })

    return recommendations


def print_course_plan(conn, current_occupation, target_occupation):
    print(
        f"\n=== Query 3: What courses should {current_occupation} take "
        f"to become {target_occupation}? ==="
    )

    missing_skills = get_missing_skills(conn, current_occupation, target_occupation)
    recommendations = recommend_courses_for_missing_skills(conn, missing_skills)

    if not missing_skills:
        print("No missing skills found based on current V1 mappings.")
        return

    print("\nMissing target-role skills:")
    for skill in missing_skills:
        print(f"- {skill['skill']} ({skill['category']}, importance {skill['importance']}/5)")

    print("\nRecommended course quests:")
    total_cost = 0
    total_hours = 0

    for i, course in enumerate(recommendations, start=1):
        total_cost += course["cost"]
        total_hours += course["duration_hours"]

        print(f"{i}. {course['title']}")
        print(f"   Unlocks skill: {course['skill']} | Importance: {course['importance']}/5")
        print(
            f"   Provider: {course['provider']} | "
            f"Cost: ${course['cost']:,.0f} | "
            f"Duration: {course['duration_hours']:.0f} hours | "
            f"Difficulty: {course['difficulty']}"
        )

    print("\nEstimated course plan total:")
    print(f"Total course cost: ${total_cost:,.0f}")
    print(f"Total course duration: {total_hours:.0f} hours")
    print(f"Approximate study time at 6 hours/week: {total_hours / 6:.1f} weeks")


def main():
    conn = init_db()

    print_required_skills(conn, "Data Analyst")
    print_path(conn, "Administrative Executive", "Data Analyst")
    print_course_plan(conn, "Administrative Executive", "Data Analyst")
    print_strategy_comparison(conn, "Administrative Executive", "Data Analyst")
    print_chance_analysis(conn, "Administrative Executive", "Data Analyst")

    print(f"\nSQLite database created at: {DB_PATH}")


if __name__ == "__main__":
    main()
