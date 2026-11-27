"""Query layer over the existing NAV symbol index and dependency graph.

This module deliberately does not parse NAV source or rebuild the graph. It
joins the two existing SQLite artifacts and exposes evidence-oriented queries.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .control_flow import analyze_control_flow
from .parser import parse_nav_text, split_objects
from .semantic_conditions import enrich_control_flow, load_table_sources, parse_record_variables
from .record_filters import analyze_record_filter_paths, annotate_record_lookup_conditions
from .snapshot_evaluator import evaluate_condition_snapshot


def _attach_snapshot_evaluations(nodes: Any, snapshot: dict[str, Any],
                                 variables: dict[str, int],
                                 tables: dict[int, dict[str, Any]]) -> None:
    if isinstance(nodes, list):
        for node in nodes:
            _attach_snapshot_evaluations(node, snapshot, variables, tables)
    elif isinstance(nodes, dict):
        if nodes.get("type") == "if" and isinstance(nodes.get("normalized_condition"), dict):
            nodes["snapshot_evaluation"] = evaluate_condition_snapshot(
                nodes["normalized_condition"], snapshot, variables, tables
            )
        for value in nodes.values():
            if isinstance(value, (dict, list)):
                _attach_snapshot_evaluations(value, snapshot, variables, tables)



def _connect(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Required index not found: {p}")
    db = sqlite3.connect(p)
    db.row_factory = sqlite3.Row
    return db


def _one(db: sqlite3.Connection, sql: str, args: tuple = ()) -> dict[str, Any] | None:
    row = db.execute(sql, args).fetchone()
    return dict(row) if row else None


def _many(db: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute(sql, args).fetchall()]


def _resolve_node(graph: sqlite3.Connection, node: str) -> str:
    """Resolve exact canonical node or a unique object name / id."""
    row = _one(graph, "SELECT node FROM objects WHERE node=? COLLATE NOCASE", (node,))
    if row:
        return row["node"]
    rows = _many(
        graph,
        "SELECT node FROM objects WHERE name=? COLLATE NOCASE OR node LIKE ? ORDER BY node LIMIT 3",
        (node, f"% {node}"),
    )
    if len(rows) == 1:
        return rows[0]["node"]
    if len(rows) > 1:
        raise ValueError("Ambiguous object reference. Use the canonical 'Type ID' form: " +
                         ", ".join(r["node"] for r in rows))
    # A procedure node is canonical: "Codeunit 80.PostItemJnlLine".
    row = _one(graph, "SELECT node FROM procedures WHERE node=? COLLATE NOCASE", (node,))
    if row:
        return row["node"]
    raise ValueError(f"Object/procedure not found in dependency graph: {node}")


def object_detail(graph: sqlite3.Connection, node: str) -> dict[str, Any]:
    node = _resolve_node(graph, node)
    obj = _one(graph, "SELECT * FROM objects WHERE node=?", (node,))
    if not obj:
        raise ValueError(f"Not an object node: {node}")
    obj["top_procedures"] = _many(
        graph, "SELECT node,name,line,is_local,origin FROM procedures WHERE object_node=? ORDER BY name",
        (node,),
    )
    obj["incoming_dependencies"] = _many(
        graph, "SELECT src,kind,count,new_vs_original FROM edges WHERE dst=? ORDER BY kind,src LIMIT 100",
        (node,),
    )
    obj["outgoing_dependencies"] = _many(
        graph, "SELECT dst,kind,count,new_vs_original FROM edges WHERE src=? ORDER BY kind,dst LIMIT 100",
        (node,),
    )
    obj["table_usage"] = _many(
        graph, "SELECT table_node,table_name,usage,count,new_vs_original FROM table_usage "
              "WHERE src_object=? ORDER BY table_node,usage", (node,),
    )
    return obj


def procedure_detail(graph: sqlite3.Connection, node: str) -> dict[str, Any]:
    row = _one(graph, "SELECT * FROM procedures WHERE node=? COLLATE NOCASE", (node,))
    if not row:
        raise ValueError(f"Procedure not found in dependency graph: {node}")
    row["callers"] = _many(
        graph, "SELECT src,kind,count,new_vs_original FROM edges WHERE dst=? AND kind='CALL' ORDER BY src",
        (row["node"],),
    )
    row["callees"] = _many(
        graph, "SELECT dst,kind,count,new_vs_original FROM edges WHERE src=? AND kind='CALL' ORDER BY dst",
        (row["node"],),
    )
    return row


def graph_neighbors(graph: sqlite3.Connection, node: str, direction: str,
                    kinds: tuple[str, ...] = ("CALL",)) -> list[dict[str, Any]]:
    node = _resolve_node(graph, node)
    if not kinds:
        raise ValueError("At least one dependency kind is required")
    placeholders = ",".join("?" for _ in kinds)
    if direction == "callers":
        sql = (f"SELECT src AS node,kind,count,new_vs_original FROM edges "
               f"WHERE dst=? AND kind IN ({placeholders}) ORDER BY kind,src")
    else:
        sql = (f"SELECT dst AS node,kind,count,new_vs_original FROM edges "
               f"WHERE src=? AND kind IN ({placeholders}) ORDER BY kind,dst")
    return _many(graph, sql, (node, *kinds))


def impact(graph: sqlite3.Connection, node: str, kinds: tuple[str, ...] = ("CALL",)) -> list[str]:
    """Return transitive callers. CALL is the safe default; loose refs are opt-in."""
    start = _resolve_node(graph, node)
    if not kinds:
        raise ValueError("At least one dependency kind is required")
    placeholders = ",".join("?" for _ in kinds)
    rows = _many(graph, f"SELECT src,dst FROM edges WHERE kind IN ({placeholders})", kinds)
    reverse: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        reverse[row["dst"]].append(row["src"])
    seen, queue = {start}, deque([start])
    while queue:
        current = queue.popleft()
        for caller in reverse[current]:
            if caller not in seen:
                seen.add(caller)
                queue.append(caller)
    seen.discard(start)
    return sorted(seen)


def table_usage(graph: sqlite3.Connection, table: str, usage: str | None = None) -> list[dict[str, Any]]:
    table_node = _resolve_node(graph, table)
    if not table_node.startswith("Table "):
        raise ValueError(f"Expected a Table node, got: {table_node}")
    sql = ("SELECT src,src_origin,table_node,table_name,usage,count,new_vs_original "
           "FROM table_usage WHERE table_node=?")
    args: tuple[Any, ...] = (table_node,)
    if usage:
        sql += " AND usage=?"
        args += (usage.upper(),)
    return _many(graph, sql + " ORDER BY usage,src", args)


def symbol_search(symbols: sqlite3.Connection, terms: list[str], limit: int = 30) -> list[dict[str, Any]]:
    if not terms:
        raise ValueError("Provide one or more search terms")
    where, args = [], []
    for term in terms:
        where.append("instr(lower(name || ' ' || object_name || ' ' || detail),lower(?))>0")
        args.append(term)
    return _many(
        symbols,
        "SELECT kind,name,num,object_type,object_id,object_name,detail,source_file,line,line_end "
        "FROM symbols WHERE " + " AND ".join(where) +
        " ORDER BY CASE kind WHEN 'object' THEN 0 WHEN 'procedure' THEN 1 ELSE 2 END,"
        "object_type,object_id,line LIMIT ?",
        (*args, limit),
    )


def _print(data: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(data, list):
        if not data:
            print("(no results)")
        for item in data:
            if isinstance(item, dict):
                print(" | ".join(f"{k}={v}" for k, v in item.items()))
            else:
                print(item)
    elif isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}:")
            if isinstance(value, list):
                for item in value:
                    print("  - " + (", ".join(f"{k}={v}" for k, v in item.items())
                                     if isinstance(item, dict) else str(item)))
            else:
                print(f"  {value}")
    else:
        print(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nav-intel",
        description="Evidence-oriented queries over existing NAV symbol and dependency indexes.",
    )
    parser.add_argument("--company", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    sub = parser.add_subparsers(dest="command", required=True)

    find = sub.add_parser("search", help="search indexed NAV symbols")
    find.add_argument("terms", nargs="+")
    find.add_argument("--limit", type=int, default=30)

    show = sub.add_parser("object", help="show object metadata and graph neighborhood")
    show.add_argument("node", help='canonical node, e.g. "Codeunit 80"')

    proc = sub.add_parser("procedure", help="show procedure callers and callees")
    proc.add_argument("node", help='canonical node, e.g. "Codeunit 80.PostItemJnlLine"')

    for name in ("callers", "callees"):
        cmd = sub.add_parser(name, help=f"list direct {name}")
        cmd.add_argument("node")
        cmd.add_argument("--kinds", default="CALL", help="comma-separated edge kinds")

    imp = sub.add_parser("impact", help="find transitive callers (impact surface)")
    imp.add_argument("node")
    imp.add_argument("--kinds", default="CALL")

    tab = sub.add_parser("table", help="show all indexed READ/WRITE usage for a table")
    tab.add_argument("node", help='canonical table node, e.g. "Table 36"')
    tab.add_argument("--usage", choices=("READ", "WRITE", "VAR", "SOURCE", "RELATION", "REF"))

    cond = sub.add_parser("conditions", help="extract IF/ELSE and CASE paths from a C/AL source export")
    cond.add_argument("--source-file", required=True, help="NAV TXT export containing the target object")
    cond.add_argument("--object", dest="object_node", help='optional object identity, e.g. "Codeunit 80"')
    cond.add_argument("--procedure", help="procedure name; omit to analyze the full object CODE section")
    cond.add_argument("--table-source", action="append", default=[], help="Table TXT metadata export; repeat for multiple tables")
    cond.add_argument("--snapshot-json", help="explicit Record-variable snapshot JSON; requires --table-source")

    args = parser.parse_args(argv)
    base = Path("data")
    graph_path = base / "depgraph" / args.company / "depgraph.db"
    symbol_path = base / "search" / args.company / "search.db"
    try:
        if args.command == "conditions":
            source = Path(args.source_file).read_text(encoding="utf-8-sig", errors="replace")
            objects = split_objects(source)
            if not objects:
                raise ValueError(f"No NAV OBJECT found in source file: {args.source_file}")
            selected = []
            for object_match, block in objects:
                parsed_candidate = parse_nav_text(block, args.source_file)
                identity = parsed_candidate["object"]
                if args.object_node:
                    wanted = args.object_node.casefold()
                    if (f"{identity['type']} {identity['id']}".casefold() != wanted
                            and identity["name"].casefold() != wanted):
                        continue
                selected.append((object_match, block, parsed_candidate))
            if len(selected) != 1:
                raise ValueError('Source file must resolve to exactly one object; use --object "Type ID"')
            object_match, block, parsed_block = selected[0]
            parsed = parsed_block
            file_line_offset = source.count("\n", 0, object_match.start())
            if args.procedure:
                matches = [p for p in parsed_block["procedures"] if p["name"].casefold() == args.procedure.casefold()]
                if len(matches) != 1:
                    raise ValueError(f"Expected one procedure named {args.procedure!r}; found {len(matches)}")
                raw_lines = matches[0]["raw"].splitlines()
                begin = next((i for i, line in enumerate(raw_lines) if line.strip().upper() == "BEGIN"), None)
                if begin is None:
                    raise ValueError(f"Procedure {args.procedure!r} has no BEGIN block")
                code = "\n".join(raw_lines[begin:])
                line_offset = file_line_offset + matches[0]["line_start"] + begin - 1
                result = analyze_control_flow(code, parsed["object"]["type"], parsed["object"]["id"],
                                              parsed["object"]["name"], matches[0]["name"], args.source_file,
                                              line_offset=line_offset)
            else:
                section = parsed_block["sections"].get("CODE")
                if not section:
                    raise ValueError("Selected object has no CODE section")
                code = "\n".join(block.splitlines()[section["line_start"] - 1:section["line_end"]])
                line_offset = file_line_offset + section["line_start"] - 1
                result = analyze_control_flow(code, parsed["object"]["type"], parsed["object"]["id"],
                                              parsed["object"]["name"], None, args.source_file,
                                              line_offset=line_offset)
            if args.snapshot_json and not args.table_source:
                raise ValueError("--snapshot-json requires at least one --table-source")
            if args.table_source:
                variable_source = "\n".join(v["raw"] for v in parsed_block["variables"])
                if args.procedure:
                    variable_source += "\n" + matches[0]["raw"]
                variables = parse_record_variables(variable_source)
                tables = load_table_sources(args.table_source)
                enrich_control_flow(result["nodes"], variables, tables)
                filter_analysis = analyze_record_filter_paths(
                    result["nodes"], variables, tables, args.source_file
                )
                annotate_record_lookup_conditions(result["nodes"], filter_analysis["lookups"])
                result["record_filter_analysis"] = filter_analysis
                result["semantic_resolution"] = {
                    "enabled": True,
                    "record_variables": variables,
                    "table_ids_loaded": sorted(tables),
                    "runtime_evaluated": False,
                }
                if args.snapshot_json:
                    snapshot = json.loads(Path(args.snapshot_json).read_text(encoding="utf-8"))
                    if not isinstance(snapshot, dict) or not all(isinstance(v, dict) for v in snapshot.values()):
                        raise ValueError("Snapshot JSON must map Record variable names to field/value objects")
                    _attach_snapshot_evaluations(result["nodes"], snapshot, variables, tables)
                    result["snapshot_source"] = str(args.snapshot_json)
                    result["snapshot_provenance"] = "caller_supplied_snapshot"
                    result["runtime_evaluated"] = False
            else:
                result["semantic_resolution"] = {
                    "enabled": False,
                    "reason": "provide --table-source to resolve Table/Field/Option metadata",
                    "runtime_evaluated": False,
                }
        elif args.command == "search":
            with _connect(symbol_path) as symbols:
                result = symbol_search(symbols, args.terms, args.limit)
        else:
            with _connect(graph_path) as graph:
                if args.command == "object":
                    result = object_detail(graph, args.node)
                elif args.command == "procedure":
                    result = procedure_detail(graph, args.node)
                elif args.command in ("callers", "callees"):
                    result = graph_neighbors(graph, args.node, args.command, tuple(args.kinds.split(",")))
                elif args.command == "impact":
                    result = impact(graph, args.node, tuple(args.kinds.split(",")))
                else:
                    result = table_usage(graph, args.node, args.usage)
        _print(result, args.as_json)
        return 0
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"nav-intel: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
