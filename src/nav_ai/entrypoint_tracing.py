"""Connect source-declared NAV entry points to static CALL graph evidence."""
from __future__ import annotations

from collections import deque
from typing import Any


def trace_entrypoint_graph(
    graph,
    entries: list[dict[str, Any]],
    *,
    max_depth: int = 5,
    max_nodes: int = 5000,
) -> dict[str, Any]:
    """Trace CALL-reachable procedures per declaring object and explicit RunObject targets.

    Results describe static reachability only. They do not assert invocation order,
    UI availability, branch selection, or runtime execution.
    """
    if max_depth < 0 or max_nodes < 1:
        raise ValueError("max_depth must be non-negative and max_nodes positive")

    adjacency: dict[str, list[str]] = {}
    for src, dst in graph.execute(
        "SELECT src,dst FROM edges WHERE kind='CALL' ORDER BY src,dst"
    ):
        adjacency.setdefault(str(src).casefold(), []).append((str(dst).casefold(), str(dst)))

    procedures = {
        str(row[0]).casefold(): str(row[0])
        for row in graph.execute("SELECT node FROM procedures")
    }
    objects = {
        str(row[0]).casefold(): str(row[0])
        for row in graph.execute("SELECT node FROM objects")
    }

    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(str(entry["object"]), []).append(entry)

    traces: list[dict[str, Any]] = []
    for declared_object in sorted(grouped, key=str.casefold):
        object_node = objects.get(declared_object.casefold())
        if object_node is None:
            traces.append({
                "entry_object": declared_object,
                "status": "object_not_indexed",
                "entry_count": len(grouped[declared_object]),
                "reachable_procedures": [],
                "unresolved_call_targets": [],
                "runobject_targets": [],
            })
            continue

        starts = [
            str(row[0]) for row in graph.execute(
                "SELECT node FROM procedures WHERE object_node=? ORDER BY node",
                (object_node,),
            )
        ]
        trigger_scope = f"{object_node} TRIGGERS"
        if trigger_scope.casefold() in adjacency:
            starts.append(trigger_scope)

        depths: dict[str, int] = {}
        parents: dict[str, str] = {}
        queue = deque()
        for start in starts:
            key = start.casefold()
            if key not in depths:
                depths[key] = 0
                queue.append(key)

        unresolved: set[tuple[str, str]] = set()
        truncated = False
        while queue:
            current = queue.popleft()
            depth = depths[current]
            if depth >= max_depth:
                continue
            for target_key, target_label in adjacency.get(current, []):
                if target_key not in procedures:
                    unresolved.add((procedures.get(current, current), target_label))
                    continue
                if target_key in depths:
                    continue
                if len(depths) >= max_nodes:
                    truncated = True
                    queue.clear()
                    break
                depths[target_key] = depth + 1
                parents[target_key] = current
                queue.append(target_key)

        reachable = []
        for key in sorted(depths, key=lambda item: (depths[item], procedures.get(item, item))):
            if key not in procedures:
                continue
            path = [procedures[key]]
            cursor = key
            while cursor in parents:
                cursor = parents[cursor]
                if cursor in procedures:
                    path.append(procedures[cursor])
            path.reverse()
            reachable.append({
                "procedure": procedures[key],
                "depth": depths[key],
                "call_path": path,
            })

        runobject_targets = sorted({
            str(entry["target"])
            for entry in grouped[declared_object]
            if entry.get("entry_kind") == "object_launch_property" and entry.get("target")
        })
        traces.append({
            "entry_object": object_node,
            "status": "traced",
            "entry_count": len(grouped[declared_object]),
            "entry_kinds": sorted({str(entry["entry_kind"]) for entry in grouped[declared_object]}),
            "reachable_procedure_count": len(reachable),
            "reachable_procedures": reachable,
            "unresolved_call_targets": [
                {"source": source, "target": target}
                for source, target in sorted(unresolved)
            ],
            "runobject_targets": [
                {
                    "target": target,
                    "indexed": target.casefold() in objects,
                    "evidence": "RunObject_property",
                    "runtime_invoked": False,
                }
                for target in runobject_targets
            ],
            "truncated": truncated,
            "limits": {"max_depth": max_depth, "max_nodes": max_nodes},
        })

    return {
        "entry_object_count": len(traces),
        "traced_object_count": sum(item["status"] == "traced" for item in traces),
        "unindexed_object_count": sum(item["status"] == "object_not_indexed" for item in traces),
        "traces": traces,
        "semantics": {
            "method": "source-declared entry object to bounded static CALL reachability",
            "runtime_executed": False,
            "call_order_proven": False,
            "limitations": [
                "CALL edges express static reachability, not execution order or invocation.",
                "The graph is object/procedure scoped; individual Page Action and trigger bodies are not yet mapped to distinct graph nodes.",
                "RunObject target indexing does not prove that the target was launched.",
                "Dynamic RUN targets, event subscribers, Job Queue configuration and external invocations need additional evidence.",
            ],
        },
    }
