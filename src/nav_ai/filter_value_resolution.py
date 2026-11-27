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
    if len(assignment_path) > len(target_path):
        return False
    return all(a == b for a, b in zip(assignment_path, target_path))


def _resolve(expression: str, events: list[dict[str, Any]], line: int,
             path: list[dict[str, Any]], seen: set[str] | None = None) -> dict[str, Any]:
    raw = expression.strip()
    if _LITERAL.fullmatch(raw):
        return {"status": "literal", "expression": raw, "resolved_value": raw,
                "evaluated": False}
    if not _IDENTIFIER.fullmatch(raw):
        return {"status": "symbolic_expression", "expression": raw,
                "evaluated": False}
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
        return {"status": "unresolved_variable", "variable": raw,
                "evaluated": False}
    assignment = max(candidates, key=lambda item: int(item.get("line", 0)))
    next_seen = set(seen)
    next_seen.add(key)
    upstream = _resolve(str(assignment.get("expression", "")), events,
                        int(assignment.get("line", line)),
                        assignment.get("path", []), next_seen)
    return {
        "status": "resolved_symbolically" if upstream["status"] in {"literal", "resolved_symbolically"} else "partially_resolved",
        "variable": raw,
        "assignment": {
            "expression": assignment.get("expression"),
            "line": assignment.get("line"),
            "source_file": assignment.get("source_file"),
            "kind": assignment.get("kind"),
        },
        "upstream": upstream,
        "evaluated": False,
    }


def enrich_record_filter_values(filter_analysis: dict[str, Any],
                                assignment_flow: dict[str, Any]) -> None:
    """Attach value provenance to SETRANGE/SETFILTER arguments at filter time."""
    assignments = assignment_flow.get("events", [])
    for event in filter_analysis.get("events", []):
        if event.get("operation") not in {"SETRANGE", "SETFILTER"}:
            continue
        arguments = event.get("arguments", [])
        event["argument_value_resolution"] = [
            _resolve(str(argument), assignments, int(event.get("line", 0)),
                     event.get("path", []))
            for argument in arguments
        ]
    for lookup in filter_analysis.get("lookups", []):
        for record_filter in lookup.get("active_filters", []):
            if "argument_value_resolution" in record_filter:
                continue
            arguments = record_filter.get("arguments", [])
            record_filter["argument_value_resolution"] = [
                _resolve(str(argument), assignments,
                         int(record_filter.get("line", lookup.get("line", 0))),
                         lookup.get("path_conditions", []))
                for argument in arguments
            ]
    filter_analysis["value_provenance"] = {
        "analysis": "path_sensitive_symbolic_assignment_resolution",
        "runtime_evaluated": False,
        "limitations": [
            "Only explicit assignment events produced by the existing assignment-flow analyzer are considered.",
            "Only simple identifier aliases and literal assignments are resolved; arbitrary C/AL expressions remain symbolic.",
            "Assignments must precede the SETRANGE/SETFILTER statement and have a compatible static branch path.",
            "Procedure side effects, database values, triggers, WITH scope and implicit conversions are not evaluated."
        ]
    }
