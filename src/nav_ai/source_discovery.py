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
from .control_flow import analyze_control_flow
from .assignment_flow import analyze_assignment_flow
from .semantic_conditions import parse_record_variables, parse_table_metadata, enrich_control_flow
from .record_filters import analyze_record_filter_paths, annotate_record_lookup_conditions
from .trace_interprocedural import analyze_trace_call_edges


def _iter_source_texts(root: str, source_labels: set[str] | None = None):
    path = Path(root)
    normalized_labels = {
        label.casefold() for label in (source_labels or set())
    }
    normalized_basenames = {Path(label).name.casefold() for label in normalized_labels}

    def wanted(label: str) -> bool:
        if source_labels is None:
            return True
        return label.casefold() in normalized_labels or Path(label).name.casefold() in normalized_basenames

    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file() and item.suffix.lower() == ".txt":
                if wanted(item.name):
                    yield str(item), item.name, item.read_text(encoding="utf-8-sig", errors="replace")
            elif item.is_file() and item.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(item) as archive:
                        for name in archive.namelist():
                            if name.lower().endswith(".txt") and wanted(name):
                                yield f"{item}!{name}", name, archive.read(name).decode("utf-8-sig", errors="replace")
                except (OSError, zipfile.BadZipFile):
                    continue
    elif path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".txt") and wanted(name):
                    yield f"{path}!{name}", name, archive.read(name).decode("utf-8-sig", errors="replace")
    elif path.is_file():
        # A direct TXT path is always read; it may contain several objects.
        if path.suffix.lower() != ".zip" or wanted(path.name):
            yield str(path), path.name, path.read_text(encoding="utf-8-sig", errors="replace")
    else:
        raise FileNotFoundError(f"Source root not found: {root}")


def build_source_catalog(
    source_roots: list[str],
    wanted_keys: set[tuple[str, int]] | None = None,
    symbols: sqlite3.Connection | None = None,
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """Index exported objects by exact NAV type/id without guessing duplicates.

    When symbol-index source labels are available, scan only those TXT members/files.
    Objects without a source label remain unresolved rather than forcing a full scan.
    """
    catalog: dict[tuple[str, int], list[dict[str, Any]]] = {}
    source_labels: set[str] | None = None
    if wanted_keys:
        labels: set[str] = set()
        for object_type, object_id in wanted_keys:
            labels.update(_symbol_source_labels(symbols, object_type, object_id))
        # Use every available label even when some graph objects have no symbol
        # entry. Those objects remain explicitly missing instead of forcing a
        # potentially expensive full export scan.
        if labels:
            source_labels = labels
    seen: set[tuple[str, str]] = set()
    for root in source_roots:
        for display_path, source_label, text in _iter_source_texts(root, source_labels):
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
                    "object_line_offset": line_offset,
                    "raw_block": block,
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
                     max_nodes: int = 5000,
                     analyze_conditions: bool = False) -> dict[str, Any]:
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
        procedure_starts = [row[0] for row in graph.execute(
            "SELECT node FROM procedures WHERE object_node=? ORDER BY node",
            (start_row[0],),
        ).fetchall()]
        start_label = start_row[0]
        object_scope_starts = [start_row[0], f"{start_row[0]} TRIGGERS"]
        has_object_scope_calls = graph.execute(
            "SELECT 1 FROM edges WHERE kind='CALL' AND src IN (?,?) LIMIT 1",
            tuple(object_scope_starts),
        ).fetchone() is not None
        if not procedure_starts and not has_object_scope_calls:
            raise ValueError(f"Object has no indexed procedures or object-scope calls: {start_label}")
        # Object-level code and trigger scope are separate graph sources in
        # depgraph.py; include them as roots so their direct CALL edges are not lost.
        starts = procedure_starts + object_scope_starts
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
    parent_by_node: dict[str, str] = {}
    queue = deque()
    for node in starts:
        if node not in depth_by_node:
            depth_by_node[node] = 0
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
            parent_by_node[target] = node
            queue.append(target)

    wanted_objects: set[tuple[str, int]] = set()
    for node in depth_by_node:
        proc_row = graph.execute(
            "SELECT object_node FROM procedures WHERE node=?", (node,)
        ).fetchone()
        if proc_row:
            object_type, object_id = proc_row[0].rsplit(" ", 1)
            wanted_objects.add((object_type, int(object_id)))
    catalog = build_source_catalog(source_roots, wanted_objects, symbols)
    tables: dict[int, dict[str, Any]] = {}
    table_source_status: list[dict[str, Any]] = []
    if analyze_conditions:
        required_table_ids: set[int] = set()
        for candidates in catalog.values():
            for candidate in candidates:
                try:
                    parsed_source = parse_nav_text(candidate["raw_block"], candidate["source_path"])
                except ValueError:
                    continue
                declarations = "\n".join(
                    variable["raw"] for variable in parsed_source["variables"]
                )
                for procedure in parsed_source["procedures"]:
                    required_table_ids.update(
                        parse_record_variables(declarations + "\n" + procedure["raw"]).values()
                    )
        table_keys = {("Table", table_id) for table_id in required_table_ids}
        table_catalog = build_source_catalog(source_roots, table_keys, symbols) if table_keys else {}
        catalog.update(table_catalog)
        for object_type, object_id in table_catalog:
            if object_type != "table":
                continue
            resolved_table = _resolve_source(catalog, symbols, "Table", object_id)
            if resolved_table.get("status") != "resolved":
                table_source_status.append({
                    "table_id": object_id,
                    "status": resolved_table.get("status"),
                    "candidates": resolved_table.get("candidates", []),
                })
                continue
            try:
                metadata = parse_table_metadata(
                    resolved_table["raw_block"], resolved_table["source_path"]
                )
                for field in metadata["fields"].values():
                    field["line"] += resolved_table["object_line_offset"]
                tables[object_id] = metadata
            except ValueError as exc:
                table_source_status.append({
                    "table_id": object_id, "status": "parse_error", "error": str(exc)
                })
    procedures = []
    condition_analysis_count = 0
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
        source_public = {
            key: value for key, value in source.items() if key != "raw_block"
        }
        path_nodes = [row["node"]]
        parent = parent_by_node.get(row["node"])
        while parent:
            path_nodes.append(parent)
            parent = parent_by_node.get(parent)
        path_nodes.reverse()
        direct_table_usage = [
            dict(usage_row) for usage_row in graph.execute(
                "SELECT table_node,table_name,usage,count,new_vs_original "
                "FROM table_usage WHERE src=? ORDER BY usage,table_node",
                (row["node"],),
            ).fetchall()
        ]
        item = {
            "node": row["node"],
            "object_node": row["object_node"],
            "procedure": row["name"],
            "depth": depth,
            "origin": row["origin"],
            "is_local": bool(row["is_local"]),
            "graph_line": row["line"],
            "call_path": path_nodes,
            "table_usage": direct_table_usage,
            "source": source_public,
        }
        proc_info = None
        if source["status"] == "resolved":
            proc_info = source["procedures"].get(row["name"].casefold())
            if proc_info:
                item["source_line_start"] = proc_info["line_start"]
                item["source_line_end"] = proc_info["line_end"]
            else:
                item["source_procedure_status"] = "not_found_in_resolved_object"

        if analyze_conditions and source["status"] != "resolved":
            item["condition_analysis"] = {
                "status": "source_unavailable",
                "reason": source["status"],
                "runtime_evaluated": False,
            }
        elif analyze_conditions and not proc_info:
            item["condition_analysis"] = {
                "status": "procedure_not_found",
                "reason": "Procedure name from dependency graph was not found in resolved source object",
                "runtime_evaluated": False,
            }
        elif analyze_conditions and proc_info:
            try:
                parsed_object = parse_nav_text(source["raw_block"], source["source_path"])
                proc_matches = [
                    proc for proc in parsed_object["procedures"]
                    if proc["name"].casefold() == row["name"].casefold()
                ]
                if len(proc_matches) != 1:
                    raise ValueError(
                        f"Expected one source procedure {row['name']!r}; found {len(proc_matches)}"
                    )
                selected_proc = proc_matches[0]
                raw_lines = selected_proc["raw"].splitlines()
                begin = next((
                    index for index, line in enumerate(raw_lines)
                    if line.strip().upper() == "BEGIN"
                ), None)
                if begin is None:
                    raise ValueError(f"Procedure {row['name']} has no BEGIN block")
                code = "\n".join(raw_lines[begin:])
                line_offset = (
                    source["object_line_offset"] + selected_proc["line_start"] + begin - 1
                )
                tree = analyze_control_flow(
                    code, object_type, object_id, source["object_name"],
                    selected_proc["name"], source["source_path"],
                    line_offset=line_offset,
                )
                variable_source = "\n".join(
                    variable["raw"] for variable in parsed_object["variables"]
                ) + "\n" + selected_proc["raw"]
                variables = parse_record_variables(variable_source)
                if tables:
                    enrich_control_flow(tree["nodes"], variables, tables)
                missing_table_ids = sorted(set(variables.values()) - set(tables))
                filters = analyze_record_filter_paths(
                    tree["nodes"], variables, tables, source["source_path"]
                )
                annotate_record_lookup_conditions(tree["nodes"], filters["lookups"])
                item["condition_analysis"] = {
                    "status": "analyzed",
                    "nodes": tree["nodes"],
                    "assignment_flow_analysis": analyze_assignment_flow(
                        tree["nodes"], source["source_path"]
                    ),
                    "record_filter_analysis": filters,
                    "semantic_resolution": {
                        "enabled": bool(tables),
                        "record_variables": variables,
                        "table_ids_loaded": sorted(tables),
                        "missing_table_ids_for_procedure": missing_table_ids,
                        "table_source_status": table_source_status,
                        "runtime_evaluated": False,
                    },
                    "runtime_evaluated": False,
                }
                condition_analysis_count += 1
            except (ValueError, KeyError) as exc:
                item["condition_analysis"] = {
                    "status": "unavailable",
                    "reason": str(exc),
                    "runtime_evaluated": False,
                }
        procedures.append(item)

    trace_edges = [
        {
            "src": src,
            "dst": dst,
            "src_depth": depth_by_node[src],
            "dst_depth": depth_by_node[dst],
            "tree_edge": parent_by_node.get(dst) == src,
        }
        for src, targets in adjacency.items() if src in depth_by_node
        for dst in targets if dst in depth_by_node
    ]
    interprocedural_analysis = analyze_trace_call_edges(trace_edges, catalog, symbols)
    reached_objects = sorted({item["object_node"] for item in procedures})
    aggregate_table_usage: list[dict[str, Any]] = []
    if reached_objects:
        placeholders = ",".join("?" for _ in reached_objects)
        aggregate_table_usage = [
            dict(row) for row in graph.execute(
                "SELECT table_node,table_name,usage,SUM(count) AS count,"
                "MAX(new_vs_original) AS new_vs_original "
                f"FROM table_usage WHERE src_object IN ({placeholders}) "
                "GROUP BY table_node,table_name,usage ORDER BY usage,table_node",
                tuple(reached_objects),
            ).fetchall()
        ]
    origin_counts: dict[str, int] = {}
    source_status_counts: dict[str, int] = {}
    condition_node_counts = {"if": 0, "case": 0}
    def count_conditions(value: Any) -> None:
        if isinstance(value, dict):
            kind = value.get("type")
            if kind in condition_node_counts:
                condition_node_counts[kind] += 1
            for child in value.values():
                if isinstance(child, (dict, list)):
                    count_conditions(child)
        elif isinstance(value, list):
            for child in value:
                count_conditions(child)
    for item in procedures:
        origin_counts[item["origin"]] = origin_counts.get(item["origin"], 0) + 1
        status = item["source"]["status"]
        source_status_counts[status] = source_status_counts.get(status, 0) + 1
        analysis = item.get("condition_analysis", {})
        if analysis.get("status") == "analyzed":
            count_conditions(analysis.get("nodes", []))
    return {
        "start": start_label,
        "max_depth": max_depth,
        "max_nodes": max_nodes,
        "procedure_count": len(procedures),
        "edge_count": len(trace_edges),
        "truncated": truncated,
        "conditions_analyzed": bool(analyze_conditions),
        "condition_analysis_count": condition_analysis_count,
        "table_metadata_count": len(tables),
        "procedures": procedures,
        "call_edges": trace_edges,
        "interprocedural_analysis": interprocedural_analysis,
        "table_usage_summary": aggregate_table_usage,
        "process_summary": {
            "procedure_count": len(procedures),
            "call_edge_count": len(trace_edges),
            "origin_counts": origin_counts,
            "source_status_counts": source_status_counts,
            "table_count": len({row["table_node"] for row in aggregate_table_usage}),
            "table_usage_counts": {
                usage: sum(row["count"] for row in aggregate_table_usage if row["usage"] == usage)
                for usage in sorted({row["usage"] for row in aggregate_table_usage})
            },
            "condition_node_counts": condition_node_counts,
            "unresolved_call_target_count": len(unresolved_call_targets),
        },
        "unresolved_call_targets": [
            {"src": src, "dst": dst, "reason": "CALL edge targets an object/non-procedure graph node"}
            for src, dst in sorted(unresolved_call_targets)
        ],
        "semantics": {
            "graph_source": "existing dependency graph CALL edges",
            "source_resolution": "exact object type/id; symbol source_file labels used to disambiguate",
            "condition_analysis": (
                "static IF/ELSE/CASE, assignment and filter analysis for resolved procedures"
                if analyze_conditions else "not requested"
            ),
            "interprocedural_analysis": "direct call-site bindings and explicit callee VAR mutations for discovered CALL edges",
            "runtime_evaluated": False,
            "limitations": [
                "Only CALL edges already present in the dependency graph are traversed.",
                "CALL edges targeting object nodes (for example Var.RUN) are reported as unresolved targets, not expanded into guessed procedures.",
                "Calls absent from the graph, dynamic dispatch, triggers and implicit side effects are not discovered.",
                "Missing or ambiguous source exports are reported rather than inferred.",
                "Depth is measured in procedure-call edges; starting all procedures of an object begins at depth zero.",
            "Each procedure has one shortest first-discovered call_path; alternate paths are retained in call_edges, not collapsed into a single asserted execution path.",
            ],
        },
    }
