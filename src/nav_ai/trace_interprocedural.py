"""Bounded interprocedural VAR-effect composition for dependency-graph traces.

Only direct source-level calls and explicit VAR parameter assignments are
propagated. Results are symbolic static evidence, never runtime execution.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .interprocedural import analyze_direct_call_bindings, build_caller_var_effect_map
from .var_mutation import analyze_var_parameter_mutations


def analyze_trace_call_edges(
    edges: list[dict[str, Any]],
    catalog: dict[tuple[str, int], list[dict[str, Any]]],
    symbols: Any = None,
    max_call_depth: int = 2,
) -> dict[str, Any]:
    """Compose explicit VAR effects across a bounded number of discovered edges.

    Each round propagates one additional call hop from callee summaries into
    caller procedure summaries. Cycles cannot cause unbounded traversal because
    the number of rounds is explicitly bounded.
    """
    from .source_discovery import _resolve_source

    if max_call_depth < 0:
        raise ValueError("max_call_depth must be zero or greater")

    object_cache: dict[str, dict[str, Any]] = {}
    node_info: dict[str, dict[str, Any]] = {}
    edge_info: list[dict[str, Any]] = []

    def source_for(node: str) -> tuple[str, str, dict[str, Any]]:
        object_node, procedure = node.split(".", 1)
        object_type, object_id = object_node.rsplit(" ", 1)
        if object_node not in object_cache:
            object_cache[object_node] = _resolve_source(
                catalog, symbols, object_type, int(object_id)
            )
        source = object_cache[object_node]
        node_info[node] = {
            "object_node": object_node,
            "procedure": procedure,
            "source": source,
        }
        return object_node, procedure, source

    for edge in edges:
        src, dst = edge["src"], edge["dst"]
        item = {**edge, "status": "pending"}
        try:
            caller_object, caller_proc, caller = source_for(src)
            callee_object, callee_proc, callee = source_for(dst)
            item.update({
                "caller_object": caller_object,
                "caller_procedure": caller_proc,
                "callee_object": callee_object,
                "callee_procedure": callee_proc,
            })
            if caller.get("status") != "resolved" or callee.get("status") != "resolved":
                item.update({
                    "status": "source_unavailable",
                    "caller_source_status": caller.get("status"),
                    "callee_source_status": callee.get("status"),
                })
            else:
                item["binding"] = analyze_direct_call_bindings(
                    caller["raw_block"], callee["raw_block"], callee_proc,
                    caller["source_path"], callee["source_path"],
                )
                item["status"] = (
                    "analyzed" if item["binding"].get("call_sites")
                    else "no_matching_direct_call"
                )
        except (ValueError, KeyError, OSError) as exc:
            item.update({"status": "analysis_unavailable", "reason": str(exc)})
        edge_info.append(item)

    # Seed each procedure with its own explicit, local VAR assignments.
    summaries: dict[str, dict[str, Any]] = {}
    for node, info in node_info.items():
        source = info["source"]
        if source.get("status") != "resolved":
            continue
        try:
            summaries[node] = analyze_var_parameter_mutations(
                source["raw_block"], info["procedure"], source["source_path"]
            )
        except (ValueError, KeyError, OSError):
            continue

    def binding_with_summary(binding: dict[str, Any],
                             summary: dict[str, Any]) -> dict[str, Any]:
        enriched = deepcopy(binding)
        effects = {
            item["parameter"].casefold(): item
            for item in summary.get("var_parameters", [])
        }
        for site in enriched.get("call_sites", []):
            site["var_parameter_effects"] = []
            for argument in site.get("arguments", []):
                if not argument.get("by_reference"):
                    continue
                effect = effects.get(argument["parameter"].casefold())
                if effect:
                    site["var_parameter_effects"].append({
                        "parameter": argument["parameter"],
                        "caller_argument": argument.get("argument"),
                        "caller_argument_record_type": argument.get("argument_record_type"),
                        "mutation_state": effect["mutation_state"],
                        "mutations": deepcopy(effect["mutations"]),
                        "propagation": "symbolic_only",
                    })
        return enriched

    def compose_one_round() -> dict[str, dict[int, list[dict[str, Any]]]]:
        effects_by_caller: dict[str, dict[int, list[dict[str, Any]]]] = {}
        for edge in edge_info:
            if edge["status"] not in {"analyzed", "no_matching_direct_call"}:
                continue
            callee_summary = summaries.get(edge["dst"])
            if not callee_summary or not edge.get("binding"):
                continue
            enriched = binding_with_summary(edge["binding"], callee_summary)
            effect_map = build_caller_var_effect_map(enriched)
            if not effect_map:
                continue
            caller_effects = effects_by_caller.setdefault(edge["src"], {})
            for line, effects in effect_map.items():
                caller_effects.setdefault(line, []).extend(effects)
        return effects_by_caller

    propagated_hops = 0
    for _ in range(max_call_depth):
        effects_by_caller = compose_one_round()
        updated: dict[str, dict[str, Any]] = {}
        for node, call_effects in effects_by_caller.items():
            info = node_info.get(node)
            if not info:
                continue
            source = info["source"]
            try:
                updated[node] = analyze_var_parameter_mutations(
                    source["raw_block"], info["procedure"], source["source_path"],
                    call_effects=call_effects,
                )
            except (ValueError, KeyError, OSError):
                continue
        if not updated:
            break
        summaries.update(updated)
        propagated_hops += 1

    final_edges: list[dict[str, Any]] = []
    unresolved = 0
    for edge in edge_info:
        result = {k: v for k, v in edge.items() if k != "binding"}
        binding = edge.get("binding")
        if binding:
            callee_summary = summaries.get(edge["dst"])
            if callee_summary:
                enriched = binding_with_summary(binding, callee_summary)
                result["call_binding"] = enriched
                effect_map = build_caller_var_effect_map(enriched)
                result["caller_state_effect_map"] = {
                    str(line): effects for line, effects in effect_map.items()
                }
                result["callee_var_mutation_summary"] = callee_summary
                result["status"] = (
                    "analyzed" if enriched.get("call_sites")
                    else "no_matching_direct_call"
                )
            else:
                result["call_binding"] = binding
                result["status"] = "callee_summary_unavailable"
        if result["status"] not in {"analyzed"}:
            unresolved += 1
        result["runtime_evaluated"] = False
        final_edges.append(result)

    procedure_summaries = []
    for node, summary in sorted(summaries.items()):
        procedure_summaries.append({
            "procedure": node,
            "summary": summary,
            "runtime_evaluated": False,
        })

    return {
        "analysis": "bounded_interprocedural_var_effect_composition",
        "edge_count": len(final_edges),
        "analyzed_edge_count": sum(item["status"] == "analyzed" for item in final_edges),
        "unresolved_edge_count": unresolved,
        "max_call_depth": max_call_depth,
        "propagated_hops": propagated_hops,
        "procedure_summaries": procedure_summaries,
        "edges": final_edges,
        "runtime_evaluated": False,
        "limitations": [
            "Only discovered CALL edges with resolved source and direct receiver.Procedure(...) syntax are bound.",
            "Only explicit assignments to callee VAR parameters and their qualified fields are summarized.",
            "Boolean path specialization is applied only when Boolean literals are present at the call site.",
            "Composition is bounded by max_call_depth; cycles cannot cause unbounded traversal.",
            "Effects remain symbolic; expressions, database state, triggers, implicit writes and NAV execution are not evaluated.",
            "WITH-scoped/unqualified calls, dynamic dispatch, indirect callbacks and complex actual arguments remain unresolved.",
        ],
    }
