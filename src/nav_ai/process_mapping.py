"""Evidence-based grouping of candidate NAV processes by shared direct table usage.

This is an inventory aid, not a claim that candidates are distinct business processes.
Only table_usage rows directly attributed to each entry object are considered.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .process_discovery import discover_process_entrypoints


def map_candidate_processes(
    graph: sqlite3.Connection,
    limit: int = 200,
    include_standard: bool = False,
    min_similarity: float = 0.25,
) -> dict[str, Any]:
    """Group ranked entry candidates when their direct Table footprints overlap."""
    if not 0.0 < min_similarity <= 1.0:
        raise ValueError("min_similarity must be greater than 0 and at most 1")
    discovery = discover_process_entrypoints(
        graph, limit=limit, include_standard=include_standard
    )
    candidates = discovery["candidates"]
    mapped: list[dict[str, Any]] = []
    for candidate in candidates:
        rows = graph.execute(
            "SELECT table_node, table_name, usage, count FROM table_usage "
            "WHERE src_object=? ORDER BY table_node, usage",
            (candidate["object"],),
        ).fetchall()
        table_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row["table_node"])
            entry = table_map.setdefault(key, {
                "table": key,
                "name": row["table_name"],
                "usages": [],
                "reference_count": 0,
            })
            usage = str(row["usage"])
            if usage not in entry["usages"]:
                entry["usages"].append(usage)
            entry["reference_count"] += int(row["count"] or 0)
        mapped.append({
            **candidate,
            "direct_tables": sorted(table_map.values(), key=lambda item: item["table"]),
            "table_ids": sorted(table_map),
        })

    parent = list(range(len(mapped)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

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
            if score >= min_similarity:
                a, b = find(left), find(right)
                if a != b:
                    parent[b] = a
                similarities.append({
                    "left": mapped[left]["object"],
                    "right": mapped[right]["object"],
                    "shared_tables": shared,
                    "jaccard_similarity": round(score, 4),
                    "evidence": "shared_direct_table_usage",
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
            "basis": "transitive_pairwise_shared_direct_table_usage",
            "confidence": "heuristic_related_candidates",
            "runtime_executed": False,
        })
    clusters.sort(key=lambda item: (-len(item["members"]), item["members"][0].casefold()))
    return {
        "candidate_count": len(mapped),
        "cluster_count": len(clusters),
        "min_similarity": min_similarity,
        "candidates": mapped,
        "similarities": similarities,
        "clusters": clusters,
        "semantics": {
            "method": "Jaccard similarity of direct table_usage sets for ranked entry objects",
            "meaning": "related candidates for investigation, not confirmed end-to-end business processes",
            "runtime_evaluated": False,
            "limitations": [
                "Only table usage attributed directly to each entry object is included; reachable callees are not yet folded into the footprint.",
                "Shared tables can indicate common master data or infrastructure rather than the same business process.",
                "Transitive pairwise grouping can connect members that do not all share a table with one another.",
                "Dynamic calls, UI navigation, job queues, integrations and runtime execution are not inferred.",
                "Candidates without direct table usage remain unclustered.",
            ],
        },
    }
