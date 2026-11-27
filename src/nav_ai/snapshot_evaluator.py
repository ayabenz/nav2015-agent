"""Evaluate supported C/AL predicates against an explicitly supplied record snapshot.

This is not NAV runtime execution and never reads the database. Unknown or
unsupported operands produce an indeterminate result rather than a guess.
"""
from __future__ import annotations

import re
from typing import Any

from .semantic_conditions import _unquote, resolve_condition


_FIELD_REF = re.compile(
    r'^\s*(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*'
    r'(?P<field>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)\s*$',
    re.I,
)
_OPTION_MEMBER = re.compile(
    r'^\s*(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*'
    r'(?P<field>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)\s*::\s*'
    r'(?:(?:"[^"]*"|[A-Za-z_][A-Za-z0-9_ ]*)\s*::\s*)?'
    r'(?P<option>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)\s*$',
    re.I,
)


def _snapshot_value(expression: str, snapshot: dict[str, Any],
                    variables: dict[str, int],
                    tables: dict[int, dict[str, Any]]) -> tuple[Any, str | None]:
    raw = expression.strip()
    option_match = _OPTION_MEMBER.match(raw)
    if option_match:
        return _unquote(option_match.group("option")).strip(), None
    field_match = _FIELD_REF.match(raw)
    if field_match:
        variable = field_match.group("var")
        field_name = _unquote(field_match.group("field")).strip()
        record = next((value for key, value in snapshot.items()
                       if str(key).casefold() == variable.casefold()), None)
        if not isinstance(record, dict):
            return None, f"snapshot_record_missing:{variable}"
        value = next((value for key, value in record.items()
                      if str(key).casefold() == field_name.casefold()), None)
        if value is None and not any(str(key).casefold() == field_name.casefold() for key in record):
            return None, f"snapshot_field_missing:{variable}.{field_name}"
        resolved = resolve_condition(raw, variables, tables)["field_references"]
        field = resolved[0] if resolved else {}
        if field.get("resolution") != "resolved":
            return None, f"field_metadata_unresolved:{variable}.{field_name}"
        if value is None:
            return None, f"snapshot_value_null:{variable}.{field_name}"
        if field.get("field_type", "").casefold() == "option" and isinstance(value, int):
            choices = field.get("option_values", [])
            if 0 <= value < len(choices):
                return choices[value], None
            return None, f"option_ordinal_out_of_range:{variable}.{field_name}:{value}"
        return value, None
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'"), None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw), None
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw), None
    if raw.upper() == "TRUE":
        return True, None
    if raw.upper() == "FALSE":
        return False, None
    return None, f"unsupported_operand:{raw}"


def evaluate_condition_snapshot(tree: dict[str, Any], snapshot: dict[str, Any],
                                variables: dict[str, int],
                                tables: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a normalized predicate using only caller-supplied values."""
    missing: list[str] = []

    def evaluate(node: dict[str, Any]) -> bool | None:
        kind = node.get("type")
        if kind == "operand":
            value, reason = _snapshot_value(str(node.get("value", "")), snapshot, variables, tables)
            if reason:
                missing.append(reason)
                return None
            return value if isinstance(value, bool) else None
        if kind == "not":
            value = evaluate(node.get("operand", {}))
            return None if value is None else not value
        if kind == "boolean":
            values = [evaluate(child) for child in node.get("operands", [])]
            if node.get("operator") == "AND":
                if False in values:
                    return False
                return True if values and all(value is True for value in values) else None
            if node.get("operator") == "OR":
                if True in values:
                    return True
                return False if values and all(value is False for value in values) else None
            return None
        if kind == "comparison":
            left, reason = _snapshot_value(str(node.get("left", "")), snapshot, variables, tables)
            if reason:
                missing.append(reason)
                return None
            if "values" in node:
                rights = []
                for expression in node["values"]:
                    value, reason = _snapshot_value(str(expression), snapshot, variables, tables)
                    if reason:
                        missing.append(reason)
                        return None
                    rights.append(value)
                return left in rights
            right, reason = _snapshot_value(str(node.get("right", "")), snapshot, variables, tables)
            if reason:
                missing.append(reason)
                return None
            operator = node.get("operator")
            try:
                if operator == "=":
                    return left == right
                if operator == "<>":
                    return left != right
                if operator == "<":
                    return left < right
                if operator == ">":
                    return left > right
                if operator == "<=":
                    return left <= right
                if operator == ">=":
                    return left >= right
            except (TypeError, ValueError):
                missing.append(f"incompatible_values:{left!r}:{right!r}")
                return None
        return None

    result = evaluate(tree)
    return {
        "result": result,
        "status": "evaluated_from_supplied_snapshot" if result is not None else "indeterminate",
        "provenance": "caller_supplied_snapshot",
        "runtime_evaluated": False,
        "missing_or_unsupported": sorted(set(missing)),
    }
