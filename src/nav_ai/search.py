#!/usr/bin/env python3
"""Exact / keyword symbol search over NAV TXT exports (roadmap P1.26).

nav-search <company> index [inputs...]             # parse every object into a SQLite symbol index
nav-search <company> find [terms...] [options]     # search symbols in data/search/<company>/search.db
nav-search <company> "Sales Header" --exact        # exact (case-insensitive) name match
nav-search <company> sales post --kind procedure   # keyword: every term in name or object name
nav-search <company> --id 50076                    # object id, field id or variable id
Kinds: object, field, procedure, variable, trigger. Lines are absolute line numbers in the source file.
"""
from __future__ import annotations
import argparse, sqlite3, sys, zipfile
from pathlib import Path
from . import semantic_diff as n
from .parser import parse_nav_text

KINDS = ("object", "field", "procedure", "variable", "trigger")
SCHEMA = """
CREATE TABLE symbols(kind TEXT, name TEXT, num INT, object_type TEXT, object_id INT, object_name TEXT,
    detail TEXT, source_file TEXT, line INT, line_end INT);
CREATE INDEX ix_s_name ON symbols(name COLLATE NOCASE); CREATE INDEX ix_s_num ON symbols(num);
CREATE INDEX ix_s_obj ON symbols(object_type, object_id);
"""

def iter_objects(path):
    """Yield (source_file, first_line_in_file, object_text) for every OBJECT in a TXT, ZIP, or folder."""
    path = Path(path)
    def texts():
        if path.is_dir():
            for txt_path in sorted(path.rglob("*.txt")):
                yield txt_path.name, txt_path.read_text(encoding="utf-8-sig", errors="replace")
            for zip_path in sorted(path.rglob("*.zip")):
                with zipfile.ZipFile(zip_path) as zf:
                    for name in zf.namelist():
                        if name.lower().endswith(".txt"):
                            yield name, zf.read(name).decode("utf-8-sig", errors="replace")
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".txt"):
                        yield name, zf.read(name).decode("utf-8-sig", errors="replace")
        else:
            yield path.name, path.read_bytes().decode("utf-8-sig", errors="replace")
    for name, text in texts():
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        ms = list(n.HEADER.finditer(text))
        line, prev = 1, 0
        for i, m in enumerate(ms):
            line += text.count("\n", prev, m.start()); prev = m.start()   # incremental: large files stay linear
            yield name, line, text[m.start():(ms[i+1].start() if i+1 < len(ms) else len(text))].strip()

def symbols_of(parsed, source_file, first_line):
    """Rows in COLS order; parser lines are relative to the object, so shift them to file lines."""
    o = parsed["object"]; base = first_line - 1
    who = (o["type"], o["id"], o["name"])
    def row(kind, name, num, detail, start, end): return (kind, name, num, *who, detail, source_file, base + start, base + end)
    rows = [row("object", o["name"], o["id"], o["version_list"] or "", 1, parsed["source"]["line_count"])]
    rows += [row("field", f["name"], f["id"], f["data_type"], f["line_start"], f["line_end"]) for f in parsed["fields"]]
    rows += [row("procedure", p["name"], None, p["signature"], p["line_start"], p["line_end"]) for p in parsed["procedures"]]
    rows += [row("variable", v["name"], v["nav_id"], v["data_type"], v["line"], v["line"]) for v in parsed["variables"]]
    rows += [row("trigger", t["name"], None, t["section"], t["line"], t["line"]) for t in parsed["triggers"]]
    return rows

def build_index(inputs, db_path):
    db_path = Path(db_path); db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists(): db_path.unlink()
    db = sqlite3.connect(db_path); db.executescript(SCHEMA)
    seen, skipped = set(), []
    for src in inputs:                                  # later inputs replace earlier ones for the same object
        for name, first_line, block in iter_objects(src):
            try:
                parsed = parse_nav_text(block, name)
            except ValueError as e:
                skipped.append(str(e)); continue
            o = parsed["object"]; key = (o["type"], o["id"])
            if key in seen: db.execute("DELETE FROM symbols WHERE object_type=? AND object_id=?", key)
            seen.add(key)
            db.executemany("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?)", symbols_of(parsed, name, first_line))
    db.commit()
    counts = dict(db.execute("SELECT kind, COUNT(*) FROM symbols GROUP BY kind"))
    db.close()
    return len(seen), counts, skipped

COLS = ("kind", "name", "num", "object_type", "object_id", "object_name", "detail", "source_file", "line", "line_end")

def search(db, terms=(), exact=False, num=None, kinds=(), object_type=None, object_id=None, limit=50):
    """Return (rows, total). exact: whole name equals ' '.join(terms); keyword: every term in name or object name."""
    where, args = [], []
    if exact and terms:
        where.append("name = ? COLLATE NOCASE"); args.append(" ".join(terms))
    else:
        for t in terms:
            where.append("instr(lower(name || ' ' || object_name), lower(?)) > 0"); args.append(t)
    if num is not None: where.append("num = ?"); args.append(num)
    if kinds: where.append(f"kind IN ({','.join('?' * len(kinds))})"); args += list(kinds)
    if object_type: where.append("object_type = ? COLLATE NOCASE"); args.append(object_type)
    if object_id is not None: where.append("object_id = ?"); args.append(object_id)
    if not where: raise ValueError("give search terms, --id, --kind, --type or --object-id")
    cond = " AND ".join(where)
    q0 = " ".join(terms).lower()
    total = db.execute(f"SELECT COUNT(*) FROM symbols WHERE {cond}", args).fetchone()[0]
    order = ("CASE WHEN lower(name) = ? THEN 0 WHEN instr(lower(name), ?) = 1 THEN 1 ELSE 2 END, "
             "CASE kind WHEN 'object' THEN 0 WHEN 'procedure' THEN 1 WHEN 'field' THEN 2 WHEN 'variable' THEN 3 ELSE 4 END, "
             "name COLLATE NOCASE, object_type, object_id, line")
    rows = db.execute(f"SELECT {','.join(COLS)} FROM symbols WHERE {cond} ORDER BY {order} LIMIT ?", args + [q0, q0, limit]).fetchall()
    return [dict(zip(COLS, r)) for r in rows], total

def format_rows(rows):
    if not rows: return "(no results)"
    lines = []
    for r in rows:
        num = f" #{r['num']}" if r["num"] is not None else ""
        lines.append(f"{r['kind']:<9} {r['name']}{num}  [{r['object_type']} {r['object_id']} {r['object_name']}]  "
                     f"{r['detail']}  {r['source_file']}:{r['line']}")
    return "\n".join(lines)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="nav-search", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company", help="Company name (uses data/input/{company} for index, data/search/{company}/search.db for find)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ix = sub.add_parser("index", help="build the symbol index")
    ix.add_argument("inputs", nargs="*", help="Input file(s) or folder(s) (overrides company)")
    fd = sub.add_parser("find", help="search the index")
    fd.add_argument("terms", nargs="*")
    fd.add_argument("--exact", action="store_true")
    fd.add_argument("--id", type=int, dest="num", help="object id, field id or variable id")
    fd.add_argument("--kind", action="append", default=[], choices=KINDS)
    fd.add_argument("--type", dest="object_type", help="Table, Page, Codeunit, Report ...")
    fd.add_argument("--object-id", type=int); fd.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)

    db_path = Path(f"data/search/{a.company}/search.db")

    # Resolve input paths for index
    if a.cmd == "index":
        input_paths = a.inputs if a.inputs else [f"data/input/{a.company}"]
        objects, counts, skipped = build_index(input_paths, db_path)
        print(f"indexed {objects} object(s): {counts}  skipped {len(skipped)}  -> {db_path}")
        for s in skipped[:5]: print("  skipped:", s)
        return 0

    if not db_path.exists():
        print(f"index not found: {db_path} (run: nav-search <company> index or --db <path>)", file=sys.stderr); return 2
    db = sqlite3.connect(db_path)
    try:
        rows, total = search(db, a.terms, a.exact, a.num, a.kind, a.object_type, a.object_id, a.limit)
    except ValueError as e:
        print(e, file=sys.stderr); return 2
    print(format_rows(rows))
    print(f"{total} result(s)" + (f", showing {len(rows)} (use --limit)" if total > len(rows) else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())
