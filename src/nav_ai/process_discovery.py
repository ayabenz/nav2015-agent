"""Heuristic discovery of candidate NAV business-process entry points.

Candidates are ranked from object metadata and existing graph connectivity. A
candidate is not proof of a user-facing workflow or runtime execution.
"""
from __future__ import annotations

import sqlite3
from typing import Any


_ENTRY_TYPES = {"page": 40, "report": 35, "xmlport": 30, "codeunit": 20}


def discover_process_entrypoints(
    graph: sqlite3.Connection,
    limit: int = 200,
    include_standard: bool = False,
) -> dict[str, Any]:
    """Rank likely process entry objects without asserting business meaning."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    rows = graph.execute(
        "SELECT node,type,id,name,origin,procedures,out_edges,in_edges "
        "FROM objects ORDER BY type,id"
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    for row in rows:
        kind = str(row["type"]).casefold()
        origin = str(row["origin"] or "UNKNOWN")
        if kind not in _ENTRY_TYPES:
            excluded["unsupported_object_type"] = excluded.get("unsupported_object_type", 0) + 1
            continue
        if not include_standard and origin == "STANDARD_UNCHANGED":
            excluded["standard_unchanged"] = excluded.get("standard_unchanged", 0) + 1
            continue
        incoming = int(row["in_edges"] or 0)
        outgoing = int(row["out_edges"] or 0)
        procedure_count = int(row["procedures"] or 0)
        score = _ENTRY_TYPES[kind]
        reasons = [f"object_type:{kind}"]
        if origin in {"CUSTOM", "MODIFIED_STANDARD"}:
            score += 25
            reasons.append(f"company_origin:{origin.lower()}")
        if incoming == 0:
            score += 20
            reasons.append("no_indexed_incoming_edges")
        elif incoming <= 3:
            score += 8
            reasons.append("few_indexed_incoming_edges")
        if outgoing:
            score += min(15, outgoing)
            reasons.append("has_indexed_outgoing_dependencies")
        if procedure_count:
            score += min(10, procedure_count)
            reasons.append("has_indexed_procedures")
        candidates.append({
            "object": row["node"],
            "type": row["type"],
            "object_id": int(row["id"]),
            "name": row["name"],
            "origin": origin,
            "procedure_count": procedure_count,
            "incoming_edge_count": incoming,
            "outgoing_edge_count": outgoing,
            "score": score,
            "reasons": reasons,
            "confidence": "heuristic_candidate",
            "runtime_executed": False,
        })
    candidates.sort(key=lambda item: (-item["score"], item["object"].casefold()))
    selected = candidates[:limit]
    return {
        "candidate_count": len(candidates),
        "returned_count": len(selected),
        "limit": limit,
        "include_standard": include_standard,
        "candidates": selected,
        "excluded_counts": excluded,
        "semantics": {
            "method": "object type, origin, indexed incoming/outgoing edge counts, and procedure count",
            "meaning": "ranked candidates for human review; not confirmed business processes or runtime entry points",
            "runtime_evaluated": False,
            "limitations": [
                "Graph connectivity is static and may omit UI actions, job queues, integrations, events, and dynamic calls.",
                "Low incoming-edge count does not prove a process is externally initiated.",
                "A Page or Report may be a lookup, subpage, or helper rather than a process entry.",
                "Candidate ranking does not cluster related objects into business processes.",
            ],
        },
    }
