"""Automatic source discovery for dependency-graph call traces.

The graph determines reachable procedure nodes. Source roots are only used to
resolve those nodes to exported NAV TXT objects; unresolved or duplicate
matches remain explicit in the result.
"""
from __future__ import annotations

import sqlite3
import zipfile
from collections import deque
from pathlib import Path
from typing import Any

from .parser import parse_nav_text, split_objects


def _iter_source_texts(root: str):
    path = Path(root)
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file() and item.suffix.lower() == ".txt":
                yield str(item), item.name, item.read_text(encoding="utf-8-sig", errors="replace")
            elif item.is_file() and item.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(item) as archive:
                        for name in archive.namelist():
                            if name.lower().endswith(".txt"):
                                yield f"{item}!{name}", name, archive.read(name).decode("utf-8-sig", errors="replace")
                except (OSError, zipfile.BadZipFile):
                    continue
    elif path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".txt"):
                    yield f"{path}!{name}", name, archive.read(name).decode("utf-8-sig", errors="replace")
    elif path.is_file():
        yield str(path), path.name, path.read_text(encoding="utf-8-sig", errors="replace")
    else:
        raise FileNotFoundError(f"Source root not found: {root}")


def build_source_catalog(source_roots: list[str]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """Index exported objects by exact NAV type/id without guessing duplicates."""
    catalog: dict[tuple[str, int], list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for root in source_roots:
        for display_path, source_label, text in _iter_source_texts(root):
            identity_key = (display_path.casefold(), source_label.casefold())
            if identity_key in seen:
                continue
            seen.add(identity_key)
            normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
            for object_match, block in split_objects(normalized_text):
                line_offset = normalized_text.count("\n", 0, object_match.start())
                try:
                    parsed = parse_nav_text(block, display_path)
                except ValueError:
                    continue
                obj = parsed["object"]
                key = (obj["type"].casefold(), int(obj["id"]))
                catalog.setdefault(key, []).append({
                    "source_path": display_path,
                    "source_label": source_label,
                    "object_name": obj["name"],
                    "procedures": {
                        p["name"].casefold(): {
                            "name": p["name"],
                            "line_start": line_offset + p["line_start"],
                            "line_end": line_offset + p["line_end"],
                        }
                        for p in parsed["procedures"]
                    },
                })
    return catalog


def _symbol_source_labels(symbols: sqlite3.Connection | None,
                          object_type: str, object_id: int) -> list[str]:
    if symbols is None:
        return []
    try:
        rows = symbols.execute(
            "SELECT DISTINCT source_file FROM symbols "
            "WHERE object_type=? COLLATE NOCASE AND object_id=?",
            (object_type, object_id),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(row[0]) for row in rows if row[0]]


def _resolve_source(catalog: dict[tuple[str, int], list[dict[str, Any]]],
                    symbols: sqlite3.Connection | None,
                    object_type: str, object_id: int) -> dict[str, Any]:
    candidates = catalog.get((object_type.casefold(), object_id), [])
    labels = {label.casefold() for label in _symbol_source_labels(symbols, object_type, object_id)}
    matched = [item for item in candidates if item["source_label"].casefold() in labels]
    if len(matched) == 1:
        return {"status": "resolved", **matched[0]}
    if not matched and len(candidates) == 1:
        return {"status": "resolved", **candidates[0]}
    if not candidates:
        return {"status": "missing", "candidate_count": 0}
    remaining = matched if matched else candidates
    return {
        "status": "ambiguous",
        "candidate_count": len(remaining),
        "candidates": [item["source_path"] for item in remaining],
    }


def trace_call_graph(graph: sqlite3.Connection, start: str,
                     source_roots: list[str],
                     symbols: sqlite3.Connection | None = None,
                     max_depth: int = 5,
                     max_nodes: int = 5000) -> dict[str, Any]:
    """Trace reachable CALL procedure nodes and resolve each to a source export."""
    if max_depth < 0:
        raise ValueError("max_depth must be zero or greater")
    if max_nodes < 1:
        raise ValueError("max_nodes must be at least 1")

    start_row = graph.execute(
        "SELECT node,type,id,name FROM objects WHERE node=? COLLATE NOCASE",
        (start,),
    ).fetchone()
    if start_row:
        starts = [row[0] for row in graph.execute(
            "SELECT node FROM procedures WHERE object_node=? ORDER BY node",
            (start_row[0],),
        ).fetchall()]
        start_label = start_row[0]
        if not starts:
            raise ValueError(f"Object has no indexed procedures: {start_label}")
    else:
        proc = graph.execute(
            "SELECT node,object_node FROM procedures WHERE node=? COLLATE NOCASE",
            (start,),
        ).fetchone()
        if not proc:
            raise ValueError(f"Start object/procedure not found in graph: {start}")
        starts = [proc[0]]
        start_label = proc[0]

    adjacency: dict[str, list[str]] = {}
    for src, dst in graph.execute("SELECT src,dst FROM edges WHERE kind='CALL' ORDER BY src,dst"):
        adjacency.setdefault(src, []).append(dst)
    procedure_nodes = {
        row[0] for row in graph.execute("SELECT node FROM procedures").fetchall()
    }

    depth_by_node: dict[str, int] = {}
    queue = deque()
    for node in starts:
        depth_by_node.setdefault(node, 0)
        queue.append(node)
    truncated = False
    unresolved_call_targets: set[tuple[str, str]] = set()
    while queue:
        node = queue.popleft()
        depth = depth_by_node[node]
        if depth >= max_depth:
            continue
        for target in adjacency.get(node, []):
            if target not in procedure_nodes:
                unresolved_call_targets.add((node, target))
                continue
            if target in depth_by_node:
                continue
            if len(depth_by_node) >= max_nodes:
                truncated = True
                queue.clear()
                break
            depth_by_node[target] = depth + 1
            queue.append(target)

    catalog = build_source_catalog(source_roots)
    procedures = []
    object_cache: dict[str, dict[str, Any]] = {}
    for node, depth in sorted(depth_by_node.items(), key=lambda item: (item[1], item[0].casefold())):
        row = graph.execute(
            "SELECT node,object_node,name,line,is_local,origin FROM procedures WHERE node=?",
            (node,),
        ).fetchone()
        if not row:
            continue
        object_type, object_id = row["object_node"].rsplit(" ", 1)
        object_id_int = int(object_id)
        key = row["object_node"]
        if key not in object_cache:
            source = _resolve_source(catalog, symbols, object_type, object_id_int)
            object_cache[key] = {
                "object_node": key,
                "source": source,
            }
        source = object_cache[key]["source"]
        item = {
            "node": row["node"],
            "object_node": row["object_node"],
            "procedure": row["name"],
            "depth": depth,
            "origin": row["origin"],
            "is_local": bool(row["is_local"]),
            "graph_line": row["line"],
            "source": source,
        }
        if source["status"] == "resolved":
            proc_info = source["procedures"].get(row["name"].casefold())
            if proc_info:
                item["source_line_start"] = proc_info["line_start"]
                item["source_line_end"] = proc_info["line_end"]
            else:
                item["source_procedure_status"] = "not_found_in_resolved_object"
        procedures.append(item)

    trace_edges = [
        {"src": src, "dst": dst, "depth": depth_by_node[dst]}
        for src, targets in adjacency.items() if src in depth_by_node
        for dst in targets if dst in depth_by_node and depth_by_node[dst] == depth_by_node[src] + 1
    ]
    return {
        "start": start_label,
        "max_depth": max_depth,
        "max_nodes": max_nodes,
        "procedure_count": len(procedures),
        "edge_count": len(trace_edges),
        "truncated": truncated,
        "procedures": procedures,
        "call_edges": trace_edges,
        "unresolved_call_targets": [
            {"src": src, "dst": dst, "reason": "CALL edge targets an object/non-procedure graph node"}
            for src, dst in sorted(unresolved_call_targets)
        ],
        "semantics": {
            "graph_source": "existing dependency graph CALL edges",
            "source_resolution": "exact object type/id; symbol source_file labels used to disambiguate",
            "runtime_evaluated": False,
            "limitations": [
                "Only CALL edges already present in the dependency graph are traversed.",
                "CALL edges targeting object nodes (for example Var.RUN) are reported as unresolved targets, not expanded into guessed procedures.",
                "Calls absent from the graph, dynamic dispatch, triggers and implicit side effects are not discovered.",
                "Missing or ambiguous source exports are reported rather than inferred.",
                "Depth is measured in procedure-call edges; starting all procedures of an object begins at depth zero.",
            ],
        },
    }
