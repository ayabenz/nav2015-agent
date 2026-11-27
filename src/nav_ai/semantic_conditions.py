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
    result: dict[str, int] = {}
    for line in source.splitlines():
        match = _VAR_RE.match(line)
        if match:
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
        if node.get("type") == "case" and isinstance(node.get("expression"), str):
            node["normalized_expression"] = normalize_condition_expression(node["expression"])
            node["expression_resolution"] = resolve_condition(node["expression"], variables, tables)
        for value in node.values():
            if isinstance(value, (dict, list)):
                enrich_control_flow(value, variables, tables)


def load_table_sources(paths: list[str | Path]) -> dict[int, dict[str, Any]]:
    tables = {}
    for path_value in paths:
        path = Path(path_value)
        table = parse_table_metadata(path.read_text(encoding="utf-8-sig", errors="replace"), str(path))
        tables[table["table_id"]] = table
    return tables
