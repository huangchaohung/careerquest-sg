
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
from collections import defaultdict, deque

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network


PATH_ORANGE = "#f97316"
START_GREEN = "#22c55e"
GOAL_RED = "#ef4444"
FOCUS_PURPLE = "#9333ea"
UNRELATED_GREY = "#cbd5e1"


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


def _extract_necessary_nodes(
    current_occupation: str,
    target_occupation: str,
    route_summaries: Dict[str, Optional[dict]],
) -> set[str]:
    nodes = {current_occupation, target_occupation}

    for summary in route_summaries.values():
        if not summary:
            continue
        nodes.update(summary.get("path_names", []))

    return nodes


def _build_undirected_adjacency(rows):
    adjacency = defaultdict(set)

    for row in rows:
        source = row["from_occupation"]
        target = row["to_occupation"]
        adjacency[source].add(target)
        adjacency[target].add(source)

    return adjacency


def _nodes_within_degree(rows, seed_nodes: set[str], max_degree: int = 2) -> set[str]:
    adjacency = _build_undirected_adjacency(rows)

    visible = set(seed_nodes)
    queue = deque((node, 0) for node in seed_nodes)

    while queue:
        node, degree = queue.popleft()

        if degree >= max_degree:
            continue

        for neighbor in adjacency.get(node, []):
            if neighbor not in visible:
                visible.add(neighbor)
                queue.append((neighbor, degree + 1))

    return visible


def _font_config(color: str, size: int, bold: bool = False) -> dict:
    return {
        "color": color,
        "size": size,
        "face": "Arial Black" if bold else "arial",
        "vadjust": 0,
        "strokeWidth": 0,
    }


def render_interactive_career_graph(
    conn,
    current_occupation: str,
    target_occupation: str,
    route_summaries: Dict[str, Optional[dict]],
    height: int = 620,
    max_degree_from_path: int = 2,
):
    rows = _get_transition_rows(conn)
    route_edges = _extract_route_edges(route_summaries)
    necessary_nodes = _extract_necessary_nodes(
        current_occupation=current_occupation,
        target_occupation=target_occupation,
        route_summaries=route_summaries,
    )
    visible_nodes = _nodes_within_degree(
        rows=rows,
        seed_nodes=necessary_nodes,
        max_degree=max_degree_from_path,
    )

    filtered_rows = [
        row for row in rows
        if row["from_occupation"] in visible_nodes and row["to_occupation"] in visible_nodes
    ]

    net = Network(
        height=f"{height}px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#1f2937",
    )

    net.barnes_hut(
        gravity=-24000,
        central_gravity=0.22,
        spring_length=170,
        spring_strength=0.03,
        damping=0.78,
    )

    all_nodes = set()
    for row in filtered_rows:
        all_nodes.add(row["from_occupation"])
        all_nodes.add(row["to_occupation"])

    all_nodes.update(necessary_nodes)

    for node in sorted(all_nodes):
        color = UNRELATED_GREY
        border = "#94a3b8"
        size = 16
        title = node
        font = _font_config("#1f2937", 14, bold=False)
        node_role = "normal"

        if node == current_occupation:
            color = START_GREEN
            border = "#15803d"
            size = 32
            title = f"Starting role: {node}"
            font = _font_config(START_GREEN, 20, bold=True)
            node_role = "start"

        elif node == target_occupation:
            color = GOAL_RED
            border = "#b91c1c"
            size = 34
            title = f"Goal role: {node}"
            font = _font_config(GOAL_RED, 20, bold=True)
            node_role = "goal"

        elif node in necessary_nodes:
            color = "#fed7aa"
            border = PATH_ORANGE
            size = 24
            title = f"Role on displayed pathway: {node}"
            font = _font_config(PATH_ORANGE, 18, bold=True)
            node_role = "path"

        net.add_node(
            node,
            label=node,  # IMPORTANT: plain text only, no HTML
            title=title,
            color={
                "background": color,
                "border": border,
                "highlight": {
                    "background": color,
                    "border": FOCUS_PURPLE,
                },
                "hover": {
                    "background": color,
                    "border": FOCUS_PURPLE,
                },
            },
            font=font,
            size=size,
            node_role=node_role,
        )

    for row in filtered_rows:
        source = row["from_occupation"]
        target = row["to_occupation"]
        is_route_edge = (source, target) in route_edges

        if is_route_edge:
            color = PATH_ORANGE
            width = 4
            title_prefix = "Highlighted strategy path"
        else:
            color = "#94a3b8"
            width = 1
            title_prefix = "Related transition"

        title = (
            f"{title_prefix}<br>"
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
            color={
                "color": color,
                "highlight": FOCUS_PURPLE,
                "hover": FOCUS_PURPLE,
            },
            width=width,
            arrows="to",
        )

    net.set_options("""
    const options = {
      "nodes": {
        "borderWidth": 2,
        "font": {
          "size": 14,
          "face": "arial",
          "color": "#1f2937",
          "multi": "html"
        },
        "shape": "dot",
        "scaling": {
          "min": 12,
          "max": 36
        }
      },
      "edges": {
        "smooth": {
          "type": "dynamic"
        },
        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.9
          }
        },
        "font": {
          "size": 10
        },
        "selectionWidth": 2,
        "hoverWidth": 2
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 120,
        "navigationButtons": true,
        "keyboard": true,
        "selectConnectedEdges": true
      },
      "physics": {
        "enabled": true,
        "stabilization": {
          "iterations": 180
        }
      }
    }
    """)

    html_path = Path("career_graph.html")
    net.save_graph(str(html_path))
    html_content = html_path.read_text(encoding="utf-8")

    focus_script = """
    <script type="text/javascript">
    (function() {
      const PATH_ORANGE = "#f97316";
      const START_GREEN = "#22c55e";
      const GOAL_RED = "#ef4444";
      const FOCUS_PURPLE = "#9333ea";

      function fontConfig(color, size, bold) {
        return {
          color: color,
          size: size,
          face: bold ? "Arial Black" : "arial",
          vadjust: 0,
          strokeWidth: 0
        };
      }

      function enforceBasePathFonts() {
        const currentNodes = nodes.get();

        currentNodes.forEach(function(node) {
          if (node.node_role === "start") {
            nodes.update({
              id: node.id,
              label: node.id,
              font: fontConfig(START_GREEN, 22, true)
            });
          } else if (node.node_role === "goal") {
            nodes.update({
              id: node.id,
              label: node.id,
              font: fontConfig(GOAL_RED, 22, true)
            });
          } else if (node.node_role === "path") {
            nodes.update({
              id: node.id,
              label: node.id,
              font: fontConfig(PATH_ORANGE, 20, true)
            });
          } else {
            nodes.update({
              id: node.id,
              label: node.id
            });
          }
        });
      }

      const originalNodes = {};
      const originalEdges = {};

      enforceBasePathFonts();

      nodes.get().forEach(function(node) {
        originalNodes[node.id] = {
          label: node.id,
          color: JSON.parse(JSON.stringify(node.color || {})),
          font: JSON.parse(JSON.stringify(node.font || {})),
          size: node.size || 16,
          node_role: node.node_role || "normal"
        };
      });

      edges.get().forEach(function(edge) {
        originalEdges[edge.id] = {
          color: JSON.parse(JSON.stringify(edge.color || {})),
          width: edge.width || 1
        };
      });

      function withOpacity(hex, opacity) {
        if (!hex || typeof hex !== "string" || !hex.startsWith("#") || hex.length !== 7) {
          return hex;
        }
        const alpha = Math.round(opacity * 255).toString(16).padStart(2, "0");
        return hex + alpha;
      }

      function fadeColorObject(colorObj, opacity) {
        if (!colorObj || typeof colorObj !== "object") {
          return colorObj;
        }

        const cloned = JSON.parse(JSON.stringify(colorObj));

        if (cloned.background) cloned.background = withOpacity(cloned.background, opacity);
        if (cloned.border) cloned.border = withOpacity(cloned.border, opacity);
        if (cloned.color) cloned.color = withOpacity(cloned.color, opacity);

        if (cloned.highlight) {
          if (cloned.highlight.background) cloned.highlight.background = withOpacity(cloned.highlight.background, opacity);
          if (cloned.highlight.border) cloned.highlight.border = withOpacity(cloned.highlight.border, opacity);
        }

        if (cloned.hover) {
          if (cloned.hover.background) cloned.hover.background = withOpacity(cloned.hover.background, opacity);
          if (cloned.hover.border) cloned.hover.border = withOpacity(cloned.hover.border, opacity);
        }

        return cloned;
      }

      function resetGraph(refit) {
        nodes.get().forEach(function(node) {
          const original = originalNodes[node.id];
          if (!original) return;

          nodes.update({
            id: node.id,
            label: original.label,
            color: JSON.parse(JSON.stringify(original.color)),
            font: JSON.parse(JSON.stringify(original.font)),
            size: original.size
          });
        });

        edges.get().forEach(function(edge) {
          const original = originalEdges[edge.id];
          if (!original) return;

          edges.update({
            id: edge.id,
            color: JSON.parse(JSON.stringify(original.color)),
            width: original.width
          });
        });

        if (refit) {
          network.unselectAll();
        }
      }

      function focusNode(nodeId, persistFade) {
        const connectedEdges = network.getConnectedEdges(nodeId);
        const connectedNodes = network.getConnectedNodes(nodeId);
        const connectedNodeSet = new Set(connectedNodes);
        connectedNodeSet.add(nodeId);

        resetGraph(false);

        nodes.get().forEach(function(node) {
          const original = originalNodes[node.id];
          if (!original) return;

          if (node.id === nodeId) {
            nodes.update({
              id: node.id,
              label: node.id,
              color: {
                background: original.color.background || "#ffffff",
                border: FOCUS_PURPLE,
                highlight: {
                  background: original.color.background || "#ffffff",
                  border: FOCUS_PURPLE
                },
                hover: {
                  background: original.color.background || "#ffffff",
                  border: FOCUS_PURPLE
                }
              },
              font: fontConfig(FOCUS_PURPLE, 17, false)
            });
          } else if (connectedNodeSet.has(node.id)) {
            nodes.update({
              id: node.id,
              label: node.id,
              color: {
                background: original.color.background || "#ffffff",
                border: FOCUS_PURPLE,
                highlight: {
                  background: original.color.background || "#ffffff",
                  border: FOCUS_PURPLE
                },
                hover: {
                  background: original.color.background || "#ffffff",
                  border: FOCUS_PURPLE
                }
              },
              font: fontConfig(FOCUS_PURPLE, 16, false)
            });
          } else if (persistFade) {
            nodes.update({
              id: node.id,
              color: fadeColorObject(original.color, 0.30),
              font: fontConfig("#9ca3af", 13, false)
            });
          }
        });

        connectedEdges.forEach(function(edgeId) {
          const original = originalEdges[edgeId];
          edges.update({
            id: edgeId,
            color: {
              color: FOCUS_PURPLE,
              highlight: FOCUS_PURPLE,
              hover: FOCUS_PURPLE
            },
            width: original ? original.width : 1
          });
        });

        if (persistFade) {
          edges.get().forEach(function(edge) {
            if (!connectedEdges.includes(edge.id)) {
              const original = originalEdges[edge.id];
              if (!original) return;

              let color = JSON.parse(JSON.stringify(original.color));

              if (color && typeof color === "object" && color.color) {
                color = {
                  ...color,
                  color: withOpacity(color.color, 0.25),
                  highlight: withOpacity(color.highlight || color.color, 0.25),
                  hover: withOpacity(color.hover || color.color, 0.25)
                };
              }

              edges.update({
                id: edge.id,
                color: color,
                width: original.width
              });
            }
          });
        }
      }

      let selectedNode = null;

      network.once("afterDrawing", function() {
        enforceBasePathFonts();
      });

      network.on("hoverNode", function(params) {
        if (selectedNode === null) {
          focusNode(params.node, false);
        }
      });

      network.on("blurNode", function(params) {
        if (selectedNode === null) {
          resetGraph(false);
        }
      });

      network.on("selectNode", function(params) {
        if (params.nodes.length > 0) {
          selectedNode = params.nodes[0];
          focusNode(selectedNode, true);
        }
      });

      network.on("deselectNode", function(params) {
        selectedNode = null;
        resetGraph(false);
      });

      network.on("click", function(params) {
        if (params.nodes.length === 0) {
          selectedNode = null;
          resetGraph(true);
        }
      });
    })();
    </script>
    """

    if "</body>" in html_content:
        html_content = html_content.replace("</body>", focus_script + "\n</body>")
    else:
        html_content += focus_script

    st.caption(
        f"Legend: green = starting role, red = goal role, orange arrows = displayed strategy path. "
        f"Path role labels are coloured and enlarged; hover/click highlights adjacent roles and arrows in purple. "
        f"Graph shows roles within degree {max_degree_from_path} of the start/goal/path roles."
    )
    components.html(html_content, height=height + 50, scrolling=True)
