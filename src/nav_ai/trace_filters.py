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
    max_call_depth: int = 2,
) -> dict[str, Any]:
    """Compose Record-filter effects across a bounded chain of traced CALL edges."""
    from copy import deepcopy
    from .source_discovery import _resolve_source

    if max_call_depth < 0:
        raise ValueError("max_call_depth must be zero or greater")
    tables = tables or {}
    source_cache: dict[str, dict[str, Any]] = {}
    contexts: dict[str, dict[str, Any]] = {}
    edge_info: list[dict[str, Any]] = []

    def context_for(node: str) -> dict[str, Any]:
        if node in contexts:
            return contexts[node]
        object_node, procedure_name = node.split(".", 1)
        object_type, object_id = object_node.rsplit(" ", 1)
        source = source_cache.setdefault(
            object_node, _resolve_source(catalog, symbols, object_type, int(object_id))
        )
        context: dict[str, Any] = {"object_node": object_node, "procedure": procedure_name, "source": source}
        if source.get("status") == "resolved":
            parsed = parse_nav_text(source["raw_block"], source["source_path"])
            matches = [p for p in parsed.get("procedures", [])
                       if p["name"].casefold() == procedure_name.casefold()]
            if len(matches) == 1:
                procedure = matches[0]
                raw_lines = procedure["raw"].splitlines()
                begin = next((i for i, line in enumerate(raw_lines)
                              if line.strip().upper() == "BEGIN"), None)
                if begin is not None:
                    body = "\n".join(raw_lines[begin:])
                    line_offset = procedure["line_start"] + begin - 1
                    tree = analyze_control_flow(
                        body, parsed["object"]["type"], parsed["object"]["id"],
                        parsed["object"]["name"], procedure["name"],
                        source["source_path"], line_offset=line_offset,
                    )
                    variable_source = "\n".join(v["raw"] for v in parsed.get("variables", [])) + "\n" + procedure["raw"]
                    variables = parse_record_variables(variable_source)
                    context.update({
                        "parsed": parsed, "procedure_data": procedure, "tree": tree,
                        "variables": variables, "line_offset": source.get("object_line_offset", 0),
                    })
        contexts[node] = context
        return context

    for edge in edges:
        item = {**edge, "status": "unavailable", "caller_filter_effect_map": {}}
        try:
            caller = context_for(edge["src"])
            callee = context_for(edge["dst"])
            item.update({
                "caller_object": caller["object_node"], "caller_procedure": caller["procedure"],
                "callee_object": callee["object_node"], "callee_procedure": callee["procedure"],
            })
            if caller.get("tree") and callee.get("tree"):
                binding = analyze_direct_call_bindings(
                    caller["source"]["raw_block"], callee["source"]["raw_block"],
                    callee["procedure"], caller["source"]["source_path"],
                    callee["source"]["source_path"],
                )
                item["binding"] = binding
                item["status"] = "analyzed" if binding.get("call_sites") else "no_matching_direct_call"
            else:
                item["reason"] = "source_or_procedure_unavailable"
                item["status"] = "source_unavailable"
        except (ValueError, KeyError, OSError) as exc:
            item.update({"status": "analysis_unavailable", "reason": str(exc)})
        edge_info.append(item)

    summaries: dict[str, dict[str, Any]] = {}
    for node, context in contexts.items():
        if context.get("tree"):
            summaries[node] = analyze_record_filter_paths(
                context["tree"]["nodes"], context["variables"], tables,
                context["source"]["source_path"],
            )

    def map_summary(edge: dict[str, Any], summary: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
        mapped: dict[int, list[dict[str, Any]]] = {}
        binding = edge.get("binding", {})
        context = contexts.get(edge["dst"], {})
        procedure = context.get("procedure_data", {})
        formals = {
            p["name"].casefold(): p for p in procedure.get("parameters", [])
            if p.get("by_reference") and re.search(r"Record\\s+\\d+", p.get("data_type", ""), re.I)
        }
        for site in binding.get("call_sites", []):
            bool_args = {
                a["parameter"]: a["argument"].upper() == "TRUE"
                for a in site.get("arguments", [])
                if a.get("type_match") == "compatible_literal"
                and a.get("formal_type", "").casefold() == "boolean"
                and a.get("argument", "").upper() in {"TRUE", "FALSE"}
            }
            for argument in site.get("arguments", []):
                formal = argument.get("parameter", "")
                formal_key = formal.casefold()
                if not argument.get("by_reference") or formal_key not in formals:
                    continue
                actual = str(argument.get("argument", "")).strip()
                if not _SIMPLE_NAME.fullmatch(actual):
                    continue
                record_type = re.search(r"Record\\s+(\\d+)", formals[formal_key]["data_type"], re.I)
                if not record_type or argument.get("argument_record_type") != f"Table {record_type.group(1)}":
                    continue
                for event in summary.get("events", []):
                    if str(event.get("record_variable", "")).casefold() != formal_key:
                        continue
                    if _resolve_boolean_path(event.get("path") or [], bool_args) != "compatible":
                        continue
                    operation = event.get("operation")
                    if operation not in {"RESET", "SETRANGE", "SETFILTER", "SETRANGE_CLEAR"}:
                        continue
                    mapped.setdefault(int(site["line"]), []).append({
                        "operation": operation, "record_variable": actual,
                        "field": event.get("field"), "arguments": deepcopy(event.get("arguments", [])),
                        "callee_line": event.get("line"),
                        "callee_source_file": context["source"]["source_path"],
                        "callee_parameter": formal, "path": deepcopy(event.get("path", [])),
                        "path_specialization": "call_site_boolean_arguments" if event.get("path") else "unconditional",
                        "propagation": "bounded_interprocedural", "runtime_evaluated": False,
                    })
        return mapped

    propagated_hops = 0
    for _ in range(max_call_depth):
        effects_by_caller: dict[str, dict[int, list[dict[str, Any]]]] = {}
        for edge in edge_info:
            if edge.get("status") not in {"analyzed", "no_matching_direct_call"}:
                continue
            summary = summaries.get(edge["dst"])
            if not summary:
                continue
            mapped = map_summary(edge, summary)
            for line, effects in mapped.items():
                target = effects_by_caller.setdefault(edge["src"], {})
                target.setdefault(line, []).extend(effects)
        updated: dict[str, dict[str, Any]] = {}
        for node, call_effects in effects_by_caller.items():
            context = contexts.get(node, {})
            if not context.get("tree"):
                continue
            updated[node] = analyze_record_filter_paths(
                context["tree"]["nodes"], context["variables"], tables,
                context["source"]["source_path"], call_effects=call_effects,
            )
        if not updated:
            break
        summaries.update(updated)
        propagated_hops += 1

    final_edges = []
    for edge in edge_info:
        result = {k: v for k, v in edge.items() if k != "binding"}
        binding = edge.get("binding")
        summary = summaries.get(edge["dst"])
        if binding:
            result["call_binding"] = binding
            if summary:
                result["filter_summary"] = summary
                mapped = map_summary(edge, summary)
                result["caller_filter_effect_map"] = {str(k): v for k, v in mapped.items()}
                result["parameter_filter_event_counts"] = {
                    p["name"]: sum(1 for e in summary.get("events", [])
                                   if str(e.get("record_variable", "")).casefold() == p["name"].casefold())
                    for p in contexts[edge["dst"]].get("procedure_data", {}).get("parameters", [])
                    if p.get("by_reference") and re.search(r"Record\\s+\\d+", p.get("data_type", ""), re.I)
                }
            else:
                result["status"] = "callee_summary_unavailable"
        result["runtime_evaluated"] = False
        final_edges.append(result)

    return {
        "analysis": "bounded_interprocedural_record_filter_effect_composition",
        "edge_count": len(final_edges),
        "analyzed_edge_count": sum(e["status"] == "analyzed" for e in final_edges),
        "max_call_depth": max_call_depth,
        "propagated_hops": propagated_hops,
        "edges": final_edges,
        "procedure_summaries": [
            {"procedure": node, "summary": summary, "runtime_evaluated": False}
            for node, summary in sorted(summaries.items())
        ],
        "runtime_evaluated": False,
        "limitations": [
            "Only discovered direct CALL edges and simple typed VAR Record arguments are composed.",
            "Only explicit RESET, SETRANGE, SETFILTER and field-clearing SETRANGE operations are propagated.",
            "Conditional effects require supported Boolean literal arguments at each call boundary.",
            "Composition is bounded by max_call_depth; cycles cannot cause unbounded traversal.",
            "Filter expressions and placeholders remain symbolic; no filter is executed and no row existence is inferred.",
            "Complex actual arguments, non-VAR Records, WITH scopes, RecordRef/FieldRef and implicit effects remain unresolved.",
        ],
    }
