#!/usr/bin/env python3
"""Heuristic semantic diff for Microsoft Dynamics NAV C/AL TXT object exports."""
from __future__ import annotations
import argparse, hashlib, re, zipfile
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

HEADER = re.compile(r'^OBJECT\s+(Table|Page|Report|Codeunit|Query|XMLport|MenuSuite)\s+(\d+)\s+([^\r\n]+)', re.M)
PROC = re.compile(r'(?mi)^\s{4}(?:(LOCAL)\s+)?PROCEDURE\s+("?[^@\s(]+"?|[A-Za-z_][\w.]*)\s*(?:@\d+)?\s*\(')
TOKEN = re.compile(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'|:=|<>|<=|>=|\.\.|[A-Za-z_][A-Za-z0-9_.]*|\d+(?:\.\d+)?D?|[^\s]', re.S)
STRUCTURAL = {"FIELDS","KEYS","FIELDGROUPS","CONTROLS","ACTIONS","REQUESTPAGE","DATAITEMS","ELEMENTS"}
SECTIONS = ["PROPERTIES","FIELDS","KEYS","FIELDGROUPS","CONTROLS","ACTIONS","REQUESTPAGE","DATAITEMS","ELEMENTS"]

def read_objects(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # TXT is \n, ZIP members are \r\n
    ms = list(HEADER.finditer(text))
    return {(m.group(1), int(m.group(2))): text[m.start():(ms[i+1].start() if i+1 < len(ms) else len(text))].strip()
            for i, m in enumerate(ms)}

def load_objects(path):
    """Load NAV objects from a file (.txt), ZIP file, or folder containing .txt/.zip files."""
    path = Path(path)
    objects = {}
    if path.is_dir():
        for txt_path in sorted(path.rglob("*.txt")):
            text = txt_path.read_text(encoding="utf-8-sig", errors="replace")
            objects.update(read_objects(text))
        for zip_path in sorted(path.rglob("*.zip")):
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".txt"):
                        objects.update(read_objects(zf.read(name).decode("utf-8-sig", errors="replace")))
    elif path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".txt"):
                    objects.update(read_objects(zf.read(name).decode("utf-8-sig", errors="replace")))
    else:
        # Single .txt file
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        objects.update(read_objects(text))
    return objects


def load_original(path):
    return load_objects(path)


def load_company(path):
    return load_objects(path)

def section(block, name):
    m = re.search(r'(?m)^\s{2}' + re.escape(name) + r'\s*\{', block)
    if not m: return ""
    start, depth, in_string, i = m.end()-1, 0, False, m.end()-1
    while i < len(block):
        c = block[i]
        if c == '"':
            if in_string and i+1 < len(block) and block[i+1] == '"':
                i += 2; continue
            in_string = not in_string
        if not in_string:
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return block[start+1:i]
        i += 1
    return block[start+1:]

def strip_cal_comments(source, strip_braces=True):
    """Remove C/AL // and {...} comments without touching quoted literals."""
    out = []
    i = 0
    single = double = False
    brace_depth = 0
    while i < len(source):
        c = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if single:
            out.append(c)
            if c == "'" and nxt == "'":
                out.append(nxt); i += 2; continue
            if c == "'":
                single = False
            i += 1; continue
        if double:
            out.append(c)
            if c == '"' and nxt == '"':
                out.append(nxt); i += 2; continue
            if c == '"':
                double = False
            i += 1; continue
        if c == "'":
            single = True; out.append(c); i += 1; continue
        if c == '"':
            double = True; out.append(c); i += 1; continue
        if c == "/" and nxt == "/":
            out.extend("  "); i += 2
            while i < len(source) and source[i] not in "\r\n":
                out.append(" "); i += 1
            continue
        if strip_braces and c == "{":
            brace_depth = 1
            out.append(" "); i += 1
            while i < len(source) and brace_depth:
                ch = source[i]
                if ch == "{": brace_depth += 1
                elif ch == "}": brace_depth -= 1
                out.append("\n" if ch == "\n" else " ")
                i += 1
            continue
        out.append(c); i += 1
    return "".join(out)


def mask_cal_strings(source):
    """Replace single-quoted C/AL strings with spaces, preserving line positions."""
    out = []
    i = 0
    in_string = False
    while i < len(source):
        c = source[i]
        if not in_string and c == "'":
            in_string = True; out.append(" "); i += 1; continue
        if in_string:
            if c == "'" and i + 1 < len(source) and source[i + 1] == "'":
                out.extend("  "); i += 2; continue
            if c == "'":
                in_string = False
            out.append("\n" if c == "\n" else " ")
            i += 1; continue
        out.append(c); i += 1
    return "".join(out)


def lexical_tokens(source, strip_braces=True):
    source = strip_cal_comments(source, strip_braces=strip_braces)
    return " ".join(TOKEN.findall(source))

CODE_TAIL = re.compile(r'\n\s{4}BEGIN\s*(?:\{[^{}]*\}\s*)?END\.[\s}]*$')

def code_section(block):
    # The object's closing "BEGIN END." block is not part of the last procedure.
    return CODE_TAIL.sub("\n", section(block, "CODE"))

def procedures(block):
    code = code_section(block)
    matches = list(PROC.finditer(code))
    result = {}
    for i, m in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(code)
        raw = code[m.start():end]
        name = m.group(2).strip('"')
        semi = raw.find(';')
        signature = raw[:semi+1] if semi >= 0 else raw[:1000]
        result[name] = {"tokens": lexical_tokens(raw), "signature": lexical_tokens(signature),
                        "line": code.count("\n", 0, m.start()) + 1, "raw": raw}
    return result

def trigger_tokens(block):
    code = code_section(block)
    m = PROC.search(code)
    return lexical_tokens(code[:m.start()] if m else code)

def section_tokens(block, name):
    return lexical_tokens(section(block, name), strip_braces=name not in STRUCTURAL)

def canonical_source(block):
    block = re.sub(r'(?m)^\s*(Date|Time|Modified|Version List)\s*=.*?;\s*$', '', block)
    block = block.replace("\r\n", "\n").replace("\r", "\n")
    block = re.sub(r'[ \t]+', ' ', block)
    block = re.sub(r'\n\s*\n+', '\n', block)
    return block.strip()

def metadata(block, key):
    props = section(block, "OBJECT-PROPERTIES")
    m = re.search(r'(?m)^\s*' + re.escape(key) + r'\s*=(.*?);?\s*$', props)
    return m.group(1).strip() if m else ""

def analyze(original, company):
    object_rows, procedure_rows, section_rows = [], [], []
    for key in sorted(set(original) & set(company)):
        ob, cb = original[key], company[key]
        op, cp = procedures(ob), procedures(cb)
        added, removed = sorted(set(cp)-set(op)), sorted(set(op)-set(cp))
        changed = sorted(n for n in set(op)&set(cp) if op[n]["tokens"] != cp[n]["tokens"])
        unchanged = len(set(op)&set(cp)) - len(changed)
        trigger_changed = trigger_tokens(ob) != trigger_tokens(cb)
        changed_sections = []
        for sec in SECTIONS:
            before, after = section_tokens(ob, sec), section_tokens(cb, sec)
            if before != after:
                changed_sections.append(sec)
                section_rows.append({"Object Type":key[0],"Object ID":key[1],"Section":sec,
                    "Original normalized tokens":len(before.split()),"Company normalized tokens":len(after.split()),
                    "Original excerpt":section(ob,sec)[:700].strip(),"Company excerpt":section(cb,sec)[:700].strip()})
        semantic = bool(added or removed or changed or trigger_changed or changed_sections)
        head = HEADER.search(cb); name = head.group(3).strip() if head else ""
        ov, cv = metadata(ob,"Version List"), metadata(cb,"Version List")
        object_rows.append({"Object Type":key[0],"Object ID":key[1],"Object Name":name,
            "Added Procedures":len(added),"Removed Procedures":len(removed),"Changed Procedures":len(changed),
            "Unchanged Procedures":unchanged,"Trigger Changed":"Yes" if trigger_changed else "No",
            "Changed Sections":", ".join(changed_sections),"Semantic Change Detected":"Yes" if semantic else "No",
            "Original Version List":ov,"Company Version List":cv,"Company Modified Flag":metadata(cb,"Modified"),
            "Added Procedure Names":", ".join(added),"Removed Procedure Names":", ".join(removed),
            "Changed Procedure Names":", ".join(changed)})
        for typ, names in [("ADDED",added),("REMOVED",removed),("CHANGED",changed)]:
            for name2 in names:
                before, after = op.get(name2), cp.get(name2)
                procedure_rows.append({"Object Type":key[0],"Object ID":key[1],"Object Name":name,
                    "Change Type":typ,"Procedure":name2,"Original Line":before["line"] if before else "",
                    "Company Line":after["line"] if after else "",
                    "Original Signature":before["signature"] if before else "",
                    "Company Signature":after["signature"] if after else "",
                    "Original Code Excerpt":before["raw"][:1200].strip() if before else "",
                    "Company Code Excerpt":after["raw"][:1200].strip() if after else ""})
    return pd.DataFrame(object_rows), pd.DataFrame(procedure_rows), pd.DataFrame(section_rows)

def add_table(wb, name, frame, table_name):
    sh = wb.create_sheet(name)
    sh.append(list(frame.columns))
    for row in frame.itertuples(index=False, name=None):
        sh.append([None if pd.isna(v) else v for v in row])
    sh.freeze_panes = "A2"; sh.auto_filter.ref = sh.dimensions
    for col in sh.columns:
        letter = get_column_letter(col[0].column)
        maxlen = max((len(str(c.value or "")) for c in list(col)[:100]), default=12)
        sh.column_dimensions[letter].width = min(max(maxlen+2, 14), 65)
    for c in sh[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    if sh.max_row > 1:
        t = Table(displayName=table_name, ref=sh.dimensions)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sh.add_table(t)

def write_report(out, objects, procs, sections):
    wb = Workbook(); ws = wb.active; ws.title = "Dashboard"
    ws["A1"] = "NAV C/AL Semantic Source Diff"
    ws["A1"].font = Font(size=16,bold=True,color="FFFFFF")
    ws["A1"].fill = PatternFill("solid",fgColor="1F4E78"); ws.merge_cells("A1:C1")
    ws.append(["Metric","Count","Meaning"])
    rows = [
        ("Matched objects",len(objects),"Object Type + Object ID found in both exports"),
        ("Semantic changes",int((objects["Semantic Change Detected"]=="Yes").sum()),"Heuristic changes in procedures, triggers, or supported sections"),
        ("Added procedures",int((procs["Change Type"]=="ADDED").sum()) if len(procs) else 0,"New procedure names"),
        ("Removed procedures",int((procs["Change Type"]=="REMOVED").sum()) if len(procs) else 0,"Missing procedure names"),
        ("Changed procedures",int((procs["Change Type"]=="CHANGED").sum()) if len(procs) else 0,"Same-name procedures with different tokens"),
        ("Changed sections",len(sections),"Differences in supported structural sections")]
    for r in rows: ws.append(list(r))
    add_table(wb,"Object Semantic Summary",objects,"ObjectSemanticSummary")
    add_table(wb,"Procedure Changes",procs,"ProcedureChanges")
    add_table(wb,"Section Changes",sections,"SectionChanges")
    wb.save(out)

def main():
    ap=argparse.ArgumentParser()
    #ap.add_argument("--original",help="Original NAV object export TXT",default="data/input/original")
    ap.add_argument("--company",required=True,help="Company object export ZIP containing TXT files")
    ap.add_argument("--output",default="NAV_Semantic_Source_Diff_Report.xlsx")
    args=ap.parse_args()
    original_dir = "data/input/original"
    company_dir = f"data/input/{args.company}"
    output_dir = f"reports/{args.company}/{args.output}"
    original, company = load_original(original_dir), load_company(company_dir)
    objects, procs, sections = analyze(original,company)
    Path(output_dir).parent.mkdir(parents=True, exist_ok=True)
    write_report(output_dir,objects,procs,sections)
    print(f"Original objects: {len(original)}")
    print(f"Company objects: {len(company)}")
    print(f"Matched objects: {len(objects)}")
    print(f"Semantic changes: {(objects['Semantic Change Detected']=='Yes').sum()}")
    print(f"Report: {output_dir}")

if __name__ == "__main__":
    main()
