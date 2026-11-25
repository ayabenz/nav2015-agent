"""Regression tests for CSV v3 support in parse_diff()."""
import os, tempfile, csv
from pathlib import Path
from nav_ai.depgraph import parse_diff


def _write_csv(tmpdir, name, rows, header):
    p = Path(tmpdir) / name
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header.split(","))
        for r in rows:
            writer.writerow(r.split(","))
    return str(p)


def test_parse_diff_csv_object_summary():
    with tempfile.TemporaryDirectory() as td:
        path = _write_csv(
            td,
            "report_Object_Semantic_Summary.csv",
            [
                'Table,18,Customer,Yes,,0,0,,0,,,,,,,,',
                'Codeunit,80,Sales-Post,No,,0,0,,0,,,,,,,,',
            ],
            "Object Type,Object ID,Object Name,Semantic Change Detected,Added Procedures,Removed Procedures,Changed Procedures,Unchanged Procedures,Trigger Changed,Changed Sections,Original Version List,Company Version List,Company Modified Flag,Added Procedure Names,Removed Procedure Names,Changed Procedure Names",
        )
        changed_objs, added, changed = parse_diff(path)
        assert ("Table", 18) in changed_objs
        assert ("Codeunit", 80) not in changed_objs
        assert added == set()
        assert changed == set()


def test_parse_diff_csv_procedure_changes():
    with tempfile.TemporaryDirectory() as td:
        path = _write_csv(
            td,
            "report_Procedure_Changes.csv",
            [
                'Codeunit,80,Sales-Post,PostItemJnlLine,ADDED,,,,,,,,,,,,,,',
                'Codeunit,80,Sales-Post,Post,CHANGED,,,,,,,,,,,,,,',
                'Table,18,Customer,MyNewProc,ADDED,,,,,,,,,,,,,,',
            ],
            "Object Type,Object ID,Object Name,Procedure,Change Type,Original Line,Company Line,Original Signature,Company Signature,Original Code Excerpt,Company Code Excerpt,Original Version List,Company Version List,Company Modified Flag,Added Procedure Names,Removed Procedure Names,Changed Procedure Names",
        )
        changed_objs, added, changed = parse_diff(path)
        assert changed_objs == set()
        assert ("Codeunit", 80, "PostItemJnlLine") in added
        assert ("Codeunit", 80, "Post") in changed
        assert ("Table", 18, "MyNewProc") in added


def test_parse_diff_csv_both_files_merged():
    """Simulate main() merging object summary CSV and procedure changes CSV."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "report"
        _write_csv(
            td,
            "report_Object_Semantic_Summary.csv",
            ['Table,18,Customer,Yes,,0,0,,0,,,,,,,,'],
            "Object Type,Object ID,Object Name,Semantic Change Detected,Added Procedures,Removed Procedures,Changed Procedures,Unchanged Procedures,Trigger Changed,Changed Sections,Original Version List,Company Version List,Company Modified Flag,Added Procedure Names,Removed Procedure Names,Changed Procedure Names",
        )
        _write_csv(
            td,
            "report_Procedure_Changes.csv",
            ['Codeunit,80,Sales-Post,NewProc,ADDED,,,,,,,,,,,,,,'],
            "Object Type,Object ID,Object Name,Procedure,Change Type,Original Line,Company Line,Original Signature,Company Signature,Original Code Excerpt,Company Code Excerpt,Original Version List,Company Version List,Company Modified Flag,Added Procedure Names,Removed Procedure Names,Changed Procedure Names",
        )
        co, ca, cc = parse_diff(str(base) + "_Object_Semantic_Summary.csv")
        _, pa, pc = parse_diff(str(base) + "_Procedure_Changes.csv")
        changed_objs, added, changed = co, ca | pa, cc | pc
        assert ("Table", 18) in changed_objs
        assert ("Codeunit", 80, "NewProc") in added


def test_parse_diff_xlsx_still_works():
    """Ensure existing xlsx path still works (create a minimal xlsx)."""
    import pandas as pd
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "report.xlsx"
        o = pd.DataFrame({
            "Object Type": ["Table", "Codeunit"],
            "Object ID": [18, 80],
            "Object Name": ["Customer", "Sales-Post"],
            "Semantic Change Detected": ["Yes", "No"],
        })
        p = pd.DataFrame({
            "Object Type": ["Codeunit"],
            "Object ID": [80],
            "Object Name": ["Sales-Post"],
            "Procedure": ["Post"],
            "Change Type": ["CHANGED"],
        })
        with pd.ExcelWriter(path) as xl:
            o.to_excel(xl, sheet_name="Object Semantic Summary", index=False)
            p.to_excel(xl, sheet_name="Procedure Changes", index=False)
        changed_objs, added, changed = parse_diff(path)
        assert ("Table", 18) in changed_objs
        assert ("Codeunit", 80) not in changed_objs
        assert ("Codeunit", 80, "Post") in changed
