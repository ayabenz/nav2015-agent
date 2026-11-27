"""Conservative path-sensitive local assignment tracking for C/AL.

Tracks only explicit := statements in parsed source. Values are symbolic source
expressions, not evaluated values. Unknown calls invalidate tracked state.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


_ASSIGNMENT = re.compile(
    r'^\s*(?P<target>[A-Za-z_][A-Za-z0-9_@]*(?:\s*\.\s*(?:"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*))?)\s*:=\s*(?P<value>.*?)\s*;?\s*$',
    re.S,
)
_CALL = re.compile(r'\b[A-Za-z_][A-Za-z0-9_@]*\s*\(', re.I)
_IDENTIFIER = re.compile(r'(?<![.])\b[A-Za-z_][A-Za-z0-9_@]*(?:\s*\.\s*(?:"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*))?', re.I)


def _key(value: str) -> str:
    return re.sub(r'\s+', '', value).casefold()


def _assignment(source: str, line: int, source_file: str) -> dict[str, Any] | None:
    match = _ASSIGNMENT.match(source)
    if not match:
        return None
    target = match.group("target").strip()
    value = match.group("value").strip().rstrip(";").strip()
    if not target or not value:
        return None
    return {
        "target": target,
        "target_key": _key(target),
        "expression": value,
        "line": line,
        "source_file": source_file,
        "kind": "explicit_assignment",
        "evaluated": False,
    }


def analyze_assignment_flow(nodes: list[dict[str, Any]], source_file: str = "<memory>") -> dict[str, Any]:
    """Attach incoming assignment alternatives to IF nodes without evaluating them."""
    events: list[dict[str, Any]] = []

    def walk(node: Any, states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if node is None:
            return states
        if isinstance(node, list):
            current = states
            for child in node:
                current = walk(child, current)
            return current
        if not isinstance(node, dict):
            return states
        kind = node.get("type")
        if kind == "block":
            return walk(node.get("children", []), states)
        if kind == "statement":
            for state in states:
                assignment = _assignment(str(node.get("source", "")),
                                          int(node.get("line_start", 1)), source_file)
                if assignment:
                    if _CALL.search(assignment["expression"]):
                        invalidated = list(state["values"])
                        state["values"].clear()
                        if invalidated:
                            events.append({
                                "kind": "unknown_call_invalidation",
                                "line": node.get("line_start", 1),
                                "source": node.get("source", ""),
                                "invalidated": invalidated,
                                "path": list(state["path"]),
                                "source_file": source_file,
                            })
                    state["values"][assignment["target_key"]] = assignment
                    events.append({**assignment, "path": list(state["path"])})
                elif _CALL.search(str(node.get("source", ""))):
                    # C/AL procedures can mutate VAR parameters; without signatures,
                    # invalidate all known values rather than preserve stale facts.
                    invalidated = list(state["values"])
                    state["values"].clear()
                    if invalidated:
                        events.append({
                            "kind": "unknown_call_invalidation",
                            "line": node.get("line_start", 1),
                            "source": node.get("source", ""),
                            "invalidated": invalidated,
                            "path": list(state["path"]),
                            "source_file": source_file,
                        })
            return states
        if kind == "if":
            alternatives = []
            for state in states:
                refs = []
                condition = str(node.get("condition", ""))
                for match in _IDENTIFIER.finditer(condition):
                    name = match.group(0).strip()
                    key = _key(name)
                    value = state["values"].get(key)
                    if value and all(x["target_key"] != key for x in refs):
                        refs.append({**value, "referenced_as": name})
                alternatives.append({
                    "path": list(state["path"]),
                    "known_assignments": refs,
                    "unresolved_references": [
                        m.group(0).strip() for m in _IDENTIFIER.finditer(condition)
                        if _key(m.group(0)) not in state["values"]
                    ],
                })
            node["assignment_context"] = {
                "alternatives": alternatives,
                "state": "path_specific" if len(alternatives) == 1 else "multiple_incoming_paths",
                "runtime_evaluated": False,
                "meaning": "latest explicit assignments visible on each static source path; expressions are not evaluated",
            }
            true_states, false_states = [], []
            for state in states:
                t, f = deepcopy(state), deepcopy(state)
                t["path"].append({"if": node.get("condition", ""), "outcome": True})
                f["path"].append({"if": node.get("condition", ""), "outcome": False})
                true_states.append(t)
                false_states.append(f)
            after_true = walk(node.get("true_branch"), true_states)
            after_false = walk(node.get("false_branch"), false_states) if node.get("false_branch") is not None else false_states
            return after_true + after_false
        if kind == "case":
            arms = [(f'{node.get("expression", "")} IN ({a.get("labels", "")})', a.get("body"))
                    for a in node.get("arms", [])]
            if node.get("default") is not None:
                arms.append((f'{node.get("expression", "")} unmatched', node.get("default")))
            elif arms:
                arms.append((f'{node.get("expression", "")} unmatched', None))
            branched = []
            for state in states:
                for predicate, body in arms:
                    branch = deepcopy(state)
                    branch["path"].append({"case": predicate})
                    branched.extend(walk(body, [branch]))
            return branched or states
        return states

    final_states = walk(nodes, [{"values": {}, "path": []}])
    return {
        "analysis": "path_sensitive_static_assignment_flow",
        "runtime_evaluated": False,
        "events": events,
        "final_path_count": len(final_states),
        "limitations": [
            "Only simple explicit := statements in parsed statement nodes are tracked.",
            "Assignment expressions are preserved symbolically and are never evaluated.",
            "Unknown procedure calls invalidate all tracked values because VAR mutation cannot be ruled out.",
            "Interprocedural parameter/return flow, WITH scope, implicit database changes and trigger side effects are not modeled.",
            "A static path is a syntactic possibility, not proof that NAV executed it.",
        ],
    }
