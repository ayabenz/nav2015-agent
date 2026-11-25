#!/usr/bin/env python3
"""Audit every object flagged by nav_semantic_diff: per-element diff, whitespace-only marked."""
import argparse, difflib, re
from pathlib import Path
import pandas as pd
from . import semantic_diff as n

def squash(s):  # drop every whitespace char: equal after this => whitespace-only difference
    return re.sub(r"\s+", "", s)

TAIL = re.compile(r"\s*BEGIN END\.(\s*\}\s*\})?\s*$")

def strip_tail(s):  # object's closing "BEGIN END." block is glued to the last procedure/header
    return TAIL.sub("", s)

def summarize(a, b):
    ta, tb = a.split(), b.split()
    ops = [(t, " ".join(ta[i1:i2]), " ".join(tb[j1:j2]))
           for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes() if t != "equal"]
    deleted = sum(len(o[1].split()) for o in ops); inserted = sum(len(o[2].split()) for o in ops)
    text = " | ".join(f"{t}: [{x[:80]}] -> [{y[:80]}]" for t, x, y in ops[:3])
    return len(ops), deleted, inserted, text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True, help="Company name (uses data/input/{company})")
    ap.add_argument("--output", default="NAV_Audit_Report.xlsx")
    args = ap.parse_args()
    orig, comp = n.load_original("data/input/original"), n.load_company(f"data/input/{args.company}")
    args.output = f"reports/{args.company}/{args.output}"
    rows = []
    def add(key, name, kind, elem, a, b):
        ws = squash(a) == squash(b) and a != b
        art = not ws and kind in ("PROC CHANGED", "CODE HEADER/VARS") and strip_tail(a) == strip_tail(b)
        cat = "WHITESPACE ONLY" if ws else "BOUNDARY ARTIFACT" if art else "REAL"
        nops, dele, ins, text = summarize(a, b)
        rows.append({"Object Type": key[0], "Object ID": key[1], "Object Name": name, "Element Type": kind,
                     "Element": elem, "Category": cat, "Diff Ops": nops,
                     "Tokens Deleted": dele, "Tokens Inserted": ins, "Diff Summary": text})
    for key in sorted(set(orig) & set(comp)):
        ob, cb = orig[key], comp[key]
        head = n.HEADER.search(cb); name = head.group(3).strip() if head else ""
        op, cp = n.procedures(ob), n.procedures(cb)
        for p in sorted(set(cp) - set(op)): add(key, name, "PROC ADDED", p, "", cp[p]["tokens"])
        for p in sorted(set(op) - set(cp)): add(key, name, "PROC REMOVED", p, op[p]["tokens"], "")
        for p in sorted(set(op) & set(cp)):
            if op[p]["tokens"] != cp[p]["tokens"]: add(key, name, "PROC CHANGED", p, op[p]["tokens"], cp[p]["tokens"])
        a, b = n.trigger_tokens(ob), n.trigger_tokens(cb)
        if a != b: add(key, name, "CODE HEADER/VARS", "(before first procedure)", a, b)
        for sec in n.SECTIONS:
            a, b = n.section_tokens(ob, sec), n.section_tokens(cb, sec)
            if a != b: add(key, name, "SECTION", sec, a, b)
    detail = pd.DataFrame(rows)
    g = detail.groupby(["Object Type", "Object ID", "Object Name"], sort=False)
    summ = g.agg(**{"Elements Changed": ("Element", "size"),
                    "Whitespace-only Elements": ("Category", lambda s: int((s == "WHITESPACE ONLY").sum())),
                    "Boundary-artifact Elements": ("Category", lambda s: int((s == "BOUNDARY ARTIFACT").sum())),
                    "Real Elements": ("Category", lambda s: int((s == "REAL").sum())),
                    "Tokens Deleted": ("Tokens Deleted", "sum"), "Tokens Inserted": ("Tokens Inserted", "sum")}).reset_index()
    summ["Verdict"] = summ.apply(lambda r: "NOISE ONLY (whitespace/boundary)" if r["Real Elements"] == 0 else
                                 ("REAL + NOISE" if r["Elements Changed"] > r["Real Elements"] else "REAL"), axis=1)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(args.output, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Object Verdict", index=False)
        detail.to_excel(xw, sheet_name="Element Detail", index=False)
        for sh in xw.book.worksheets:
            sh.freeze_panes = "A2"; sh.auto_filter.ref = sh.dimensions
    print(f"Objects audited: {len(summ)}"); print(summ["Verdict"].value_counts().to_string())
    print(detail["Category"].value_counts().to_string())
    print(f"Report: {args.output}")

if __name__ == "__main__":
    main()
