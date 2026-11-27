"""Resolve conservative per-entry-point source calls against the NAV graph."""
from __future__ import annotations

import re
import sqlite3
from collections import deque
from typing import Any

STRING_RE = re.compile(r"'(?:[^']|'')*'")


def _mask_non_code(text: str) -> str:
    text = STRING_RE.sub(" ", text)
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r"\{[^{}]*\}", " ", text)


def map_entrypoint_calls(
    graph: sqlite3.Connection,
    entry_bodies: dict[str, Any],
    *,
    max_depth: int = 5,
    max_nodes: int = 5000,
) -> dict[str, Any]:
    """Map unique same-object procedure identifiers and explicit RUN targets."""
    if max_depth < 0 or max_nodes < 1:
        raise ValueError("max_depth must be non-negative and max_nodes positive")

    objects = {
        str(node).casefold(): str(node)
        for (node,) in graph.execute("SELECT node FROM objects")
    }
    procedures = graph.execute(
        "SELECT node, object_node, name FROM procedures ORDER BY node"
    ).fetchall()
    by_object: dict[str, list[tuple[str, str]]] = {}
    for node, object_node, name in procedures:
        by_object.setdefault(str(object_node).casefold(), []).append((str(name), str(node)))

    adjacency: dict[str, list[str]] = {}
    for src, dst in graph.execute("SELECT src,dst FROM edges WHERE kind='CALL' ORDER BY src,dst"):
        adjacency.setdefault(str(src).casefold(), []).append(str(dst))

    mapped: list[dict[str, Any]] = []
    for entry in entry_bodies.get("entries", []):
        owner = str(entry.get("object", ""))
        body = _mask_non_code(str(entry.get("body", "")))
        direct: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        seen: set[str] = set()

        for proc_name, proc_node in by_object.get(owner.casefold(), []):
            pattern = re.compile(
                r"(?<![\w."])"
                + re.escape(proc_name.strip('"'))
                + r"\s*(?:\(|;)",
                re.I,
            )
            if pattern.search(body) and proc_node.casefold() not in seen:
                seen.add(proc_node.casefold())
                direct.append({
                    "target": proc_node,
                    "kind": "local_procedure_name_match",
                    "confidence": "source_identifier_match",
                })

        run_re = re.compile(
            r"\b(CODEUNIT|REPORT|PAGE|XMLPORT)\s*\.\s*RUN(?:MODAL)?\s*\(\s*"
            r"(?:\1\s*::\s*)?(?:(\d+)|\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_]*))",
            re.I,
        )
        for match in run_re.finditer(body):
            kind = match.group(1).title().replace("Xmlport", "XMLport")
            object_node = None
            if match.group(2):
                object_node = f"{kind} {int(match.group(2))}"
            elif match.group(3):
                rows = graph.execute(
                    "SELECT node FROM objects WHERE type=? COLLATE NOCASE AND name=? COLLATE NOCASE",
                    (kind, match.group(3)),
                ).fetchall()
                if len(rows) == 1:
                    object_node = str(rows[0][0])
            if object_node and object_node.casefold() in objects:
                target = objects[object_node.casefold()]
                if target.casefold() not in seen:
                    seen.add(target.casefold())
                    direct.append({
                        "target": target,
                        "kind": "explicit_run_object",
                        "confidence": "explicit_object_reference",
                    })
            else:
                unresolved.append({
                    "expression": match.group(0),
                    "reason": "RUN target is not uniquely resolvable from graph metadata",
                })

        roots = [item["target"] for item in direct if "." in item["target"]]
        reached: dict[str, int] = {}
        parents: dict[str, str] = {}
        queue = deque((root, 0) for root in roots)
        truncated = False
        while queue:
            node, depth = queue.popleft()
            key = node.casefold()
            if key in reached:
                continue
            if len(reached) >= max_nodes:
                truncated = True
                break
            reached[key] = depth
            if depth >= max_depth:
                continue
            for target in adjacency.get(key, []):
                if target.casefold() not in reached:
                    parents[target.casefold()] = key
                    queue.append((target, depth + 1))

        labels = {str(row[0]).casefold(): str(row[0]) for row in procedures}
        procedures_out = []
        for key, depth in sorted(reached.items(), key=lambda item: (item[1], item[0])):
            path = [labels.get(key, key)]
            parent = parents.get(key)
            while parent:
                path.append(labels.get(parent, parent))
                parent = parents.get(parent)
            path.reverse()
            procedures_out.append({
                "node": labels.get(key, key),
                "depth": depth,
                "call_path": path,
            })

        mapped.append({
            "entry_id": entry.get("entry_id"),
            "object": owner,
            "entry_kind": entry.get("entry_kind"),
            "line_start": entry.get("line_start"),
            "line_end": entry.get("line_end"),
            "direct_targets": direct,
            "reachable_procedures": procedures_out,
            "unresolved_calls": unresolved,
            "truncated": truncated,
            "runtime_executed": False,
            "call_order_proven": False,
            "semantics": "Static source identifier and explicit RUN-reference mapping; not proof of runtime invocation.",
        })

    return {
        "entry_count": len(mapped),
        "entries": mapped,
        "semantics": {
            "runtime_executed": False,
            "limitations": [
                "Only call-shaped, unique same-object procedure identifiers and explicit RUN object references are resolved.",
                "Typed variable method calls, ambiguous identifiers, function-return shorthand, event dispatch, dynamic RUN and indirect calls remain unresolved.",
                "Object RUN targets are reported without expanding object-wide procedures as if they belonged to this individual entry.",
            ],
        },
    }
