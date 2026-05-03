"""
CareerQuest SG - seed data loader and first milestone queries.

Default: uses SQLite so you can run it immediately with no database setup.
Later, you can adapt the same CSV files for PostgreSQL/MySQL.

Run from project root:
    python scripts/load_seed_data.py
"""

from pathlib import Path
import sqlite3
import pandas as pd
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "careerquest_seed.sqlite"

TABLES = [
    "occupations",
    "skills",
    "courses",
    "occupation_skills",
    "career_transitions",
]


def load_csvs_to_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)

    for table in TABLES:
        csv_path = DATA_DIR / f"{table}.csv"
        if not csv_path.exists():
            print(f"Skipping {table}: {csv_path} not found")
            continue

        df = pd.read_csv(csv_path)
        df.to_sql(table, conn, if_exists="replace", index=False)
        print(f"Loaded {len(df):>3} rows into {table}")

    return conn


def get_required_skills(conn: sqlite3.Connection, occupation_name: str) -> pd.DataFrame:
    query = """
    SELECT
        o.name AS occupation,
        s.name AS skill,
        s.category,
        os.importance
    FROM occupation_skills os
    JOIN occupations o ON os.occupation_id = o.occupation_id
    JOIN skills s ON os.skill_id = s.skill_id
    WHERE LOWER(o.name) = LOWER(?)
    ORDER BY os.importance DESC, s.name ASC;
    """
    return pd.read_sql_query(query, conn, params=(occupation_name,))


def build_career_graph(conn: sqlite3.Connection) -> nx.DiGraph:
    occupations = pd.read_sql_query("SELECT occupation_id, name FROM occupations", conn)
    transitions = pd.read_sql_query("SELECT * FROM career_transitions", conn)

    id_to_name = dict(zip(occupations["occupation_id"], occupations["name"]))

    graph = nx.DiGraph()
    for _, row in occupations.iterrows():
        graph.add_node(row["name"], occupation_id=int(row["occupation_id"]))

    for _, row in transitions.iterrows():
        source = id_to_name[row["from_occupation_id"]]
        target = id_to_name[row["to_occupation_id"]]
        graph.add_edge(
            source,
            target,
            estimated_months=int(row["estimated_months"]),
            estimated_cost=float(row["estimated_cost"]),
            difficulty=int(row["difficulty"]),
            notes=row["notes"],
        )

    return graph


def get_path(graph: nx.DiGraph, start: str, target: str, weight: str = "estimated_months"):
    try:
        path = nx.shortest_path(graph, start, target, weight=weight)
    except nx.NetworkXNoPath:
        return None

    steps = []
    total_months = 0
    total_cost = 0.0
    total_difficulty = 0

    for source, dest in zip(path[:-1], path[1:]):
        edge = graph[source][dest]
        total_months += edge["estimated_months"]
        total_cost += edge["estimated_cost"]
        total_difficulty += edge["difficulty"]
        steps.append({
            "from": source,
            "to": dest,
            "months": edge["estimated_months"],
            "cost": edge["estimated_cost"],
            "difficulty": edge["difficulty"],
            "notes": edge["notes"],
        })

    return {
        "path": path,
        "steps": steps,
        "total_months": total_months,
        "total_cost": total_cost,
        "total_difficulty": total_difficulty,
    }


def print_first_milestone_queries(conn: sqlite3.Connection):
    print("\n=== Query 1: What skills does Data Analyst need? ===")
    skills = get_required_skills(conn, "Data Analyst")
    print(skills.to_string(index=False))

    print("\n=== Query 2: What path from Administrative Executive to Data Analyst? ===")
    graph = build_career_graph(conn)
    result = get_path(graph, "Administrative Executive", "Data Analyst")

    if result is None:
        print("No path found.")
        return

    print("Path:", " -> ".join(result["path"]))
    print(f"Total estimated months: {result['total_months']}")
    print(f"Total estimated cost: ${result['total_cost']:,.0f}")
    print(f"Total difficulty score: {result['total_difficulty']}")
    print("\nSteps:")
    for i, step in enumerate(result["steps"], start=1):
        print(f"{i}. {step['from']} -> {step['to']}")
        print(f"   Time: {step['months']} months | Cost: ${step['cost']:,.0f} | Difficulty: {step['difficulty']}/5")
        print(f"   Notes: {step['notes']}")


if __name__ == "__main__":
    conn = load_csvs_to_sqlite()
    print_first_milestone_queries(conn)
    conn.close()
    print(f"\nSQLite database created at: {DB_PATH}")
