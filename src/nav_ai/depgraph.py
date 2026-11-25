#!/usr/bin/env python3
"""Dependency graph engine for NAV C/AL exports.

Inputs : original (standard baseline) TXT, company ZIP, Semantic Source Diff report (.xlsx).
Outputs: SQLite dependency database + Excel dependency report.

Nodes are "Codeunit 80" (object) and "Codeunit 80.PostItemJnlLine" (procedure).
Edge kinds: VAR (typed variable), REF (CODEUNIT::"Name"), TABLE_REF (DATABASE::"Name"), SOURCE (SourceTable/TableNo/RunObject...),
RELATION (TableRelation), CALL (existing procedure, or Var.RUN on a codeunit).

Classification criteria (no dependency on Modified=Yes or object ID):
- Object in baseline and unchanged        -> STANDARD_UNCHANGED
- Object in baseline and detected changed -> MODIFIED_STANDARD
- Object not in baseline (company only)   -> CUSTOM
- Procedure new on standard object        -> ADDED
- Procedure changed on standard object    -> CHANGED
"""
from __future__ import annotations
import argparse, re, sqlite3
from collections import Counter, defaultdict, deque
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from . import semantic_diff as n

TYPES = "Record|Codeunit|Page|Report|XMLport|Query"
VAR_RE = re.compile(r'("[^"]+"|\w+)@\d+\s*:\s*(' + TYPES + r')\s+(\d+)', re.I)
REF_RE = re.compile(r'\b(CODEUNIT|PAGE|REPORT|XMLPORT|QUERY|DATABASE)::("[^"]+"|\w+)', re.I)
SRC_RE = re.compile(r'\b(?:SourceTable|DataItemTable)\s*=\s*Table(\d+)|\bTableNo\s*=\s*(\d+)'
                    r'|\bRunObject\s*=\s*(Page|Report|Codeunit|XMLport|Query)\s*(\d+)', re.I)
OWN_TABLE_RE = re.compile(r'\b(?:SourceTable\s*=\s*Table|TableNo\s*=\s*)(\d+)', re.I)
REL_RE = re.compile(r'TableRelation\s*=([^;]*);')
IDENT_RE = re.compile(r'"([^"]+)"|([A-Za-z_]\w*)')
CALL_RE = re.compile(r'(?<![\w."])("[^"]+"|\w+)\.(\w+)')
KIND = {"record": "Table", "codeunit": "Codeunit", "page": "Page", "report": "Report",
        "xmlport": "XMLport", "query": "Query", "database": "Table"}
WRITES = {"INSERT", "MODIFY", "DELETE", "MODIFYALL", "DELETEALL", "RENAME"}
READS = {"GET", "FIND", "FINDFIRST", "FINDLAST", "FINDSET", "NEXT", "SETRANGE", "SETFILTER",
         "CALCFIELDS", "CALCSUMS", "COUNT", "ISEMPTY", "SETCURRENTKEY", "SETRECFILTER"}

def obj_of(node):
    return node.split(".", 1)[0]

def uncomment(s, braces=False):  # shortcut: naive; a "//" inside a string literal is lost
    s = re.sub(r'//[^\n]*', ' ', s)
    # {..} is a comment only inside code; in object sections it delimits properties and entries
    return re.sub(r'\{[^{}]*\}', ' ', s) if braces else s

def split_procs(block):
    code = n.code_section(block)
    ms = list(n.PROC.finditer(code))
    return {m.group(2).strip('"'): {"raw": code[m.start():(ms[i+1].start() if i+1 < len(ms) else len(code))],
                                    "line": code.count("\n", 0, m.start()) + 1, "local": bool(m.group(1))}
            for i, m in enumerate(ms)}

class Index:
    """Name -> id and procedure-name lookup over every known object (company wins over original)."""
    def __init__(self, objects):
        self.names, self.pn, self.nodes, self.obj_name = {}, {}, set(), {}
        for key, block in objects.items():
            h = n.HEADER.match(block)
            name = h.group(3).strip() if h else ""
            self.names[(key[0].lower(), name.lower())] = key[1]
            self.obj_name[f"{key[0]} {key[1]}"] = name
            self.nodes.add(f"{key[0]} {key[1]}")
            self.pn[key] = {p.lower(): (p, v["line"], v["local"]) for p, v in split_procs(block).items()}
            for p in self.pn[key].values(): self.nodes.add(f"{key[0]} {key[1]}.{p[0]}")

def scan(key, block, idx):
    t, i = key; me = f"{t} {i}"
    edges, tops = Counter(), Counter()
    def add(src, dst, kind):
        if dst and dst != src and dst in idx.nodes: edges[(src, dst, kind)] += 1
    def use(src, table, op):
        if table in idx.nodes: tops[(src, table, op)] += 1
    def resolve(kind, name):
        oid = idx.names.get((KIND[kind.lower()].lower(), name.strip('"').lower()))
        return f"{KIND[kind.lower()]} {oid}" if oid else None

    procs = split_procs(block)
    code_raw = n.section(block, "CODE")
    full = uncomment(block)
    head = uncomment(block.replace(code_raw, "", 1)) if code_raw else full
    varmap = defaultdict(set)
    for m in VAR_RE.finditer(full):
        tt, tid = KIND[m.group(2).lower()], int(m.group(3))
        varmap[m.group(1).strip('"').lower()].add((tt, tid))
        add(me, f"{tt} {tid}", "VAR")
        if tt == "Table": use(me, f"Table {tid}", "VAR")
    own = i if t == "Table" else None
    if t in ("Page", "Codeunit") and (m := OWN_TABLE_RE.search(head)): own = int(m.group(1))
    if own:
        for v in ("rec", "xrec"): varmap[v].add(("Table", own))
    for m in SRC_RE.finditer(head):
        tid = m.group(1) or m.group(2)
        dst = f"Table {tid}" if tid else f"{m.group(3).title().replace('Xmlport', 'XMLport')} {m.group(4)}"
        add(me, dst, "SOURCE")
        if tid: use(me, dst, "SOURCE")
    for m in REL_RE.finditer(head):
        for q, u in IDENT_RE.findall(m.group(1)):
            dst = resolve("record", q or u)
            add(me, dst, "RELATION")
            if dst: use(me, dst, "RELATION")

    own_lc = {p.lower(): p for p in procs}
    # shortcut: matches the name anywhere in code (also inside strings); C/AL allows calls without "()"
    self_re = re.compile(r'(?<![\w."])(' + "|".join(map(re.escape, sorted(own_lc.values(), key=len, reverse=True))) +
                         r')(?![\w"@])', re.I) if own_lc else None
    scopes = [(me, head)] + [(f"{me}.{p}", uncomment(v["raw"], True)) for p, v in procs.items()]
    for src, body in scopes:
        for m in REF_RE.finditer(body):
            dst = resolve(m.group(1), m.group(2))
            if m.group(1).upper() == "DATABASE":  # data reference, not an execution path
                add(src, dst, "TABLE_REF")
                if dst: use(src, dst, "REF")
            else: add(src, dst, "REF")
        for var, meth in CALL_RE.findall(body):
            for tt, tid in varmap.get(var.strip('"').lower(), ()):
                mu = meth.upper()
                if tt == "Table" and mu in WRITES: use(src, f"Table {tid}", "WRITE")
                elif tt == "Table" and mu in READS: use(src, f"Table {tid}", "READ")
                tp = idx.pn.get((tt, tid), {}).get(meth.lower())
                if tp: add(src, f"{tt} {tid}.{tp[0]}", "CALL")
                elif mu == "RUN" and tt != "Table": add(src, f"{tt} {tid}", "CALL")
        for meth in (self_re.findall(body) if self_re else ()):
            add(src, f"{me}.{own_lc[meth.lower()]}", "CALL")
    return edges, tops

def analyze(orig, comp, changed_objs, added, changed):
    """changed_objs: {(type,id)}; added/changed: {(type,id,proc)} from the Semantic Diff report."""
    idx = Index({**orig, **comp})
    edges, tops = Counter(), Counter()
    for key, block in comp.items():
        e, t = scan(key, block, idx); edges.update(e); tops.update(t)
    oedges, otops = set(), set()
    for key, block in orig.items():
        e, t = scan(key, block, idx); oedges.update(e); otops.update(t)
    orig_procs = {k: {p.lower() for p in split_procs(b)} for k, b in orig.items()}

    def obj_origin(key):
        if key in orig:
            if key in changed_objs: return "MODIFIED_STANDARD"
            return "STANDARD_UNCHANGED"
        return "CUSTOM"
    def key_of(node):
        t, i = obj_of(node).rsplit(" ", 1); return (t, int(i))
    def origin(node):
        key = key_of(node)
        if "." not in node: return obj_origin(key)
        p = node.split(".", 1)[1]
        obj_o = obj_origin(key)
        if obj_o == "CUSTOM": return "CUSTOM"
        if (*key, p) in added: return "ADDED"
        if (*key, p) in changed: return "CHANGED"
        return obj_o
    def is_new(src, dst, kind):
        key = key_of(src)
        if key not in orig: return True
        if "." in src and src.split(".", 1)[1].lower() not in orig_procs[key]: return True
        return (src, dst, kind) not in oedges
    def src_class(src, new):
        o = origin(src)
        if o in ("CUSTOM", "ADDED"): return "CUSTOM_OBJECT" if o == "CUSTOM" else "ADDED_PROC"
        if o == "CHANGED" and new: return "CHANGED_PROC"
        if o == "MODIFIED_STANDARD" and "." not in src and new: return "MODIFIED_OBJECT"
        return None

    objects, procs, edge_rows, use_rows, c2s = [], [], [], [], []
    deg_out, deg_in, nproc = Counter(), Counter(), Counter()
    for (s, d, k), c in edges.items(): deg_out[s] += 1; deg_in[d] += 1
    for key in sorted(set(comp) | set(orig), key=lambda k: (k[0], k[1])):
        node = f"{key[0]} {key[1]}"
        for lc, (p, line, local) in idx.pn[key].items():
            pn_ = f"{node}.{p}"; nproc[node] += 1
            procs.append((pn_, node, p, line, int(local), origin(pn_)))
        objects.append([node, key[0], key[1], idx.obj_name.get(node, ""), obj_origin(key), int(key in orig),
                        int(key in changed_objs), 0, 0, 0])
    for o in objects:
        o[7], o[8], o[9] = nproc[o[0]], deg_out[o[0]], deg_in[o[0]]
    for (s, d, k), c in sorted(edges.items()):
        new = is_new(s, d, k)
        edge_rows.append((s, d, k, c, int(new), obj_of(s), obj_of(d)))
        sc, do = src_class(s, new), origin(d)
        if sc and do in ("STANDARD_UNCHANGED", "MODIFIED_STANDARD", "CHANGED"):
            c2s.append((s, sc, k, d, "MODIFIED_STANDARD" if do in ("MODIFIED_STANDARD", "CHANGED") else "STANDARD", c))
    for (s, tb, op), c in sorted(tops.items()):
        use_rows.append((s, origin(s), tb, idx.obj_name.get(tb, ""), op, c, int((s, tb, op) not in otops or key_of(s) not in orig), obj_of(s)))
    return {"objects": objects, "procs": procs, "edges": edge_rows, "usage": use_rows, "c2s": c2s,
            "origin": origin, "names": idx.obj_name}

def parse_diff(path):
    x = pd.read_excel(path, sheet_name=None)
    o, p = x["Object Semantic Summary"], x["Procedure Changes"]
    changed_objs = {(r["Object Type"], int(r["Object ID"])) for _, r in o.iterrows() if r["Semantic Change Detected"] == "Yes"}
    added = {(r["Object Type"], int(r["Object ID"]), r["Procedure"]) for _, r in p.iterrows() if r["Change Type"] == "ADDED"}
    changed = {(r["Object Type"], int(r["Object ID"]), r["Procedure"]) for _, r in p.iterrows() if r["Change Type"] == "CHANGED"}
    return changed_objs, added, changed

def write_db(path, res):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): path.unlink()
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE objects(node TEXT PRIMARY KEY, type TEXT, id INT, name TEXT, origin TEXT, in_original INT,
        semantic_change INT, procedures INT, out_edges INT, in_edges INT);
    CREATE TABLE procedures(node TEXT PRIMARY KEY, object_node TEXT, name TEXT, line INT, is_local INT, origin TEXT);
    CREATE TABLE edges(src TEXT, dst TEXT, kind TEXT, count INT, new_vs_original INT, src_object TEXT, dst_object TEXT);
    CREATE TABLE table_usage(src TEXT, src_origin TEXT, table_node TEXT, table_name TEXT, usage TEXT, count INT,
        new_vs_original INT, src_object TEXT);
    CREATE TABLE custom_to_standard(src TEXT, src_class TEXT, kind TEXT, dst TEXT, dst_class TEXT, count INT);
    CREATE INDEX ix_e_src ON edges(src); CREATE INDEX ix_e_dst ON edges(dst);
    CREATE INDEX ix_e_so ON edges(src_object); CREATE INDEX ix_e_do ON edges(dst_object);
    CREATE INDEX ix_u_t ON table_usage(table_node); CREATE INDEX ix_c_d ON custom_to_standard(dst);""")
    ins = lambda t, rows, w: db.executemany(f"INSERT INTO {t} VALUES({','.join('?'*w)})", rows)
    ins("objects", res["objects"], 10); ins("procedures", res["procs"], 6); ins("edges", res["edges"], 7)
    ins("table_usage", res["usage"], 8); ins("custom_to_standard", res["c2s"], 6)
    db.commit(); db.close()

def sheet(wb, title, headers, rows):
    ws = wb.create_sheet(title)
    for i in range(1, len(headers) + 1): ws.column_dimensions[get_column_letter(i)].width = 24
    ws.freeze_panes = "A2"
    hdr = []
    for h in headers:
        c = WriteOnlyCell(ws, value=h); c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78"); hdr.append(c)
    ws.append(hdr)
    count = 0
    for r in rows:
        if count >= 1_048_574: break  # Excel row limit
        ws.append(list(r)); count += 1
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{count + 1}"
    return count

def write_excel(path, res):
    origin, names, edges = res["origin"], res["names"], res["edges"]
    wb = Workbook(write_only=True)
    # object-level caller/callee
    agg = defaultdict(lambda: [set(), 0, 0, 0])
    for s, d, k, c, new, so, do in edges:
        if so == do: continue
        a = agg[(so, do)]; a[0].add(k); a[1] += c; a[2] += "." in s and "." in d; a[3] |= new
    caller = [(so, origin(so), do, origin(do), ", ".join(sorted(a[0])), a[1], a[2], "Yes" if a[3] else "No")
              for (so, do), a in sorted(agg.items())]
    calls = [(s, origin(s), d, origin(d), c, "Yes" if new else "No") for s, d, k, c, new, *_ in edges if k == "CALL" and "." in s]
    hot = Counter(); hot_src = defaultdict(set)
    for s, sc, k, d, dc, c in res["c2s"]: hot[d] += c; hot_src[d].add(obj_of(s))
    # summary
    ob = Counter(o[4] for o in res["objects"]); pr = Counter(p[5] for p in res["procs"])
    ek = Counter(e[2] for e in edges); cs = Counter(r[1] for r in res["c2s"])
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 42; ws.column_dimensions["B"].width = 14; ws.column_dimensions["C"].width = 90
    rows = [("NAV Dependency Report", "", ""), ("", "", ""), ("Metric", "Count", "Note"),
            ("Objects", len(res["objects"]), "")] + [(f"  objects: {k}", v, "") for k, v in sorted(ob.items())] + \
           [("Procedures", len(res["procs"]), "")] + [(f"  procedures: {k}", v, "") for k, v in sorted(pr.items())] + \
           [("Dependency edges", len(edges), "")] + [(f"  edges: {k}", v, "") for k, v in sorted(ek.items())] + \
           [("Table usage rows", len(res["usage"]), ""), ("Custom-to-standard rows", len(res["c2s"]), "")] + \
           [(f"  from {k}", v, "") for k, v in sorted(cs.items())] + [("", "", ""),
            ("Caveats", "", ""),
            ("Classification rules", "", "Based on baseline presence + Semantic Diff results (Modified=Yes and object ID are ignored)."),
            ("Object in baseline, unchanged", "", "STANDARD_UNCHANGED"),
            ("Object in baseline, changed", "", "MODIFIED_STANDARD"),
            ("Object not in baseline", "", "CUSTOM"),
            ("Procedure new on standard object", "", "ADDED"),
            ("Procedure changed on standard object", "", "CHANGED"),
            ("Changed procedure / object edges", "", "Only edges that are new versus the original count as custom-to-standard."),
            ("Resolution", "", "Static text analysis: dynamic RUNMODAL/RecordRef calls, field-level dependencies and implicit Rec in reports are not resolved."),
            ("Table usage READ/WRITE", "", "Counted per call site of typed Record variables (and Rec/xRec) by method name.")]
    for r in rows: ws.append(list(r))
    sheet(wb, "Objects", ["Node", "Type", "ID", "Name", "Origin", "In Original", "Semantic Change", "Procedures", "Out Edges", "In Edges"], res["objects"])
    sheet(wb, "Caller-Callee", ["Caller", "Caller Origin", "Callee", "Callee Origin", "Kinds", "References", "Proc-level Pairs", "New vs Original"], caller)
    sheet(wb, "Procedure Calls", ["Caller", "Caller Origin", "Callee", "Callee Origin", "Calls", "New vs Original"], calls)
    sheet(wb, "Table Usage", ["Source", "Source Origin", "Table", "Table Name", "Usage", "Count", "New vs Original", "Source Object"], res["usage"])
    sheet(wb, "Custom to Standard", ["Custom Source", "Source Class", "Kind", "Standard Target", "Target Class", "Count", "Target Name"],
          [(*r, names.get(obj_of(r[3]), "")) for r in res["c2s"]])
    sheet(wb, "Standard Hotspots", ["Standard Target", "Name", "Class", "Custom References", "Distinct Custom Objects"],
          [(d, names.get(obj_of(d), ""), "MODIFIED_STANDARD" if origin(d) in ("MODIFIED_STANDARD", "CHANGED") else "STANDARD", c, len(hot_src[d]))
           for d, c in hot.most_common()])
    wb.save(path)

def reach(edges, start, reverse, kinds=("CALL",)):
    # CALL = real code-level calls. VAR/SOURCE/RELATION/TABLE_REF only say "uses the type"; REF (X::"Name")
    # is a loose navigation link. Following them inflates impact (PostItemJnlLine: 121 -> 851 -> 8225).
    adj = defaultdict(list)
    for s, d, k, *_ in edges:
        if k in kinds: adj[d if reverse else s].append(s if reverse else d)
    seen, q = {start}, deque([start])
    while q:
        for nxt in adj[q.popleft()]:
            if nxt not in seen: seen.add(nxt); q.append(nxt)
    seen.discard(start)
    return sorted(seen)

def main():
    ap = argparse.ArgumentParser()
    #ap.add_argument("--original",help="Original (standard) NAV export TXT",default="data/input/original")
    ap.add_argument("--company", required=True, help="Company export ZIP")
    ap.add_argument("--diff", required=True, help="Semantic Source Diff report (.xlsx)")
    #ap.add_argument("--db", default="data/depgraph/depgraph.db")
    ap.add_argument("--excel", default="NAV_Dependency_Report.xlsx")
    ap.add_argument("--impact", action="append", default=[], help='node, e.g. "Codeunit 80.PostItemJnlLine": transitive dependents')
    ap.add_argument("--kinds", default="CALL", help="edge kinds followed by --impact (default CALL; add REF for loose navigation links)")
    args = ap.parse_args()
    original_dir = "data/input/original"
    company_dir = f"data/input/{args.company}"
    db_path = f"data/depgraph/{args.company}/depgraph.db"
    excel_path = f"reports/{args.company}/{args.excel}"
    diff_path = f"reports/{args.company}/{args.diff}"
    changed_objs, added, changed = parse_diff(diff_path)
    res = analyze(n.load_original(original_dir), n.load_company(company_dir), changed_objs, added, changed)
    Path(excel_path).parent.mkdir(parents=True, exist_ok=True)
    write_db(db_path, res); write_excel(excel_path, res)
    print(f"objects {len(res['objects'])}  procedures {len(res['procs'])}  edges {len(res['edges'])}  "
          f"table-usage {len(res['usage'])}  custom->standard {len(res['c2s'])}")
    print(f"DB: {db_path}\nExcel: {excel_path}")
    for t in args.impact:
        r = reach(res["edges"], t, True, tuple(args.kinds.split(","))); print(f"IMPACT {t}: {len(r)}"); [print("  ", x) for x in r[:40]]

if __name__ == "__main__":
    main()
