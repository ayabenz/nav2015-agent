"""Static extraction of C/AL Record filters and lookup context.

This module records source-level SETRANGE/SETFILTER/RESET/FIND operations.
It does not execute NAV filters or assert that a lookup found a row.
"""
from __future__ import annotations

import re
from typing import Any

from .control_flow import tokenize
from .semantic_conditions import resolve_condition, _unquote

_FIELD = re.compile(r'(?:(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*)?(?P<field>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)$', re.I)
_FIND_METHODS = {"FIND", "FINDFIRST", "FINDLAST", "FINDSET", "FIND('-')", "FIND('+')"}


def _split_args(source: str, tokens: list[dict[str, Any]], start: int, end: int) -> list[str]:
    parts: list[str] = []
    depth = 0
    part_start = start
    for i in range(start, end):
        value = tokens[i]["value"]
        if value in {"(", "["}:
            depth += 1
        elif value in {")", "]"}:
            depth -= 1
        elif value == "," and depth == 0:
            parts.append(source[tokens[part_start]["start"]:tokens[i - 1]["end"]].strip() if i > part_start else "")
            part_start = i + 1
    if part_start < end:
        parts.append(source[tokens[part_start]["start"]:tokens[end - 1]["end"]].strip())
    return parts


def analyze_record_filters(
    source: str,
    variables: dict[str, int],
    tables: dict[int, dict[str, Any]],
    source_file: str = "<memory>",
    line_offset: int = 0,
) -> dict[str, Any]:
    """Track active filters per Record variable until RESET or later replacement."""
    tokens = tokenize(source)
    has_control_flow = any(t["upper"] in {"IF", "CASE", "ELSE"} for t in tokens)
    active: dict[str, dict[str, dict[str, Any]]] = {}
    events: list[dict[str, Any]] = []
    lookups: list[dict[str, Any]] = []
    i = 0
    while i + 2 < len(tokens):
        if tokens[i]["kind"] != "WORD" or tokens[i + 1]["value"] != "." or tokens[i + 2]["kind"] != "WORD":
            i += 1
            continue
        receiver = tokens[i]["value"]
        method = tokens[i + 2]["upper"]
        if i + 3 < len(tokens) and tokens[i + 3]["value"] == "(":
            depth, close = 1, i + 4
            while close < len(tokens) and depth:
                if tokens[close]["value"] == "(":
                    depth += 1
                elif tokens[close]["value"] == ")":
                    depth -= 1
                close += 1
            if depth:
                i += 1
                continue
            args = _split_args(source, tokens, i + 4, close - 1)
        elif method in {"RESET", "FINDFIRST", "FINDLAST", "FINDSET"}:
            args, close = [], i + 3
        else:
            i += 1
            continue
        line = tokens[i]["line"] + line_offset
        key = receiver.casefold()
        active.setdefault(key, {})
        event: dict[str, Any] | None = None
        if method == "RESET":
            active[key].clear()
            event = {"operation": "RESET", "record_variable": receiver, "line": line, "filters_after": []}
        elif method in {"SETRANGE", "SETFILTER"} and args:
            field_match = _FIELD.match(args[0].strip())
            if field_match:
                field_name = _unquote(field_match.group("field")).strip()
                field_key = field_name.casefold()
                if method == "SETRANGE" and len(args) == 1:
                    active[key].pop(field_key, None)
                    operation = "SETRANGE_CLEAR"
                else:
                    detail = {
                        "operation": method,
                        "record_variable": receiver,
                        "field": field_name,
                        "arguments": args[1:],
                        "line": line,
                        "source_file": source_file,
                        "table_id": variables.get(key),
                    }
                    resolved = resolve_condition(f'{receiver}."{field_name}"', variables, tables)
                    detail["field_resolution"] = resolved["field_references"][0] if resolved["field_references"] else None
                    active[key][field_key] = detail
                    operation = method
                event = {"operation": operation, "record_variable": receiver, "field": field_name,
                         "line": line, "filters_after": list(active[key].values())}
        elif method in {"FINDFIRST", "FINDLAST", "FINDSET", "FIND"}:
            snapshot = list(active[key].values())
            lookup = {
                "operation": method, "record_variable": receiver, "line": line,
                "active_filters": snapshot, "source_file": source_file,
                "result": "unknown_static",
                "filter_state": "branch_ambiguous" if has_control_flow else "linear_source_order",
                "meaning": "lookup attempted with these source-level filters; row existence is runtime-dependent",
            }
            lookups.append(lookup)
            event = lookup
        if event is not None:
            events.append(event)
        i = close
    return {
        "analysis": "static_record_filter_flow",
        "runtime_evaluated": False,
        "events": events,
        "lookups": lookups,
        "limitations": [
            "Filter argument expressions are preserved as source text; placeholders are not evaluated.",
            "Calls are scanned in source order; when IF/CASE/ELSE occurs, active filter state is marked branch_ambiguous rather than merged by path.",
            "Interprocedural flow is not modeled.",
            "SETCURRENTKEY does not change filter membership and is not included in the filter snapshot.",
            "Dynamic RecordRef/FieldRef and WITH-scope references are not resolved.",
        ],
    }


def annotate_record_lookup_conditions(nodes: Any, lookups: list[dict[str, Any]]) -> None:
    """Attach nearby FINDFIRST lookup evidence to direct IF predicates."""
    by_line = {item["line"]: item for item in lookups}
    def visit(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, dict):
            if node.get("type") == "if":
                condition = str(node.get("condition", ""))
                match = re.search(r'\b(?P<neg>NOT\s+)?(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*FINDFIRST\b', condition, re.I)
                if match:
                    span_line = node.get("condition_span", {}).get("line_start")
                    candidates = [item for line, item in by_line.items()
                                  if item["record_variable"].casefold() == match.group("var").casefold()
                                  and line <= span_line and span_line - line <= 2]
                    if candidates:
                        node["record_lookup"] = {
                            "record_variable": match.group("var"),
                            "branch_meaning": "no_matching_record" if match.group("neg") else "matching_record",
                            "lookup": candidates[-1],
                            "runtime_evaluated": False,
                        }
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)
    visit(nodes)



def analyze_record_filter_paths(
    nodes: list[dict[str, Any]],
    variables: dict[str, int],
    tables: dict[int, dict[str, Any]],
    source_file: str = "<memory>",
) -> dict[str, Any]:
    """Interpret filter mutations over the extracted IF/CASE tree, keeping path states separate."""
    from copy import deepcopy

    lookups: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    next_path_id = 1

    def scan_statement(source: str, line_start: int, state: dict[str, Any]) -> None:
        tokens = tokenize(source)
        i = 0
        while i + 2 < len(tokens):
            if tokens[i]["kind"] != "WORD" or tokens[i + 1]["value"] != "." or tokens[i + 2]["kind"] != "WORD":
                i += 1
                continue
            receiver, method = tokens[i]["value"], tokens[i + 2]["upper"]
            if i + 3 < len(tokens) and tokens[i + 3]["value"] == "(":
                depth, close = 1, i + 4
                while close < len(tokens) and depth:
                    if tokens[close]["value"] == "(":
                        depth += 1
                    elif tokens[close]["value"] == ")":
                        depth -= 1
                    close += 1
                if depth:
                    i += 1
                    continue
                args = _split_args(source, tokens, i + 4, close - 1)
            elif method in {"RESET", "FINDFIRST", "FINDLAST", "FINDSET"}:
                args, close = [], i + 3
            else:
                i += 1
                continue

            key = receiver.casefold()
            record_filters = state["filters"].setdefault(key, {})
            line = line_start + tokens[i]["line"] - 1
            if method == "RESET":
                record_filters.clear()
                events.append({"operation": "RESET", "record_variable": receiver,
                               "line": line, "path": list(state["path"])})
            elif method in {"SETRANGE", "SETFILTER"} and args:
                field_match = _FIELD.match(args[0].strip())
                if field_match:
                    field_name = _unquote(field_match.group("field")).strip()
                    field_key = field_name.casefold()
                    if method == "SETRANGE" and len(args) == 1:
                        record_filters.pop(field_key, None)
                        operation = "SETRANGE_CLEAR"
                    else:
                        resolved = resolve_condition(f'{receiver}."{field_name}"', variables, tables)
                        detail = {
                            "operation": method, "record_variable": receiver,
                            "field": field_name, "arguments": args[1:],
                            "line": line, "source_file": source_file,
                            "table_id": variables.get(key),
                            "field_resolution": resolved["field_references"][0] if resolved["field_references"] else None,
                        }
                        record_filters[field_key] = detail
                        operation = method
                    events.append({"operation": operation, "record_variable": receiver,
                                   "field": field_name, "line": line,
                                   "filters_after": list(record_filters.values()),
                                   "path": list(state["path"])})
            elif method in {"FINDFIRST", "FINDLAST", "FINDSET", "FIND"}:
                lookups.append({
                    "operation": method, "record_variable": receiver, "line": line,
                    "active_filters": deepcopy(list(record_filters.values())),
                    "path_conditions": list(state["path"]),
                    "filter_state": "path_specific",
                    "result": "unknown_static", "runtime_evaluated": False,
                    "meaning": "lookup attempted with filters on this possible source path; row existence remains runtime-dependent",
                })
            i = close

    def process_condition_lookup(condition: str, line: int, state: dict[str, Any]) -> None:
        # A FINDFIRST used as an IF predicate is itself the lookup; record its filter state here.
        pattern = re.compile(r'\b(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*FINDFIRST\b', re.I)
        for match in pattern.finditer(condition):
            receiver = match.group("var")
            key = receiver.casefold()
            lookups.append({
                "operation": "FINDFIRST", "record_variable": receiver, "line": line,
                "active_filters": deepcopy(list(state["filters"].get(key, {}).values())),
                "path_conditions": list(state["path"]),
                "filter_state": "path_specific", "result": "unknown_static",
                "runtime_evaluated": False,
                "meaning": "IF predicate performs a lookup with filters on this possible source path",
            })

    def walk(node: Any, states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal next_path_id
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
                scan_statement(node.get("source", ""), node.get("line_start", 1), state)
            return states
        if kind == "if":
            condition = str(node.get("condition", ""))
            line = node.get("condition_span", {}).get("line_start", node.get("line_start", 1))
            true_states, false_states = [], []
            for state in states:
                process_condition_lookup(condition, line, state)
                true_state, false_state = deepcopy(state), deepcopy(state)
                true_state["path"].append({"if": condition, "outcome": True})
                false_state["path"].append({"if": condition, "outcome": False})
                true_states.append(true_state)
                false_states.append(false_state)
            after_true = walk(node.get("true_branch"), true_states)
            after_false = walk(node.get("false_branch"), false_states) if node.get("false_branch") is not None else false_states
            return after_true + after_false
        if kind == "case":
            expression = str(node.get("expression", ""))
            outcomes = [(f"{expression} IN ({arm.get('labels', '')})", arm.get("body"))
                        for arm in node.get("arms", [])]
            if node.get("default") is not None:
                outcomes.append((f"ELSE ({expression} unmatched)", node.get("default")))
            elif outcomes:
                outcomes.append((f"ELSE ({expression} unmatched)", None))
            if not outcomes:
                return states
            branched = []
            for state in states:
                for predicate, body in outcomes:
                    branch_state = deepcopy(state)
                    branch_state["path"].append({"case": predicate})
                    branched.extend(walk(body, [branch_state]))
            return branched
        # Unknown node types are not interpreted as executable filter operations.
        return states

    initial = [{"filters": {}, "path": []}]
    final_states = walk(nodes, initial)
    return {
        "analysis": "path_sensitive_static_record_filter_flow",
        "runtime_evaluated": False,
        "events": events,
        "lookups": lookups,
        "final_path_count": len(final_states),
        "limitations": [
            "Paths represent syntactic IF/CASE alternatives, not evaluated runtime conditions.",
            "Boolean predicates are preserved as source text; values and SETFILTER placeholders are not evaluated.",
            "Only operations represented by parsed statement nodes are interpreted; opaque or unsupported C/AL constructs may be omitted.",
            "Interprocedural calls, WITH scopes, RecordRef/FieldRef and database state are not modeled.",
            "Every lookup result remains unknown_static.",
        ],
    }
