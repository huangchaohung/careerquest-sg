"""
Step 5: Employability / Chance Scoring for CareerQuest SG.

This module estimates the user's chance of reaching a target occupation.

The score is deliberately transparent and explainable. It is not meant to be
a perfect prediction model. For this portfolio project, the goal is to show
decision-support logic.

Core score components:
1. Skill match score
2. Demand score
3. Salary progression feasibility
4. Path difficulty score

Final score:
    chance_score = weighted combination of the above
"""

from strategy_modes import find_best_path_by_strategy, summarize_path


def clamp(value, lower=0.0, upper=1.0):
    return max(lower, min(value, upper))


def get_occupation(conn, occupation_name):
    row = conn.execute(
        "SELECT * FROM occupations WHERE name = ?",
        (occupation_name,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Occupation not found: {occupation_name}")

    return row


def get_skills_for_occupation(conn, occupation_name):
    return conn.execute("""
        SELECT
            s.skill_id,
            s.name AS skill,
            s.category,
            os.importance
        FROM occupation_skills os
        JOIN occupations o ON os.occupation_id = o.occupation_id
        JOIN skills s ON os.skill_id = s.skill_id
        WHERE o.name = ?
    """, (occupation_name,)).fetchall()


def calculate_skill_match_score(conn, current_occupation, target_occupation):
    """
    Weighted skill match.

    If the target role needs highly important skills, missing them hurts more.
    """
    current_skills = get_skills_for_occupation(conn, current_occupation)
    target_skills = get_skills_for_occupation(conn, target_occupation)

    current_skill_ids = {row["skill_id"] for row in current_skills}

    total_weight = sum(row["importance"] for row in target_skills)
    matched_weight = sum(
        row["importance"]
        for row in target_skills
        if row["skill_id"] in current_skill_ids
    )

    if total_weight == 0:
        return 0.0

    return matched_weight / total_weight


def calculate_demand_score(conn, target_occupation):
    """
    Uses target occupation demand_score from occupations table.
    """
    target = get_occupation(conn, target_occupation)
    return clamp(float(target["demand_score"]))


def calculate_salary_feasibility_score(conn, current_occupation, target_occupation):
    """
    Simple salary transition feasibility.

    A larger salary jump is treated as more difficult.
    This is not saying the transition is impossible; it only means it likely
    requires more preparation.

    Score intuition:
    - same/lower salary target: high feasibility
    - moderate salary jump: medium-high
    - large salary jump: lower
    """
    current = get_occupation(conn, current_occupation)
    target = get_occupation(conn, target_occupation)

    current_salary = float(current["salary_median"])
    target_salary = float(target["salary_median"])

    if current_salary <= 0:
        return 0.5

    salary_jump_ratio = (target_salary - current_salary) / current_salary

    if salary_jump_ratio <= 0:
        return 1.0

    # A 100% salary jump gives approximately 0.4 feasibility.
    score = 1.0 - (0.6 * min(salary_jump_ratio, 1.0))
    return clamp(score)


def calculate_path_difficulty_score(conn, current_occupation, target_occupation):
    """
    Converts the easiest path's hardest step difficulty into a 0-1 score.
    """
    path, _ = find_best_path_by_strategy(
        conn,
        current_occupation,
        target_occupation,
        strategy="easiest",
    )

    summary = summarize_path(current_occupation, path)

    if summary is None:
        return 0.0, None

    hardest = summary["max_difficulty"]

    # difficulty 1 -> 1.0, difficulty 5 -> 0.2
    score = 1.0 - ((hardest - 1) / 5)
    return clamp(score), summary


def calculate_chance_score(conn, current_occupation, target_occupation):
    """
    Final explainable chance score.
    """
    skill_match = calculate_skill_match_score(conn, current_occupation, target_occupation)
    demand = calculate_demand_score(conn, target_occupation)
    salary_feasibility = calculate_salary_feasibility_score(conn, current_occupation, target_occupation)
    path_difficulty, easiest_path_summary = calculate_path_difficulty_score(
        conn,
        current_occupation,
        target_occupation,
    )

    weights = {
        "skill_match": 0.45,
        "demand": 0.20,
        "salary_feasibility": 0.15,
        "path_difficulty": 0.20,
    }

    chance = (
        weights["skill_match"] * skill_match
        + weights["demand"] * demand
        + weights["salary_feasibility"] * salary_feasibility
        + weights["path_difficulty"] * path_difficulty
    )

    return {
        "chance_score": clamp(chance),
        "skill_match": skill_match,
        "demand": demand,
        "salary_feasibility": salary_feasibility,
        "path_difficulty": path_difficulty,
        "weights": weights,
        "easiest_path_summary": easiest_path_summary,
    }


def score_to_label(score):
    if score >= 0.75:
        return "Strong"
    if score >= 0.55:
        return "Moderate"
    if score >= 0.35:
        return "Challenging but possible"
    return "High-risk transition"


def get_missing_high_importance_skills(conn, current_occupation, target_occupation):
    current_skills = get_skills_for_occupation(conn, current_occupation)
    target_skills = get_skills_for_occupation(conn, target_occupation)

    current_skill_ids = {row["skill_id"] for row in current_skills}

    missing = [
        row for row in target_skills
        if row["skill_id"] not in current_skill_ids
    ]

    return sorted(missing, key=lambda row: (-row["importance"], row["skill"]))


def print_chance_analysis(conn, current_occupation, target_occupation):
    print(
        f"\n=== Query 5: What are my chances of moving from "
        f"{current_occupation} to {target_occupation}? ==="
    )

    result = calculate_chance_score(conn, current_occupation, target_occupation)
    chance_pct = result["chance_score"] * 100

    print(f"Estimated chance score: {chance_pct:.1f}%")
    print(f"Transition label: {score_to_label(result['chance_score'])}")

    print("\nScore breakdown:")
    print(f"- Skill match: {result['skill_match'] * 100:.1f}%")
    print(f"- Target-role demand: {result['demand'] * 100:.1f}%")
    print(f"- Salary feasibility: {result['salary_feasibility'] * 100:.1f}%")
    print(f"- Path difficulty support: {result['path_difficulty'] * 100:.1f}%")

    missing_skills = get_missing_high_importance_skills(
        conn,
        current_occupation,
        target_occupation,
    )

    print("\nMain blockers:")
    for skill in missing_skills[:5]:
        print(f"- {skill['skill']} (importance {skill['importance']}/5)")

    easiest_path = result["easiest_path_summary"]
    if easiest_path:
        print("\nLowest-difficulty route:")
        print(" -> ".join(easiest_path["path_names"]))
        print(f"Estimated months: {easiest_path['total_months']}")
        print(f"Estimated cost: ${easiest_path['total_cost']:,.0f}")
        print(f"Hardest step difficulty: {easiest_path['max_difficulty']}/5")

    print("\nSuggested interpretation:")
    if result["skill_match"] < 0.4:
        print("- Your current profile has a large skill gap. Focus on foundational technical skills first.")
    elif result["skill_match"] < 0.7:
        print("- You already have some transferable skills. Focus on closing the highest-importance gaps.")
    else:
        print("- Your skill profile is already close to the target role. Focus on portfolio evidence and applications.")

    if result["demand"] >= 0.75:
        print("- The target role has relatively strong demand in the current dataset.")
    else:
        print("- The target role has moderate or uncertain demand in the current dataset.")

    if result["path_difficulty"] < 0.5:
        print("- The transition path includes a difficult jump. Consider an intermediate role first.")
    else:
        print("- The transition path is reasonably manageable based on the current career graph.")
