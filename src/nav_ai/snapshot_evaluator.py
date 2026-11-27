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


def _compatible_values(left: Any, right: Any) -> bool:
    """Reject Python's implicit bool/int equality and cross-type comparisons."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool)
    numeric = (int, float)
    if isinstance(left, numeric) or isinstance(right, numeric):
        return isinstance(left, numeric) and isinstance(right, numeric)
    return type(left) is type(right)


def evaluate_condition_snapshot(tree: dict[str, Any], snapshot: dict[str, Any],
                                variables: dict[str, int],
                                tables: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a normalized predicate using only caller-supplied values."""
    missing: list[str] = []
    explanation: list[dict[str, Any]] = []

    def evaluate(node: dict[str, Any], path: str = "root") -> bool | None:
        kind = node.get("type")
        if kind == "operand":
            value, reason = _snapshot_value(str(node.get("value", "")), snapshot, variables, tables)
            if reason:
                missing.append(reason)
                return None
            result = value if isinstance(value, bool) else None
            explanation.append({"path": path, "kind": "boolean_operand", "expression": node.get("value"), "value": value if reason is None else None, "result": result, "status": "evaluated" if result is not None else "indeterminate"})
            return result
        if kind == "not":
            value = evaluate(node.get("operand", {}), path + ".not")
            result = None if value is None else not value
            explanation.append({"path": path, "kind": "not", "result": result, "status": "evaluated" if result is not None else "indeterminate"})
            return result
        if kind == "boolean":
            values = [evaluate(child, f"{path}.{node.get('operator', 'bool').lower()}[{index}]") for index, child in enumerate(node.get("operands", []))]
            if node.get("operator") == "AND":
                result = False if False in values else (True if values and all(value is True for value in values) else None)
            elif node.get("operator") == "OR":
                result = True if True in values else (False if values and all(value is False for value in values) else None)
            else:
                result = None
            explanation.append({"path": path, "kind": "boolean", "operator": node.get("operator"), "operand_results": values, "result": result, "status": "evaluated" if result is not None else "indeterminate"})
            return result
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
                if any(not _compatible_values(left, value) for value in rights):
                    missing.append(f"incompatible_value_types:{type(left).__name__}:IN")
                    return None
                result = left in rights
                explanation.append({"path": path, "kind": "comparison", "operator": "IN", "left_expression": node.get("left"), "left_value": left, "right_values": rights, "result": result, "status": "evaluated"})
                return result
            right, reason = _snapshot_value(str(node.get("right", "")), snapshot, variables, tables)
            if reason:
                missing.append(reason)
                return None
            if not _compatible_values(left, right):
                missing.append(
                    f"incompatible_value_types:{type(left).__name__}:{type(right).__name__}"
                )
                return None
            operator = node.get("operator")
            try:
                if operator == "=":
                    result = left == right
                elif operator == "<>":
                    result = left != right
                elif operator == "<":
                    result = left < right
                elif operator == ">":
                    result = left > right
                elif operator == "<=":
                    result = left <= right
                elif operator == ">=":
                    result = left >= right
                else:
                    return None
                explanation.append({"path": path, "kind": "comparison", "operator": operator, "left_expression": node.get("left"), "left_value": left, "right_expression": node.get("right"), "right_value": right, "result": result, "status": "evaluated"})
                return result
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
        "explanation": explanation,
    }
