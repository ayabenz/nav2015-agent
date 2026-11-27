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
