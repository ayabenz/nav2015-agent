import sqlite3

from nav_ai.business_inventory import generate_business_process_inventory


def make_graph():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE objects(node TEXT PRIMARY KEY,type TEXT,id INT,name TEXT,origin TEXT,
            in_original INT,semantic_change INT,procedures INT,out_edges INT,in_edges INT);
        CREATE TABLE procedures(node TEXT PRIMARY KEY,object_node TEXT,name TEXT,line INT,is_local INT,origin TEXT);
        CREATE TABLE edges(src TEXT,dst TEXT,kind TEXT,count INT,new_vs_original INT,src_object TEXT,dst_object TEXT);
        CREATE TABLE table_usage(src TEXT,src_origin TEXT,table_node TEXT,table_name TEXT,
            usage TEXT,count INT,new_vs_original INT,src_object TEXT);
        INSERT INTO objects VALUES
            ('Codeunit 60001','Codeunit',60001,'Parent','CUSTOM',0,1,1,1,0),
            ('Codeunit 60002','Codeunit',60002,'Child','CUSTOM',0,1,1,0,1);
        INSERT INTO procedures VALUES
            ('Codeunit 60001.Run','Codeunit 60001','Run',5,0,'CUSTOM'),
            ('Codeunit 60002.Update','Codeunit 60002','Update',5,0,'CUSTOM');
        INSERT INTO edges VALUES
            ('Codeunit 60001.Run','Codeunit 60002.Update','CALL',1,1,'Codeunit 60001','Codeunit 60002');
        INSERT INTO table_usage VALUES
            ('Codeunit 60001.Run','CUSTOM','Table 36','Sales Header','READ',1,0,'Codeunit 60001'),
            ('Codeunit 60002.Update','CUSTOM','Table 36','Sales Header','WRITE',1,1,'Codeunit 60002');
    """)
    return db


def make_symbols():
    db = sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE symbols(kind TEXT,name TEXT,num INT,object_type TEXT,object_id INT,
        object_name TEXT,detail TEXT,source_file TEXT,line INT,line_end INT)""")
    db.executemany("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?)", [
        ("procedure", "Run", None, "Codeunit", 60001, "Parent", "Run()", "parent.txt", 1, 12),
        ("procedure", "Update", None, "Codeunit", 60002, "Child", "Update()", "child.txt", 1, 12),
    ])
    return db


def test_inventory_writes_root_candidate_cluster_and_trace_reports(tmp_path):
    parent = """OBJECT Codeunit 60001 Parent
{
  CODE
  {
    PROCEDURE Run@1();
    BEGIN
      Child.Update;
    END;
  }
}"""
    child = """OBJECT Codeunit 60002 Child
{
  CODE
  {
    PROCEDURE Update@1();
    BEGIN
      IF Ready THEN
        MESSAGE('ready');
    END;
  }
}"""
    (tmp_path / "parent.txt").write_text(parent, encoding="utf-8")
    (tmp_path / "child.txt").write_text(child, encoding="utf-8")
    output = tmp_path / "reports" / "datascrip" / "business_process"
    result = generate_business_process_inventory(
        make_graph(), make_symbols(), [str(tmp_path)], output,
        limit=10, max_depth=3, analyze_conditions=True,
    )
    assert result["trace_success_count"] == 2
    assert result["trace_failure_count"] == 0
    assert (output / "process_inventory.md").is_file()
    assert (output / "process_inventory.json").is_file()
    assert (output / "objects" / "Codeunit_60001.md").is_file()
    assert (output / "objects" / "Codeunit_60001.json").is_file()
    assert result["semantics"]["runtime_evaluated"] is False
    assert "Codeunit 60002.Update" in (output / "objects" / "Codeunit_60001.md").read_text()


def test_inventory_records_unavailable_source_trace_without_aborting(tmp_path):
    output = tmp_path / "reports" / "datascrip" / "business_process"
    result = generate_business_process_inventory(
        make_graph(), make_symbols(), [str(tmp_path)], output,
        limit=10, max_depth=2, analyze_conditions=False,
    )
    assert result["trace_failure_count"] == 2
    assert all(item["status"] == "unavailable" for item in result["traces"].values())
    assert (output / "process_inventory.json").is_file()
