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

_KEYWORDS = {
    "AND", "OR", "NOT", "TRUE", "FALSE", "THEN", "ELSE", "IF", "CASE",
    "OF", "BEGIN", "END", "IN", "MOD", "DIV", "XOR", "EXIT", "ERROR",
    "MESSAGE", "TESTFIELD", "FIELDERROR",
}


def _expression_references(expression: str) -> list[str]:
    """Return conservative variable/field references from a simple expression."""
    # Mask quoted literals so their contents are never mistaken for identifiers.
    masked = re.sub(r"'(?:''|[^'])*'", " ", expression)
    masked = re.sub(r'"(?:""|[^"])*"', " ", masked)
    refs = []
    for match in _IDENTIFIER.finditer(masked):
        name = match.group(0).strip()
        prefix = masked[:match.start()].rstrip()
        if prefix.endswith("::") or name.upper() in _KEYWORDS:
            continue
        # A call target is not a variable dependency; calls are handled as unknown.
        if masked[match.end():].lstrip().startswith("("):
            continue
        if _key(name) not in {_key(x) for x in refs}:
            refs.append(name)
    return refs


def _dependency_chain(assignment: dict[str, Any], values: dict[str, dict[str, Any]],
                      seen: set[str] | None = None) -> list[dict[str, Any]]:
    """Resolve simple assignment-to-assignment provenance without evaluating expressions."""
    seen = set(seen or ())
    key = assignment["target_key"]
    if key in seen:
        return [{"state": "cycle", "target": assignment["target"]}]
    seen.add(key)
    chain = []
    for reference in assignment.get("expression_references", []):
        dependency = values.get(_key(reference))
        if dependency is None:
            chain.append({"state": "unresolved", "reference": reference})
            continue
        chain.append({
            "state": "resolved",
            "reference": reference,
            "assignment": {k: v for k, v in dependency.items()
                           if k not in {"expression_references"}},
            "upstream": _dependency_chain(dependency, values, seen),
        })
    return chain


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
        "expression_references": _expression_references(value),
    }


def analyze_assignment_flow(nodes: list[dict[str, Any]], source_file: str = "<memory>",\n                            call_effects: dict[int, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
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
                statement_line = int(node.get("line_start", 1))
                statement_source = str(node.get("source", ""))
                mapped_effects = (call_effects or {}).get(statement_line, [])
                if mapped_effects and _CALL.search(statement_source):
                    # A recognized call may mutate VAR arguments. Invalidate prior
                    # facts first, then restore only the explicit effects mapped from
                    # the selected callee; all other state remains unknown.
                    invalidated = list(state["values"])
                    state["values"].clear()
                    if invalidated:
                        events.append({
                            "kind": "interprocedural_call_invalidation",
                            "line": statement_line,
                            "source": statement_source,
                            "invalidated": invalidated,
                            "path": list(state["path"]),
                            "source_file": source_file,
                        })
                    for effect in mapped_effects:
                        target = str(effect.get("target", "")).strip()
                        expression = str(effect.get("expression", "")).strip()
                        if not target or not expression:
                            continue
                        assignment = {
                            "target": target,
                            "target_key": _key(target),
                            "expression": expression,
                            "line": statement_line,
                            "source_file": effect.get("callee_source_file", "<callee>"),
                            "kind": "explicit_assignment",
                            "evaluated": False,
                            "expression_references": _expression_references(expression),
                            "interprocedural": True,
                            "callee_line": effect.get("callee_line"),
                            "callee_parameter": effect.get("callee_parameter"),
                            "mapping": effect.get("mapping"),
                        }
                        state["values"][assignment["target_key"]] = assignment
                        events.append({
                            **assignment,
                            "kind": "interprocedural_var_mutation",
                            "path": list(state["path"]),
                        })
                    continue
                assignment = _assignment(statement_source, statement_line, source_file)
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
                        refs.append({**value, "referenced_as": name,
                                      "dependency_chain": _dependency_chain(value, state["values"])})
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
            "Unknown procedure calls invalidate all tracked values because VAR mutation cannot be ruled out; recognized calls restore only explicitly mapped VAR effects.",
            "Interprocedural parameter/return flow, WITH scope, implicit database changes and trigger side effects are not modeled.",
            "A static path is a syntactic possibility, not proof that NAV executed it.",
        ],
    }
