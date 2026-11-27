"""Conservative normalization of C/AL boolean condition expressions."""
from __future__ import annotations

from typing import Any

from .control_flow import tokenize


def _raw(source: str, tokens: list[dict[str, Any]], start: int, end: int) -> str:
    if start >= end:
        return ""
    return source[tokens[start]["start"]:tokens[end - 1]["end"]].strip()


def _matching_outer_parentheses(tokens: list[dict[str, Any]], start: int, end: int) -> bool:
    if end - start < 2 or tokens[start]["value"] != "(" or tokens[end - 1]["value"] != ")":
        return False
    depth = 0
    for i in range(start, end):
        value = tokens[i]["value"]
        if value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
            if depth == 0 and i != end - 1:
                return False
    return depth == 0


def _split_top_level(tokens: list[dict[str, Any]], start: int, end: int,
                     operator: str) -> list[tuple[int, int]]:
    parts = []
    depth = 0
    part_start = start
    for i in range(start, end):
        value = tokens[i]["upper"]
        if value in {"(", "["}:
            depth += 1
        elif value in {")", "]"}:
            depth -= 1
        elif depth == 0 and value == operator:
            parts.append((part_start, i))
            part_start = i + 1
    if parts:
        parts.append((part_start, end))
    return parts


def _comparison_index(tokens: list[dict[str, Any]], start: int, end: int) -> int | None:
    depth = 0
    for i in range(start, end):
        value = tokens[i]["upper"]
        if value in {"(", "["}:
            depth += 1
        elif value in {")", "]"}:
            depth -= 1
        elif depth == 0 and value in {"=", "<>", "<", ">", "<=", ">=", "IN"}:
            return i
    return None


def _parse_range(source: str, tokens: list[dict[str, Any]], start: int, end: int) -> dict[str, Any]:
    while _matching_outer_parentheses(tokens, start, end):
        start += 1
        end -= 1
    for operator in ("OR", "AND"):
        parts = _split_top_level(tokens, start, end, operator)
        if parts:
            return {
                "type": "boolean",
                "operator": operator,
                "operands": [_parse_range(source, tokens, a, b) for a, b in parts],
            }
    if start < end and tokens[start]["upper"] == "NOT":
        return {"type": "not", "operand": _parse_range(source, tokens, start + 1, end)}
    op_index = _comparison_index(tokens, start, end)
    if op_index is not None:
        operator = tokens[op_index]["upper"]
        left = _raw(source, tokens, start, op_index)
        right = _raw(source, tokens, op_index + 1, end)
        result: dict[str, Any] = {
            "type": "comparison", "operator": operator,
            "left": left, "right": right,
        }
        if operator == "IN" and len(right) >= 2 and right[0] == "[" and right[-1] == "]":
            inner_start, inner_end = op_index + 2, end - 1
            items = []
            depth = 0
            part_start = inner_start
            for i in range(inner_start, inner_end):
                value = tokens[i]["value"]
                if value in {"(", "["}:
                    depth += 1
                elif value in {")", "]"}:
                    depth -= 1
                elif value == "," and depth == 0:
                    items.append(_raw(source, tokens, part_start, i))
                    part_start = i + 1
            if part_start < inner_end:
                items.append(_raw(source, tokens, part_start, inner_end))
            result["values"] = items
        return result
    return {"type": "operand", "value": _raw(source, tokens, start, end)}


def normalize_condition_expression(expression: str) -> dict[str, Any]:
    """Return a loss-conscious expression tree; unsupported fragments remain operands."""
    tokens = tokenize(expression)
    if not tokens:
        return {"type": "operand", "value": ""}
    return _parse_range(expression, tokens, 0, len(tokens))
