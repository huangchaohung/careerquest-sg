
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network


def _get_transition_rows(conn):
    return conn.execute("""
        SELECT
            source.name AS from_occupation,
            target.name AS to_occupation,
            ct.estimated_months,
            ct.estimated_cost,
            ct.difficulty,
            ct.transition_type
        FROM career_transitions ct
        JOIN occupations source ON ct.from_occupation_id = source.occupation_id
        JOIN occupations target ON ct.to_occupation_id = target.occupation_id
    """).fetchall()


def _extract_route_edges(route_summaries: Dict[str, Optional[dict]]) -> set[tuple[str, str]]:
    route_edges = set()

    for summary in route_summaries.values():
        if not summary:
            continue

        path_names = summary.get("path_names", [])
        for i in range(len(path_names) - 1):
            route_edges.add((path_names[i], path_names[i + 1]))

    return route_edges


def render_interactive_career_graph(
    conn,
    current_occupation: str,
    target_occupation: str,
    route_summaries: Dict[str, Optional[dict]],
    height: int = 620,
):
    """
    Render the full career transition graph.

    Highlights:
    - current node
    - target node
    - edges used in the displayed route strategies
    """

    rows = _get_transition_rows(conn)
    route_edges = _extract_route_edges(route_summaries)

    net = Network(
        height=f"{height}px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#1f2937",
    )

    net.barnes_hut(
        gravity=-22000,
        central_gravity=0.25,
        spring_length=170,
        spring_strength=0.03,
        damping=0.75,
    )

    all_nodes = set()
    for row in rows:
        all_nodes.add(row["from_occupation"])
        all_nodes.add(row["to_occupation"])

    for node in sorted(all_nodes):
        if node == current_occupation:
            color = "#2563eb"
            size = 28
            title = f"Starting profile: {node}"
        elif node == target_occupation:
            color = "#16a34a"
            size = 30
            title = f"Target occupation: {node}"
        elif node.startswith("Fresh Graduate"):
            color = "#9333ea"
            size = 20
            title = f"Fresh graduate profile: {node}"
        else:
            color = "#cbd5e1"
            size = 16
            title = node

        net.add_node(
            node,
            label=node,
            title=title,
            color=color,
            size=size,
        )

    for row in rows:
        source = row["from_occupation"]
        target = row["to_occupation"]
        is_route_edge = (source, target) in route_edges

        if is_route_edge:
            color = "#f97316"
            width = 4
        else:
            color = "#94a3b8"
            width = 1

        title = (
            f"{source} → {target}<br>"
            f"Time: {row['estimated_months']} months<br>"
            f"Cost: ${row['estimated_cost']:,.0f}<br>"
            f"Difficulty: {row['difficulty']}/5<br>"
            f"Type: {row['transition_type']}"
        )

        net.add_edge(
            source,
            target,
            title=title,
            color=color,
            width=width,
            arrows="to",
        )

    net.set_options("""
    const options = {
      "nodes": {
        "borderWidth": 1,
        "font": {
          "size": 14,
          "face": "arial"
        },
        "shape": "dot"
      },
      "edges": {
        "smooth": {
          "type": "dynamic"
        },
        "font": {
          "size": 10
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 120,
        "navigationButtons": true,
        "keyboard": true
      },
      "physics": {
        "enabled": true,
        "stabilization": {
          "iterations": 160
        }
      }
    }
    """)

    html_path = Path("career_graph.html")
    net.save_graph(str(html_path))
    html = html_path.read_text(encoding="utf-8")

    st.caption(
        "Legend: blue = starting profile, green = target role, purple = fresh graduate profile, orange edges = routes shown above."
    )
    components.html(html, height=height + 40, scrolling=True)
