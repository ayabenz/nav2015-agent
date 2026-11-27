"""CALL-graph-expanded Table footprints for candidate NAV processes.

Clusters are evidence-backed investigation groups, not confirmed business processes.
"""
from __future__ import annotations

import sqlite3
from collections import deque
from typing import Any

from .process_discovery import discover_process_entrypoints


def _reachable_call_nodes(
    graph: sqlite3.Connection, object_node: str, max_depth: int, max_nodes: int,
) -> dict[str, Any]:
    procedures = {
        str(row[0]) for row in graph.execute(
            "SELECT node FROM procedures WHERE object_node=?", (object_node,)
        ).fetchall()
    }
    starts = sorted(procedures | {object_node, f"{object_node} TRIGGERS"})
    adjacency: dict[str, list[str]] = {}
    for src, dst in graph.execute(
        "SELECT src,dst FROM edges WHERE kind='CALL' ORDER BY src,dst"
    ):
        adjacency.setdefault(str(src), []).append(str(dst))
    known_procedures = {
        str(row[0]) for row in graph.execute("SELECT node FROM procedures").fetchall()
    }
    depths: dict[str, int] = {}
    parents: dict[str, str] = {}
    queue = deque()
    for node in starts:
        depths[node] = 0
        queue.append(node)
    unresolved: set[tuple[str, str]] = set()
    truncated = False
    while queue:
        node = queue.popleft()
        depth = depths[node]
        if depth >= max_depth:
            continue
        for target in adjacency.get(node, []):
            if target not in known_procedures:
                unresolved.add((node, target))
                continue
            if target in depths:
                continue
            if len(depths) >= max_nodes:
                truncated = True
                queue.clear()
                break
            depths[target] = depth + 1
            parents[target] = node
            queue.append(target)
    paths: dict[str, list[str]] = {}
    for node in depths:
        path = [node]
        parent = parents.get(node)
        while parent:
            path.append(parent)
            parent = parents.get(parent)
        paths[node] = list(reversed(path))
    return {
        "nodes": depths,
        "paths": paths,
        "unresolved_call_targets": [
            {"src": src, "dst": dst, "reason": "CALL target is not an indexed procedure"}
            for src, dst in sorted(unresolved)
        ],
        "truncated": truncated,
        "procedure_nodes": sorted(node for node in depths if node in known_procedures),
    }


def map_candidate_processes(
    graph: sqlite3.Connection,
    limit: int = 200,
    include_standard: bool = False,
    min_similarity: float = 0.25,
    max_depth: int = 5,
    max_nodes_per_candidate: int = 5000,
) -> dict[str, Any]:
    """Group ranked candidates by Table usage across bounded CALL-reachable procedures."""
    if not 0.0 < min_similarity <= 1.0:
        raise ValueError("min_similarity must be greater than 0 and at most 1")
    if max_depth < 0:
        raise ValueError("max_depth must be zero or greater")
    if max_nodes_per_candidate < 1:
        raise ValueError("max_nodes_per_candidate must be at least 1")

    discovery = discover_process_entrypoints(
        graph, limit=limit, include_standard=include_standard
    )
    mapped: list[dict[str, Any]] = []
    for candidate in discovery["candidates"]:
        traversal = _reachable_call_nodes(
            graph, candidate["object"], max_depth, max_nodes_per_candidate
        )
        reachable = sorted(traversal["nodes"])
        placeholders = ",".join("?" for _ in reachable)
        rows = graph.execute(
            "SELECT src,src_object,table_node,table_name,usage,count,new_vs_original "
            f"FROM table_usage WHERE src IN ({placeholders}) ORDER BY src,table_node,usage",
            reachable,
        ).fetchall() if reachable else []
        table_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row["table_node"])
            entry = table_map.setdefault(key, {
                "table": key,
                "name": row["table_name"],
                "usages": [],
                "reference_count": 0,
                "contributing_procedures": [],
                "contributing_call_paths": [],
                "new_vs_original_count": 0,
            })
            usage = str(row["usage"])
            if usage not in entry["usages"]:
                entry["usages"].append(usage)
            entry["reference_count"] += int(row["count"] or 0)
            entry["new_vs_original_count"] += int(row["new_vs_original"] or 0)
            if row["src"] not in entry["contributing_procedures"]:
                entry["contributing_procedures"].append(str(row["src"]))
                entry["contributing_call_paths"].append(traversal["paths"].get(str(row["src"]), [str(row["src"])]))
        mapped.append({
            **candidate,
            "reachable_procedure_count": len(traversal["procedure_nodes"]),
            "reachable_node_count": len(reachable),
            "reachable_procedures": [
                {"node": node, "depth": traversal["nodes"][node],
                 "call_path": traversal["paths"][node]}
                for node in traversal["procedure_nodes"]
            ],
            "tables": sorted(table_map.values(), key=lambda item: item["table"]),
            "table_ids": sorted(table_map),
            "unresolved_call_targets": traversal["unresolved_call_targets"],
            "truncated": traversal["truncated"],
            "traversal_limits": {
                "max_depth": max_depth, "max_nodes": max_nodes_per_candidate,
            },
        })

    parent = list(range(len(mapped)))

    def find(index: int) -> int:
        if parent[index] != index:
            parent[index] = find(parent[index])
        return parent[index]

    similarities: list[dict[str, Any]] = []
    for left in range(len(mapped)):
        left_tables = set(mapped[left]["table_ids"])
        for right in range(left + 1, len(mapped)):
            right_tables = set(mapped[right]["table_ids"])
            shared = sorted(left_tables & right_tables)
            if not shared:
                continue
            union = left_tables | right_tables
            score = len(shared) / len(union) if union else 0.0
            if score < min_similarity:
                continue
            a, b = find(left), find(right)
            if a != b:
                parent[b] = a
            similarities.append({
                "left": mapped[left]["object"],
                "right": mapped[right]["object"],
                "shared_tables": shared,
                "jaccard_similarity": round(score, 4),
                "evidence": "shared_table_usage_in_call_reachable_procedures",
                "runtime_executed": False,
            })

    groups: dict[int, list[int]] = {}
    for index in range(len(mapped)):
        groups.setdefault(find(index), []).append(index)
    clusters = []
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        clusters.append({
            "members": [mapped[index]["object"] for index in indexes],
            "shared_table_universe": sorted(set().union(
                *(set(mapped[index]["table_ids"]) for index in indexes)
            )),
            "basis": "transitive_pairwise_shared_table_usage_in_call_graph",
            "confidence": "heuristic_related_candidates",
            "runtime_executed": False,
        })
    clusters.sort(key=lambda item: (-len(item["members"]), item["members"][0].casefold()))
    return {
        "candidate_count": len(mapped),
        "cluster_count": len(clusters),
        "min_similarity": min_similarity,
        "max_depth": max_depth,
        "max_nodes_per_candidate": max_nodes_per_candidate,
        "candidates": mapped,
        "similarities": similarities,
        "clusters": clusters,
        "semantics": {
            "method": "Jaccard similarity of Table sets used by CALL-reachable indexed procedures",
            "meaning": "related candidates for investigation, not confirmed end-to-end business processes",
            "dependency_evidence": "static dependency_graph CALL edges and table_usage records",
            "runtime_evaluated": False,
            "limitations": [
                "Traversal follows indexed CALL edges only; dynamic RUN targets and non-CALL relationships are not followed.",
                "Only indexed procedures and their Table usage are included; trigger/UI/job-queue/integration semantics may be incomplete.",
                "Depth and node limits can truncate a candidate footprint; inspect each candidate's truncated flag.",
                "Shared master Tables can connect unrelated workflows.",
                "Transitive pairwise clustering can connect members that do not all share a Table pairwise.",
                "A reachable dependency is not proof that the call or a Table operation ran at runtime.",
            ],
        },
    }
