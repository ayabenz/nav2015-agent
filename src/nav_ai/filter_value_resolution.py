"""Resolve Record filter argument variables from path-compatible local assignments.

This is symbolic static analysis only: it never reads NAV database rows or evaluates
arbitrary C/AL expressions.
"""
from __future__ import annotations

import re
from typing import Any


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_@]*$")
_LITERAL = re.compile(r"^(?:'.*(?<!')'|-?\d+(?:\.\d+)?|TRUE|FALSE|NULL)$", re.I)


def _compatible(assignment_path: list[dict[str, Any]],
                target_path: list[dict[str, Any]]) -> bool:
    return len(assignment_path) <= len(target_path) and all(
        a == b for a, b in zip(assignment_path, target_path)
    )


def _resolve(expression: str, events: list[dict[str, Any]], line: int,
             path: list[dict[str, Any]], seen: set[str] | None = None) -> dict[str, Any]:
    raw = expression.strip()
    if _LITERAL.fullmatch(raw):
        return {"status": "literal", "expression": raw, "resolved_value": raw,
                "evaluated": False}
    if not _IDENTIFIER.fullmatch(raw):
        return {"status": "symbolic_expression", "expression": raw, "evaluated": False}
    seen = set(seen or ())
    key = raw.casefold()
    if key in seen:
        return {"status": "cycle", "variable": raw, "evaluated": False}
    candidates = [
        event for event in events
        if event.get("target_key") == key
        and int(event.get("line", 0)) <= line
        and _compatible(event.get("path", []), path)
        and event.get("kind") in {"explicit_assignment", "interprocedural_var_mutation"}
    ]
    if not candidates:
        return {"status": "unresolved_variable", "variable": raw, "evaluated": False}
    assignment = max(candidates, key=lambda item: int(item.get("line", 0)))
    upstream = _resolve(
        str(assignment.get("expression", "")), events,
        int(assignment.get("line", line)), assignment.get("path", []), seen | {key},
    )
    return {
        "status": "resolved_symbolically" if upstream["status"] in {"literal", "resolved_symbolically"} else "partially_resolved",
        "variable": raw,
        "assignment": {k: assignment.get(k) for k in ("expression", "line", "source_file", "kind")},
        "upstream": upstream,
        "evaluated": False,
    }


def enrich_record_filter_values(filter_analysis: dict[str, Any],
                                assignment_flow: dict[str, Any]) -> None:
    """Attach value provenance to SETRANGE/SETFILTER arguments at filter time."""
    assignments = assignment_flow.get("events", [])
    for event in filter_analysis.get("events", []):
        if event.get("operation") in {"SETRANGE", "SETFILTER"}:
            event["argument_value_resolution"] = [
                _resolve(str(arg), assignments, int(event.get("line", 0)), event.get("path", []))
                for arg in event.get("arguments", [])
            ]
    for lookup in filter_analysis.get("lookups", []):
        for record_filter in lookup.get("active_filters", []):
            if "argument_value_resolution" not in record_filter:
                record_filter["argument_value_resolution"] = [
                    _resolve(str(arg), assignments,
                             int(record_filter.get("line", lookup.get("line", 0))),
                             lookup.get("path_conditions", []))
                    for arg in record_filter.get("arguments", [])
                ]
    filter_analysis["value_provenance"] = {
        "analysis": "path_sensitive_symbolic_assignment_resolution",
        "runtime_evaluated": False,
        "limitations": [
            "Only explicit assignment events from the assignment-flow analyzer are considered.",
            "Only simple identifier aliases and literals are resolved; other expressions remain symbolic.",
            "Assignments must precede the filter operation and have a compatible static branch path.",
            "Procedure side effects, database values, triggers, WITH scope and implicit conversions are not evaluated.",
        ],
    }


def analyze_record_filter_value_flow(nodes: list[dict[str, Any]],
                                     variables: dict[str, int],
                                     tables: dict[int, dict[str, Any]],
                                     source_file: str = "<memory>") -> dict[str, Any]:
    """Run path-sensitive filter tracking and symbolic argument provenance together."""
    from .assignment_flow import analyze_assignment_flow
    from .record_filters import analyze_record_filter_paths

    assignment_flow = analyze_assignment_flow(nodes, source_file)
    filter_flow = analyze_record_filter_paths(nodes, variables, tables, source_file)
    enrich_record_filter_values(filter_flow, assignment_flow)
    return {
        "analysis": "record_filter_and_value_lineage",
        "assignment_flow_analysis": assignment_flow,
        "record_filter_analysis": filter_flow,
        "runtime_evaluated": False,
    }
