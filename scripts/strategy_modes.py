"""
Step 4: Expanded strategy engine for CareerQuest SG.

New improvements:
1. Easiest route now minimizes the maximum difficulty of any single step,
   not the total difficulty. This is more intuitive for users.
2. Balanced route supports configurable weights.
3. You can print several candidate routes instead of only one.
"""

from collections import defaultdict
import heapq
from itertools import count


def get_transition_rows(conn):
    return conn.execute("""
        SELECT
            ct.*,
            source.name AS from_occupation,
            target.name AS to_occupation
        FROM career_transitions ct
        JOIN occupations source ON ct.from_occupation_id = source.occupation_id
        JOIN occupations target ON ct.to_occupation_id = target.occupation_id
    """).fetchall()


def get_normalization_max_values(conn):
    rows = get_transition_rows(conn)
    return {
        "estimated_months": max(row["estimated_months"] for row in rows),
        "estimated_cost": max(row["estimated_cost"] for row in rows),
        "difficulty": max(row["difficulty"] for row in rows),
    }


def calculate_edge_weight(row, strategy, max_values=None, balanced_weights=None):
    if strategy == "fastest":
        return row["estimated_months"]

    if strategy == "cheapest":
        return row["estimated_cost"]

    if strategy == "easiest":
        # Used only for normal shortest path fallback.
        # For true easiest, use find_easiest_path_by_max_step_difficulty().
        return row["difficulty"]

    if strategy == "balanced":
        if max_values is None:
            raise ValueError("max_values is required for balanced strategy.")

        if balanced_weights is None:
            balanced_weights = {
                "time": 0.4,
                "cost": 0.3,
                "difficulty": 0.3,
            }

        normalized_time = row["estimated_months"] / max_values["estimated_months"]
        normalized_cost = row["estimated_cost"] / max_values["estimated_cost"]
        normalized_difficulty = row["difficulty"] / max_values["difficulty"]

        return (
            balanced_weights["time"] * normalized_time
            + balanced_weights["cost"] * normalized_cost
            + balanced_weights["difficulty"] * normalized_difficulty
        )

    raise ValueError(f"Unknown strategy: {strategy}")


def build_strategy_graph(conn, strategy, balanced_weights=None):
    rows = get_transition_rows(conn)
    max_values = get_normalization_max_values(conn) if strategy == "balanced" else None
    graph = defaultdict(list)

    for row in rows:
        graph[row["from_occupation"]].append({
            "to": row["to_occupation"],
            "weight": calculate_edge_weight(row, strategy, max_values, balanced_weights),
            "estimated_months": row["estimated_months"],
            "estimated_cost": row["estimated_cost"],
            "difficulty": row["difficulty"],
            "transition_confidence": row["transition_confidence"] if "transition_confidence" in row.keys() else 0.6,
            "notes": row["notes"],
        })

    return graph


def find_best_path_by_strategy(conn, start, target, strategy, balanced_weights=None):
    if strategy == "easiest":
        return find_easiest_path_by_max_step_difficulty(conn, start, target)

    graph = build_strategy_graph(conn, strategy, balanced_weights=balanced_weights)

    tie_breaker = count()
    heap = [(0, next(tie_breaker), start, [])]
    best_seen = {}

    while heap:
        total_weight, _, current, path = heapq.heappop(heap)

        if current in best_seen and best_seen[current] <= total_weight:
            continue

        best_seen[current] = total_weight

        if current == target:
            return path, total_weight

        for edge in graph[current]:
            heapq.heappush(
                heap,
                (
                    total_weight + edge["weight"],
                    next(tie_breaker),
                    edge["to"],
                    path + [(current, edge)],
                ),
            )

    return None, None


def find_easiest_path_by_max_step_difficulty(conn, start, target):
    """
    Finds path that minimizes the hardest individual transition.
    Tie-breakers:
    1. Lower maximum step difficulty
    2. Lower total months
    3. Lower total cost
    """
    rows = get_transition_rows(conn)
    graph = defaultdict(list)

    for row in rows:
        graph[row["from_occupation"]].append({
            "to": row["to_occupation"],
            "estimated_months": row["estimated_months"],
            "estimated_cost": row["estimated_cost"],
            "difficulty": row["difficulty"],
            "transition_confidence": row["transition_confidence"] if "transition_confidence" in row.keys() else 0.6,
            "notes": row["notes"],
        })

    tie_breaker = count()
    heap = [(0, 0, 0, next(tie_breaker), start, [])]
    best_seen = {}

    while heap:
        max_difficulty, total_months, total_cost, _, current, path = heapq.heappop(heap)

        state_score = (max_difficulty, total_months, total_cost)
        if current in best_seen and best_seen[current] <= state_score:
            continue

        best_seen[current] = state_score

        if current == target:
            return path, max_difficulty

        for edge in graph[current]:
            new_max_difficulty = max(max_difficulty, edge["difficulty"])
            new_total_months = total_months + edge["estimated_months"]
            new_total_cost = total_cost + edge["estimated_cost"]

            heapq.heappush(
                heap,
                (
                    new_max_difficulty,
                    new_total_months,
                    new_total_cost,
                    next(tie_breaker),
                    edge["to"],
                    path + [(current, edge)],
                ),
            )

    return None, None


def summarize_path(start, path):
    if not path:
        return None

    path_names = [start] + [edge["to"] for _, edge in path]
    total_months = sum(edge["estimated_months"] for _, edge in path)
    total_cost = sum(edge["estimated_cost"] for _, edge in path)
    avg_difficulty = sum(edge["difficulty"] for _, edge in path) / len(path)
    max_difficulty = max(edge["difficulty"] for _, edge in path)
    avg_confidence = sum(edge.get("transition_confidence", 0.6) for _, edge in path) / len(path)

    return {
        "path_names": path_names,
        "total_months": total_months,
        "total_cost": total_cost,
        "avg_difficulty": avg_difficulty,
        "max_difficulty": max_difficulty,
        "steps": path,
        "avg_confidence": avg_confidence,
    }


def print_strategy_comparison(conn, start, target):
    print(f"\n=== Query 4: Strategy comparison from {start} to {target} ===")

    strategies = [
        ("fastest", "Fastest route"),
        ("cheapest", "Cheapest route"),
        ("easiest", "Easiest route"),
        ("balanced", "Balanced route"),
    ]

    for strategy, label in strategies:
        path, score = find_best_path_by_strategy(conn, start, target, strategy)
        summary = summarize_path(start, path)

        print(f"\n--- {label} ---")

        if summary is None:
            print("No route found.")
            continue

        print("Path:", " -> ".join(summary["path_names"]))
        print(f"Estimated months: {summary['total_months']}")
        print(f"Estimated cost: ${summary['total_cost']:,.0f}")
        print(f"Average difficulty: {summary['avg_difficulty']:.1f}/5")
        print(f"Hardest step difficulty: {summary['max_difficulty']}/5")

        if strategy == "balanced":
            print(f"Balanced score: {score:.3f}")

        print("Steps:")
        for i, (source, edge) in enumerate(summary["steps"], start=1):
            print(f"  {i}. {source} -> {edge['to']}")
