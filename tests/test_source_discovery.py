import sqlite3
import zipfile

from nav_ai.source_discovery import build_source_catalog, trace_call_graph


OBJ_A = """OBJECT Codeunit 60001 Parent
{
  CODE
  {
    PROCEDURE Run@1();
    BEGIN
      Child.Update;
    END;
  }
}"""

OBJ_B = """OBJECT Codeunit 60002 Child
{
  CODE
  {
    PROCEDURE Update@1();
    BEGIN
      MESSAGE('done');
    END;
  }
}"""


def graph_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE objects(node TEXT PRIMARY KEY,type TEXT,id INT,name TEXT,origin TEXT,
            in_original INT,semantic_change INT,procedures INT,out_edges INT,in_edges INT);
        CREATE TABLE procedures(node TEXT PRIMARY KEY,object_node TEXT,name TEXT,line INT,is_local INT,origin TEXT);
        CREATE TABLE edges(src TEXT,dst TEXT,kind TEXT,count INT,new_vs_original INT,src_object TEXT,dst_object TEXT);
        INSERT INTO objects VALUES
            ('Codeunit 60001','Codeunit',60001,'Parent','CUSTOM',0,0,1,1,0),
            ('Codeunit 60002','Codeunit',60002,'Child','CUSTOM',0,0,1,0,1);
        INSERT INTO procedures VALUES
            ('Codeunit 60001.Run','Codeunit 60001','Run',5,0,'CUSTOM'),
            ('Codeunit 60002.Update','Codeunit 60002','Update',5,0,'CUSTOM');
        INSERT INTO edges VALUES
            ('Codeunit 60001.Run','Codeunit 60002.Update','CALL',1,1,'Codeunit 60001','Codeunit 60002');
    """)
    return db


def symbol_db(source_file="child.txt"):
    db = sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE symbols(kind TEXT,name TEXT,num INT,object_type TEXT,object_id INT,
                  object_name TEXT,detail TEXT,source_file TEXT,line INT,line_end INT)""")
    db.execute("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?)",
               ("procedure", "Update", None, "Codeunit", 60002, "Child",
                "Update()", source_file, 4, 7))
    return db


def test_trace_resolves_call_graph_nodes_to_source_exports(tmp_path):
    (tmp_path / "parent.txt").write_text(OBJ_A, encoding="utf-8")
    (tmp_path / "child.txt").write_text(OBJ_B, encoding="utf-8")
    result = trace_call_graph(
        graph_db(), "Codeunit 60001", [str(tmp_path)], symbol_db(), max_depth=2
    )
    assert result["procedure_count"] == 2
    child = next(item for item in result["procedures"] if item["node"] == "Codeunit 60002.Update")
    assert child["depth"] == 1
    assert child["source"]["status"] == "resolved"
    assert child["source_line_start"] == 5
    assert child["call_path"] == ["Codeunit 60001.Run", "Codeunit 60002.Update"]
    assert result["process_summary"]["procedure_count"] == 2
    assert result["process_summary"]["call_edge_count"] == 1
    assert result["edge_count"] == 1
    assert result["semantics"]["runtime_evaluated"] is False


def test_trace_reports_missing_source_instead_of_guessing(tmp_path):
    (tmp_path / "parent.txt").write_text(OBJ_A, encoding="utf-8")
    result = trace_call_graph(
        graph_db(), "Codeunit 60001", [str(tmp_path)], symbol_db(),
        max_depth=1, analyze_conditions=True,
    )
    child = next(item for item in result["procedures"] if item["node"] == "Codeunit 60002.Update")
    assert child["source"]["status"] == "missing"
    assert child["condition_analysis"]["status"] == "source_unavailable"


def test_source_catalog_marks_duplicate_object_exports_ambiguous(tmp_path):
    (tmp_path / "one.txt").write_text(OBJ_B, encoding="utf-8")
    (tmp_path / "two.txt").write_text(OBJ_B, encoding="utf-8")
    catalog = build_source_catalog([str(tmp_path)])
    assert len(catalog[("codeunit", 60002)]) == 2



def test_trace_reports_object_level_run_target_without_guessing_procedure():
    db = graph_db()
    db.execute(
        "INSERT INTO edges VALUES(?,?,?,?,?,?,?)",
        ("Codeunit 60002.Update", "Codeunit 60001", "CALL", 1, 1,
         "Codeunit 60002", "Codeunit 60001"),
    )
    result = trace_call_graph(
        db, "Codeunit 60001", [], None, max_depth=3
    )
    assert result["unresolved_call_targets"] == [{
        "src": "Codeunit 60002.Update",
        "dst": "Codeunit 60001",
        "reason": "CALL edge targets an object/non-procedure graph node",
    }]



def test_source_catalog_reports_absolute_lines_after_file_prefix(tmp_path):
    path = tmp_path / "prefixed.txt"
    prefix = "\n\n"
    path.write_text(prefix + OBJ_B, encoding="utf-8")
    catalog = build_source_catalog([str(path)])
    procedure = catalog[("codeunit", 60002)][0]["procedures"]["update"]
    expected_offset = prefix.count("\n")
    assert procedure["line_start"] == expected_offset + 5



def test_object_trace_includes_object_and_trigger_scope_call_edges(tmp_path):
    db = graph_db()
    db.executemany(
        "INSERT INTO edges VALUES(?,?,?,?,?,?,?)",
        [
            ("Codeunit 60001", "Codeunit 60002.Update", "CALL", 1, 1,
             "Codeunit 60001", "Codeunit 60002"),
            ("Codeunit 60001 TRIGGERS", "Codeunit 60002.Update", "CALL", 1, 1,
             "Codeunit 60001", "Codeunit 60002"),
        ],
    )
    result = trace_call_graph(db, "Codeunit 60001", [], None, max_depth=1)
    assert result["procedure_count"] == 2
    assert {edge["src"] for edge in result["call_edges"]} == {
        "Codeunit 60001", "Codeunit 60001 TRIGGERS", "Codeunit 60001.Run"
    }



def test_source_catalog_reads_txt_objects_from_zip_roots(tmp_path):
    archive_path = tmp_path / "exports.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("objects/child.txt", OBJ_B)
    catalog = build_source_catalog([str(archive_path)])
    candidate = catalog[("codeunit", 60002)][0]
    assert candidate["source_label"] == "objects/child.txt"
    assert candidate["source_path"].endswith("exports.zip!objects/child.txt")



def test_trace_can_analyze_conditions_and_auto_load_table_metadata(tmp_path):
    child = """OBJECT Codeunit 60002 Child
{
  CODE
  {
    PROCEDURE Update@1(VAR Header@1000 : Record 36);
    BEGIN
      IF Header.Status = Header.Status::Released THEN BEGIN
        MESSAGE('released');
      END;
    END;
  }
}"""
    table = """OBJECT Table 36 Sales Header
{
  FIELDS
  {
    { 1 ; ; Status ; Option }
    {
      OptionString=Open,Released;
    }
  }
}"""
    (tmp_path / "parent.txt").write_text(OBJ_A, encoding="utf-8")
    (tmp_path / "child.txt").write_text(child, encoding="utf-8")
    (tmp_path / "table36.txt").write_text(table, encoding="utf-8")
    result = trace_call_graph(
        graph_db(), "Codeunit 60001", [str(tmp_path)], symbol_db(),
        max_depth=2, analyze_conditions=True,
    )
    child_result = next(
        item for item in result["procedures"] if item["node"] == "Codeunit 60002.Update"
    )
    analysis = child_result["condition_analysis"]
    assert analysis["semantic_resolution"]["enabled"] is True
    assert analysis["semantic_resolution"]["table_ids_loaded"] == [36]
    assert analysis["runtime_evaluated"] is False
    def walk(value):
        if isinstance(value, dict):
            if value.get("type") == "if":
                yield value
            for child in value.values():
                if isinstance(child, (dict, list)):
                    yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    if_nodes = list(walk(analysis["nodes"]))
    assert len(if_nodes) == 1
    assert "normalized_condition" in if_nodes[0]



def test_auto_condition_analysis_reports_missing_table_metadata(tmp_path):
    child = """OBJECT Codeunit 60002 Child
{
  CODE
  {
    PROCEDURE Update@1(VAR Header@1000 : Record 36);
    BEGIN
      IF Header.Status = Header.Status::Released THEN BEGIN
        MESSAGE('released');
      END;
    END;
  }
}"""
    (tmp_path / "parent.txt").write_text(OBJ_A, encoding="utf-8")
    (tmp_path / "child.txt").write_text(child, encoding="utf-8")
    result = trace_call_graph(
        graph_db(), "Codeunit 60001", [str(tmp_path)], symbol_db(),
        max_depth=2, analyze_conditions=True,
    )
    child_result = next(
        item for item in result["procedures"] if item["node"] == "Codeunit 60002.Update"
    )
    assert child_result["condition_analysis"]["semantic_resolution"]["missing_table_ids_for_procedure"] == [36]
