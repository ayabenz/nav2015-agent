import sqlite3

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
    assert result["edge_count"] == 1
    assert result["semantics"]["runtime_evaluated"] is False


def test_trace_reports_missing_source_instead_of_guessing(tmp_path):
    (tmp_path / "parent.txt").write_text(OBJ_A, encoding="utf-8")
    result = trace_call_graph(
        graph_db(), "Codeunit 60001", [str(tmp_path)], symbol_db(), max_depth=1
    )
    child = next(item for item in result["procedures"] if item["node"] == "Codeunit 60002.Update")
    assert child["source"]["status"] == "missing"


def test_source_catalog_marks_duplicate_object_exports_ambiguous(tmp_path):
    (tmp_path / "one.txt").write_text(OBJ_B, encoding="utf-8")
    (tmp_path / "two.txt").write_text(OBJ_B, encoding="utf-8")
    catalog = build_source_catalog([str(tmp_path)])
    assert len(catalog[("codeunit", 60002)]) == 2
