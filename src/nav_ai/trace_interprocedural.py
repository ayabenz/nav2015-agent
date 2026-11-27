"""Interprocedural summaries for discovered dependency-graph call edges.

This layer deliberately reports direct syntactic bindings and explicit VAR
parameter mutations only. It does not claim that a call or mutation executed.
"""
from __future__ import annotations

from typing import Any

from .interprocedural import analyze_direct_call_bindings, build_caller_var_effect_map
from .var_mutation import analyze_var_parameter_mutations


def analyze_trace_call_edges(
    edges: list[dict[str, Any]],
    catalog: dict[tuple[str, int], list[dict[str, Any]]],
    symbols: Any = None,
) -> dict[str, Any]:
    """Bind each discovered procedure edge to source and summarize VAR effects."""
    from .source_discovery import _resolve_source

    cache: dict[str, dict[str, Any]] = {}

    def source_for(node: str) -> tuple[str, str, dict[str, Any]]:
        object_node, procedure = node.split(".", 1)
        object_type, object_id = object_node.rsplit(" ", 1)
        if object_node not in cache:
            cache[object_node] = _resolve_source(catalog, symbols, object_type, int(object_id))
        return object_node, procedure, cache[object_node]

    results: list[dict[str, Any]] = []
    unresolved = 0
    for edge in edges:
        src, dst = edge["src"], edge["dst"]
        try:
            caller_object, caller_proc, caller = source_for(src)
            callee_object, callee_proc, callee = source_for(dst)
            if caller.get("status") != "resolved" or callee.get("status") != "resolved":
                unresolved += 1
                results.append({
                    **edge, "status": "source_unavailable",
                    "caller_source_status": caller.get("status"),
                    "callee_source_status": callee.get("status"),
                    "runtime_evaluated": False,
                })
                continue
            summary = analyze_var_parameter_mutations(
                callee["raw_block"], callee_proc, callee["source_path"]
            )
            effects_by_parameter = {
                item["parameter"].casefold(): item
                for item in summary.get("var_parameters", [])
            }
            binding = analyze_direct_call_bindings(
                caller["raw_block"], callee["raw_block"], callee_proc,
                caller["source_path"], callee["source_path"],
            )
            for site in binding.get("call_sites", []):
                site["var_parameter_effects"] = []
                for argument in site.get("arguments", []):
                    if not argument.get("by_reference"):
                        continue
                    effect = effects_by_parameter.get(argument["parameter"].casefold())
                    if effect:
                        site["var_parameter_effects"].append({
                            "parameter": argument["parameter"],
                            "caller_argument": argument.get("argument"),
                            "caller_argument_record_type": argument.get("argument_record_type"),
                            "mutation_state": effect["mutation_state"],
                            "mutations": effect["mutations"],
                            "propagation": "symbolic_only",
                        })
            effect_map = build_caller_var_effect_map(binding)
            results.append({
                **edge,
                "status": "analyzed" if binding.get("call_sites") else "no_matching_direct_call",
                "caller_object": caller_object,
                "caller_procedure": caller_proc,
                "callee_object": callee_object,
                "callee_procedure": callee_proc,
                "call_binding": binding,
                "callee_var_mutation_summary": summary,
                "caller_state_effect_map": {
                    str(line): effects for line, effects in effect_map.items()
                },
                "runtime_evaluated": False,
            })
        except (ValueError, KeyError, OSError) as exc:
            unresolved += 1
            results.append({
                **edge, "status": "analysis_unavailable",
                "reason": str(exc), "runtime_evaluated": False,
            })
    return {
        "analysis": "discovered_edge_interprocedural_var_effects",
        "edge_count": len(results),
        "analyzed_edge_count": sum(item["status"] == "analyzed" for item in results),
        "unresolved_edge_count": unresolved,
        "edges": results,
        "runtime_evaluated": False,
        "limitations": [
            "Only discovered CALL edges with resolved source and direct receiver.Procedure(...) syntax are bound.",
            "Only explicit assignments to callee VAR parameters and their qualified fields are summarized.",
            "Boolean path specialization is applied only when Boolean literals are present at the call site.",
            "Effects remain symbolic; expressions, database state and NAV execution are not evaluated.",
            "Nested and transitive effects are not recursively promoted by this edge-level summary.",
        ],
    }
