"""Direct interprocedural Record-filter effects for traced CALL edges."""
from __future__ import annotations

import re
from typing import Any

from .control_flow import analyze_control_flow
from .interprocedural import analyze_direct_call_bindings, _resolve_boolean_path
from .parser import parse_nav_text
from .record_filters import analyze_record_filter_paths
from .semantic_conditions import parse_record_variables


_SIMPLE_NAME = re.compile(r'^(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_@]*)$')


def analyze_trace_filter_edges(
    edges: list[dict[str, Any]],
    catalog: dict[tuple[str, int], list[dict[str, Any]]],
    symbols: Any = None,
    tables: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Map callee SETFILTER/SETRANGE/RESET operations through VAR Record arguments."""
    from .source_discovery import _resolve_source

    tables = tables or {}
    source_cache: dict[str, dict[str, Any]] = {}

    def source_for(node: str):
        object_node, procedure = node.split(".", 1)
        object_type, object_id = object_node.rsplit(" ", 1)
        if object_node not in source_cache:
            source_cache[object_node] = _resolve_source(
                catalog, symbols, object_type, int(object_id)
            )
        return object_node, procedure, source_cache[object_node]

    output = []
    for edge in edges:
        result = {**edge, "status": "unavailable", "caller_filter_effect_map": {}}
        try:
            caller_object, caller_proc, caller = source_for(edge["src"])
            callee_object, callee_proc, callee = source_for(edge["dst"])
            if caller.get("status") != "resolved" or callee.get("status") != "resolved":
                result["reason"] = "source_unavailable"
                output.append(result)
                continue
            binding = analyze_direct_call_bindings(
                caller["raw_block"], callee["raw_block"], callee_proc,
                caller["source_path"], callee["source_path"],
            )
            parsed = parse_nav_text(callee["raw_block"], callee["source_path"])
            matches = [p for p in parsed.get("procedures", [])
                       if p["name"].casefold() == callee_proc.casefold()]
            if len(matches) != 1:
                result["reason"] = "callee_procedure_not_found"
                output.append(result)
                continue
            procedure = matches[0]
            raw_lines = procedure["raw"].splitlines()
            begin = next((i for i, line in enumerate(raw_lines)
                          if line.strip().upper() == "BEGIN"), None)
            if begin is None:
                result["reason"] = "callee_procedure_has_no_begin"
                output.append(result)
                continue
            body = "\n".join(raw_lines[begin:])
            line_offset = procedure["line_start"] + begin - 1
            tree = analyze_control_flow(
                body, parsed["object"]["type"], parsed["object"]["id"],
                parsed["object"]["name"], procedure["name"],
                callee["source_path"], line_offset=line_offset,
            )
            variable_source = "\n".join(
                variable["raw"] for variable in parsed.get("variables", [])
            ) + "\n" + procedure["raw"]
            variables = parse_record_variables(variable_source)
            filter_summary = analyze_record_filter_paths(
                tree["nodes"], variables, tables, callee["source_path"]
            )
            formal_types = {
                parameter["name"].casefold(): parameter
                for parameter in procedure.get("parameters", [])
                if parameter.get("by_reference")
                and re.search(r"Record\s+\d+", parameter.get("data_type", ""), re.I)
            }
            parameter_events = {
                name: [
                    event for event in filter_summary.get("events", [])
                    if str(event.get("record_variable", "")).casefold() == name
                ]
                for name in formal_types
            }
            mapped: dict[int, list[dict[str, Any]]] = {}
            for site in binding.get("call_sites", []):
                bool_args = {
                    arg["parameter"]: arg["argument"].upper() == "TRUE"
                    for arg in site.get("arguments", [])
                    if arg.get("type_match") == "compatible_literal"
                    and arg.get("formal_type", "").casefold() == "boolean"
                    and arg.get("argument", "").upper() in {"TRUE", "FALSE"}
                }
                for argument in site.get("arguments", []):
                    formal = argument.get("parameter", "")
                    if not argument.get("by_reference") or formal.casefold() not in formal_types:
                        continue
                    actual = str(argument.get("argument", "")).strip()
                    if not _SIMPLE_NAME.fullmatch(actual):
                        continue
                    formal_record = re.search(
                        r"Record\s+(\d+)", formal_types[formal.casefold()]["data_type"], re.I
                    )
                    if not formal_record or argument.get("argument_record_type") != f"Table {formal_record.group(1)}":
                        continue
                    for event in parameter_events[formal.casefold()]:
                        path_state = _resolve_boolean_path(event.get("path") or [], bool_args)
                        if path_state != "compatible":
                            continue
                        operation = event.get("operation")
                        if operation not in {"RESET", "SETRANGE", "SETFILTER", "SETRANGE_CLEAR"}:
                            continue
                        mapped.setdefault(int(site["line"]), []).append({
                            "operation": operation,
                            "record_variable": actual,
                            "field": event.get("field"),
                            "arguments": event.get("arguments", []),
                            "callee_line": event.get("line"),
                            "callee_source_file": callee["source_path"],
                            "callee_parameter": formal,
                            "path": event.get("path", []),
                            "path_specialization": "call_site_boolean_arguments" if event.get("path") else "unconditional",
                            "runtime_evaluated": False,
                        })
            result.update({
                "status": "analyzed" if binding.get("call_sites") else "no_matching_direct_call",
                "caller_object": caller_object,
                "caller_procedure": caller_proc,
                "callee_object": callee_object,
                "callee_procedure": callee_proc,
                "filter_summary": filter_summary,
                "caller_filter_effect_map": {
                    str(line): effects for line, effects in mapped.items()
                },
                "caller_object_line_offset": caller.get("object_line_offset", 0),
                "runtime_evaluated": False,
            })
        except (ValueError, KeyError, OSError) as exc:
            result.update({"status": "analysis_unavailable", "reason": str(exc)})
        result["runtime_evaluated"] = False
        output.append(result)

    return {
        "analysis": "static_interprocedural_record_filter_effects",
        "edge_count": len(output),
        "analyzed_edge_count": sum(item["status"] == "analyzed" for item in output),
        "edges": output,
        "runtime_evaluated": False,
        "limitations": [
            "Only direct calls with simple typed VAR Record arguments are mapped.",
            "Only explicit SETRANGE, SETFILTER, SETRANGE-clear and RESET operations are propagated.",
            "Conditional callee filter operations are propagated only when simple Boolean call literals select the path.",
            "Filter expressions and placeholders remain symbolic; no filter is executed and no row existence is inferred.",
            "Nested interprocedural filter effects are not recursively composed yet.",
        ],
    }
