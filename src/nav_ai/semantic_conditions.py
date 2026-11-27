"""Resolve C/AL record-field references in control-flow predicates.

Resolution is static and evidence-based: a variable must have a declared Record
type and the referenced field must exist in the supplied Table export.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .condition_expression import normalize_condition_expression

_VAR_RE = re.compile(
    r'^\s*(?:"(?P<quoted>[^"]+)"|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))'
    r'(?:@\d+)?\s*:\s*Record\s+(?P<table_id>\d+)\s*;\s*$',
    re.I,
)
_FIELD_RE = re.compile(
    r'^\s*\{\s*(?P<id>\d+)\s*;\s*;\s*(?P<name>[^;]+?)\s*;\s*(?P<type>[^;}]+?)\s*(?:;|\}|$)',
    re.I,
)
_ACCESS_RE = re.compile(
    r'(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*'
    r'(?P<field>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)',
    re.I,
)
_OPTION_RE = re.compile(
    r'(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*'
    r'(?P<field>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)\s*::\s*'
    r'(?:"(?P<qualified>[^"]+)"\s*::\s*)?'
    r'(?P<option>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)',
    re.I,
)


def _unquote(value: str) -> str:
    value = value.strip()
    return value[1:-1].replace('""', '"') if value.startswith('"') and value.endswith('"') else value


def parse_table_metadata(source: str, source_file: str = "<memory>") -> dict[str, Any]:
    lines = source.splitlines()
    header = next((line.strip() for line in lines if line.strip()), "")
    match = re.match(r"OBJECT\s+Table\s+(\d+)\s+(.+)$", header, re.I)
    if not match:
        raise ValueError(f"{source_file}: expected OBJECT Table header")
    fields: dict[str, dict[str, Any]] = {}
    i = 0
    while i < len(lines):
        field_match = _FIELD_RE.match(lines[i])
        if not field_match:
            i += 1
            continue
        start = i
        depth = 0
        body_lines = []
        while i < len(lines):
            line = lines[i]
            body_lines.append(line)
            depth += line.count("{") - line.count("}")
            i += 1
            if depth <= 0:
                break
        # NAV exports may close the field declaration on its first line and
        # place field properties (including OptionString) in a following block.
        if depth <= 0 and i < len(lines) and lines[i].strip() == "{":
            depth = 0
            while i < len(lines):
                line = lines[i]
                body_lines.append(line)
                depth += line.count("{") - line.count("}")
                i += 1
                if depth <= 0:
                    break
        body = "\n".join(body_lines)
        options = re.search(r"\bOptionString\s*=\s*([^;\r\n]+)", body, re.I)
        field = {
            "id": int(field_match.group("id")),
            "name": field_match.group("name").strip(),
            "data_type": field_match.group("type").strip(),
            "option_values": [x.strip() for x in options.group(1).rstrip(" }\\t").split(",")] if options else [],
            "source_file": source_file,
            "line": start + 1,
        }
        fields[field["name"].casefold()] = field
    return {"table_id": int(match.group(1)), "table_name": match.group(2).strip(),
            "source_file": source_file, "fields": fields}


def parse_record_variables(source: str) -> dict[str, int]:
    """Resolve local and procedure-parameter Record declarations to Table IDs."""
    declaration = re.compile(
        r'(?:"(?P<quoted>[^"]+)"|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))'
        r'(?:@\d+)?\s*:\s*Record\s+(?P<table_id>\d+)',
        re.I,
    )
    result: dict[str, int] = {}
    for match in declaration.finditer(source):
        name = match.group("quoted") or match.group("plain")
        result[name.casefold()] = int(match.group("table_id"))
    return result


def resolve_condition(
    expression: str,
    variables: dict[str, int],
    tables: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve qualified Record.Field references and Option members."""
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for match in _ACCESS_RE.finditer(expression):
        var_name = match.group("var")
        field_name = _unquote(match.group("field")).strip()
        key = (var_name.casefold(), field_name.casefold())
        if key in seen:
            continue
        seen.add(key)
        table_id = variables.get(var_name.casefold())
        record: dict[str, Any] = {"variable": var_name, "field": field_name,
                                  "resolution": "unresolved", "reason": None}
        if table_id is None:
            record["reason"] = "record_variable_not_found"
        elif table_id not in tables:
            record.update({"table_id": table_id, "reason": "table_metadata_not_found"})
        else:
            table = tables[table_id]
            field = table["fields"].get(field_name.casefold())
            record.update({"table_id": table_id, "table_name": table["table_name"],
                           "table_source": table["source_file"]})
            if field is None:
                record["reason"] = "field_not_found"
            else:
                record.update({"resolution": "resolved", "field_id": field["id"],
                               "field_type": field["data_type"],
                               "field_source": field["source_file"], "field_line": field["line"],
                               "option_values": field["option_values"]})
        refs.append(record)

    options = []
    for match in _OPTION_RE.finditer(expression):
        variable = match.group("var")
        field_name = _unquote(match.group("field")).strip()
        option = _unquote(match.group("option")).strip()
        resolved = next((r for r in refs if r["variable"].casefold() == variable.casefold()
                         and r["field"].casefold() == field_name.casefold()), None)
        if resolved and resolved["resolution"] == "resolved":
            allowed = resolved.get("option_values", [])
            options.append({"variable": variable, "field": field_name, "option": option,
                            "resolution": "resolved" if option.casefold() in {v.casefold() for v in allowed} else "unverified",
                            "allowed_values": allowed})
        else:
            options.append({"variable": variable, "field": field_name, "option": option,
                            "resolution": "unresolved", "reason": "field_reference_unresolved"})
    return {"expression": expression, "field_references": refs, "option_members": options}


def _describe_operand(expression: str, variables: dict[str, int],
                       tables: dict[int, dict[str, Any]]) -> dict[str, Any]:
    resolved = resolve_condition(expression, variables, tables)
    if resolved["option_members"]:
        option = resolved["option_members"][0]
        return {
            "kind": "option_member",
            "source": expression,
            "field": option["field"],
            "option": option["option"],
            "resolution": option["resolution"],
            "allowed_values": option.get("allowed_values", []),
        }
    if resolved["field_references"]:
        field = resolved["field_references"][0]
        return {
            "kind": "field_reference",
            "source": expression,
            "variable": field["variable"],
            "table_id": field.get("table_id"),
            "table_name": field.get("table_name"),
            "field_id": field.get("field_id"),
            "field": field["field"],
            "data_type": field.get("field_type"),
            "resolution": field["resolution"],
            "reason": field.get("reason"),
        }
    stripped = expression.strip()
    if len(stripped) >= 2 and stripped[0] == "'" and stripped[-1] == "'":
        kind = "string_literal"
    elif re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
        kind = "numeric_literal"
    elif stripped.upper() in {"TRUE", "FALSE"}:
        kind = "boolean_literal"
    else:
        kind = "raw_expression"
    return {"kind": kind, "source": expression}


def describe_normalized_condition(tree: dict[str, Any], variables: dict[str, int],
                                  tables: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Annotate normalized expression nodes with evidence-backed operand descriptions."""
    kind = tree.get("type")
    if kind == "operand":
        return _describe_operand(str(tree.get("value", "")), variables, tables)
    if kind == "comparison":
        left = _describe_operand(str(tree.get("left", "")), variables, tables)
        if "values" in tree:
            right = [_describe_operand(str(value), variables, tables) for value in tree["values"]]
        else:
            right = _describe_operand(str(tree.get("right", "")), variables, tables)
        return {
            "type": "comparison",
            "operator": tree.get("operator"),
            "left": left,
            "right": right,
            "evaluated": False,
        }
    if kind == "boolean":
        return {
            "type": "boolean",
            "operator": tree.get("operator"),
            "operands": [describe_normalized_condition(child, variables, tables)
                         for child in tree.get("operands", [])],
            "evaluated": False,
        }
    if kind == "not":
        return {
            "type": "not",
            "operand": describe_normalized_condition(tree.get("operand", {}), variables, tables),
            "evaluated": False,
        }
    return {"type": "unresolved", "source": tree, "evaluated": False}


def enrich_control_flow(node: Any, variables: dict[str, int],
                        tables: dict[int, dict[str, Any]]) -> None:
    """Attach field and Option metadata to IF predicates and CASE selectors."""
    if isinstance(node, list):
        for child in node:
            enrich_control_flow(child, variables, tables)
    elif isinstance(node, dict):
        if node.get("type") == "if" and isinstance(node.get("condition"), str):
            node["normalized_condition"] = normalize_condition_expression(node["condition"])
            node["condition_resolution"] = resolve_condition(node["condition"], variables, tables)
            node["condition_explanation"] = describe_normalized_condition(node["normalized_condition"], variables, tables)
        if node.get("type") == "case" and isinstance(node.get("expression"), str):
            node["normalized_expression"] = normalize_condition_expression(node["expression"])
            node["expression_resolution"] = resolve_condition(node["expression"], variables, tables)
            node["expression_explanation"] = describe_normalized_condition(node["normalized_expression"], variables, tables)
        for value in node.values():
            if isinstance(value, (dict, list)):
                enrich_control_flow(value, variables, tables)



_ASSIGNMENT_OPTION_RE = re.compile(
    r'(?:(?P<var>[A-Za-z_][A-Za-z0-9_@]*)\s*\\.\s*)?'
    r'(?P<field>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)\s*::\s*'
    r'(?:(?P<qualifier>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)\s*::\s*)?'
    r'(?P<option>"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_ ]*)',
    re.I,
)


def resolve_assignment(target: str, expression: str,
                       variables: dict[str, int],
                       tables: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Resolve a Record.Field assignment target and Option RHS against Table metadata."""
    target_refs = resolve_condition(target, variables, tables)["field_references"]
    field_ref = target_refs[0] if target_refs else None
    target_resolution = {
        "resolution": "unresolved",
        "reason": "assignment_target_not_a_resolved_record_field",
    }
    if field_ref:
        target_resolution = dict(field_ref)

    value_resolution: dict[str, Any] = {
        "kind": "symbolic_expression",
        "source": expression,
        "resolution": "unresolved",
        "reason": "assignment_value_not_a_resolved_option_member",
    }
    option_match = _ASSIGNMENT_OPTION_RE.search(expression)
    if option_match:
        option_field = _unquote(option_match.group("field")).strip()
        qualifier = _unquote(option_match.group("qualifier") or "").strip()
        option = _unquote(option_match.group("option")).strip()
        same_field = bool(field_ref and (
            option_field.casefold() == field_ref["field"].casefold()
            or qualifier.casefold() == field_ref["field"].casefold()
        ))
        if field_ref and field_ref.get("resolution") == "resolved" and same_field:
            allowed = field_ref.get("option_values", [])
            resolution = (
                "resolved" if option.casefold() in {value.casefold() for value in allowed}
                else "unverified"
            )
            value_resolution = {
                "kind": "option_member",
                "field": field_ref["field"],
                "option": option,
                "resolution": resolution,
                "allowed_values": allowed,
                "source": expression,
                "evaluated": False,
            }
        else:
            value_resolution = {
                "kind": "option_member",
                "field": option_field,
                "option": option,
                "resolution": "unresolved",
                "reason": "option_member_does_not_match_resolved_assignment_target",
                "source": expression,
                "evaluated": False,
            }
    elif field_ref and field_ref.get("resolution") == "resolved":
        value_resolution = {
            "kind": "expression",
            "source": expression,
            "resolution": "not_option_or_unresolved_expression",
            "field_type": field_ref.get("field_type"),
            "evaluated": False,
        }

    return {
        "target": target,
        "expression": expression,
        "target_resolution": target_resolution,
        "value_resolution": value_resolution,
        "evaluated": False,
    }


def enrich_assignment_flow(flow: dict[str, Any], nodes: Any,
                           variables: dict[str, int],
                           tables: dict[int, dict[str, Any]]) -> None:
    """Attach Table/Field/Option metadata to assignment events and IF contexts."""
    for event in flow.get("events", []):
        if event.get("kind") in {
            "explicit_assignment", "interprocedural_var_mutation"
        }:
            event["semantic_assignment"] = resolve_assignment(
                str(event.get("target", "")),
                str(event.get("expression", "")),
                variables, tables,
            )

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            context = value.get("assignment_context")
            if isinstance(context, dict):
                for alternative in context.get("alternatives", []):
                    for assignment in alternative.get("known_assignments", []):
                        assignment["semantic_assignment"] = resolve_assignment(
                            str(assignment.get("target", "")),
                            str(assignment.get("expression", "")),
                            variables, tables,
                        )
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)

    walk(nodes)


def load_table_sources(paths: list[str | Path]) -> dict[int, dict[str, Any]]:
    tables = {}
    for path_value in paths:
        path = Path(path_value)
        table = parse_table_metadata(path.read_text(encoding="utf-8-sig", errors="replace"), str(path))
        tables[table["table_id"]] = table
    return tables
