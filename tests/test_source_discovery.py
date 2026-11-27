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
        CREATE TABLE table_usage(src TEXT,src_origin TEXT,table_node TEXT,table_name TEXT,usage TEXT,
            count INT,new_vs_original INT,src_object TEXT);
        INSERT INTO objects VALUES
            ('Codeunit 60001','Codeunit',60001,'Parent','CUSTOM',0,0,1,1,0),
            ('Codeunit 60002','Codeunit',60002,'Child','CUSTOM',0,0,1,0,1);
        INSERT INTO procedures VALUES
            ('Codeunit 60001.Run','Codeunit 60001','Run',5,0,'CUSTOM'),
            ('Codeunit 60002.Update','Codeunit 60002','Update',5,0,'CUSTOM');
        INSERT INTO edges VALUES
            ('Codeunit 60001.Run','Codeunit 60002.Update','CALL',1,1,'Codeunit 60001','Codeunit 60002');
        INSERT INTO table_usage VALUES
            ('Codeunit 60002.Update','CUSTOM','Table 36','Sales Header','WRITE',1,1,'Codeunit 60002');
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
    assert result["process_summary"]["table_count"] == 1
    assert child["table_usage"][0]["usage"] == "WRITE"
    assert result["table_usage_summary"][0]["table_node"] == "Table 36"
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


def test_trace_injects_composed_var_effects_into_reached_if_assignment_contexts(tmp_path):
    parent = """OBJECT Codeunit 60001 Parent
{
  CODE
  {
    VAR
      Header@1 : Record 36;
      Middle@2 : Codeunit 60002;

    PROCEDURE Run@3();
    BEGIN
      Middle.Mutate(Header,TRUE);
      IF Header.Status = Header.Status::Released THEN
        MESSAGE('parent released');
    END;
  }
}"""
    middle = """OBJECT Codeunit 60002 Middle
{
  CODE
  {
    VAR
      Deep@1 : Codeunit 60003;

    PROCEDURE Mutate@2(VAR Header@3 : Record 36;DoMutate@4 : Boolean);
    BEGIN
      Deep.Apply(Header,TRUE);
      IF Header.Status = Header.Status::Released THEN
        MESSAGE('middle released');
    END;
  }
}"""
    deep = """OBJECT Codeunit 60003 Deep
{
  CODE
  {
    PROCEDURE Apply@1(VAR Header@2 : Record 36;DoSet@3 : Boolean);
    BEGIN
      IF DoSet THEN
        Header.Status := Header.Status::Released;
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
    (tmp_path / "parent.txt").write_text(parent, encoding="utf-8")
    (tmp_path / "middle.txt").write_text(middle, encoding="utf-8")
    (tmp_path / "deep.txt").write_text(deep, encoding="utf-8")
    (tmp_path / "table36.txt").write_text(table, encoding="utf-8")

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE objects(node TEXT PRIMARY KEY,type TEXT,id INT,name TEXT,origin TEXT,
            in_original INT,semantic_change INT,procedures INT,out_edges INT,in_edges INT);
        CREATE TABLE procedures(node TEXT PRIMARY KEY,object_node TEXT,name TEXT,line INT,is_local INT,origin TEXT);
        CREATE TABLE edges(src TEXT,dst TEXT,kind TEXT,count INT,new_vs_original INT,src_object TEXT,dst_object TEXT);
        CREATE TABLE table_usage(src TEXT,src_origin TEXT,table_node TEXT,table_name TEXT,usage TEXT,
            count INT,new_vs_original INT,src_object TEXT);
        INSERT INTO objects VALUES
            ('Codeunit 60001','Codeunit',60001,'Parent','CUSTOM',0,0,1,1,0),
            ('Codeunit 60002','Codeunit',60002,'Middle','CUSTOM',0,0,1,1,1),
            ('Codeunit 60003','Codeunit',60003,'Deep','CUSTOM',0,0,1,0,1);
        INSERT INTO procedures VALUES
            ('Codeunit 60001.Run','Codeunit 60001','Run',8,0,'CUSTOM'),
            ('Codeunit 60002.Mutate','Codeunit 60002','Mutate',8,0,'CUSTOM'),
            ('Codeunit 60003.Apply','Codeunit 60003','Apply',6,0,'CUSTOM');
        INSERT INTO edges VALUES
            ('Codeunit 60001.Run','Codeunit 60002.Mutate','CALL',1,1,'Codeunit 60001','Codeunit 60002'),
            ('Codeunit 60002.Mutate','Codeunit 60003.Apply','CALL',1,1,'Codeunit 60002','Codeunit 60003');
    """)
    symbols = sqlite3.connect(":memory:")
    symbols.execute("""CREATE TABLE symbols(kind TEXT,name TEXT,num INT,object_type TEXT,object_id INT,
                       object_name TEXT,detail TEXT,source_file TEXT,line INT,line_end INT)""")
    for object_id, name, filename, proc in [
        (60001, "Parent", "parent.txt", "Run"),
        (60002, "Middle", "middle.txt", "Mutate"),
        (60003, "Deep", "deep.txt", "Apply"),
    ]:
        symbols.execute("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?)",
                        ("procedure", proc, None, "Codeunit", object_id, name,
                         proc + "()", filename, 1, 20))

    result = trace_call_graph(
        db, "Codeunit 60001", [str(tmp_path)], symbols,
        max_depth=3, analyze_conditions=True, max_interprocedural_depth=2,
    )
    def find_if(value, condition_fragment):
        if isinstance(value, dict):
            if value.get("type") == "if" and condition_fragment in value.get("condition", ""):
                return value
            for child in value.values():
                found = find_if(child, condition_fragment) if isinstance(child, (dict, list)) else None
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find_if(child, condition_fragment)
                if found:
                    return found
        return None

    for node in ("Codeunit 60001.Run", "Codeunit 60002.Mutate"):
        procedure = next(item for item in result["procedures"] if item["node"] == node)
        analysis = procedure["condition_analysis"]
        assert analysis["interprocedural_call_effect_count"] >= 1
        condition = find_if(analysis["nodes"], "Header.Status")
        assert condition is not None
        incoming = condition["assignment_context"]["alternatives"][0]["known_assignments"]
        assert any(item["target"] == "Header.Status" for item in incoming)
        propagated = next(item for item in incoming if item["target"] == "Header.Status")
        assert propagated["semantic_assignment"]["target_resolution"]["resolution"] == "resolved"
        assert propagated["semantic_assignment"]["value_resolution"]["resolution"] == "resolved"


def test_trace_propagates_callee_var_record_filter_into_caller_lookup(tmp_path):
    parent = """OBJECT Codeunit 60001 Parent
{
  CODE
  {
    VAR
      Header@1 : Record 36;
      Child@2 : Codeunit 60002;

    PROCEDURE Run@3();
    BEGIN
      Child.Update(Header,TRUE);
      IF Header.FINDFIRST THEN
        MESSAGE('found');
    END;
  }
}"""
    child = """OBJECT Codeunit 60002 Child
{
  CODE
  {
    PROCEDURE Update@1(VAR Header@2 : Record 36;DoFilter@3 : Boolean);
    BEGIN
      IF DoFilter THEN
        Header.SETRANGE(Status,Header.Status::Released);
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
    (tmp_path / "parent.txt").write_text(parent, encoding="utf-8")
    (tmp_path / "child.txt").write_text(child, encoding="utf-8")
    (tmp_path / "table36.txt").write_text(table, encoding="utf-8")
    symbols = symbol_db()
    symbols.execute("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?)",
                    ("procedure", "Run", None, "Codeunit", 60001, "Parent",
                     "Run()", "parent.txt", 1, 20))
    result = trace_call_graph(
        graph_db(), "Codeunit 60001", [str(tmp_path)], symbols,
        max_depth=2, analyze_conditions=True,
    )
    parent_result = next(
        item for item in result["procedures"] if item["node"] == "Codeunit 60001.Run"
    )
    analysis = parent_result["condition_analysis"]
    filter_edge = result["interprocedural_filter_analysis"]["edges"][0]
    assert filter_edge["filter_summary"]["events"], filter_edge["filter_summary"]
    assert filter_edge["call_binding"]["call_sites"]
    assert filter_edge["call_binding"]["call_sites"][0]["arguments"][0]["type_match"] is True, filter_edge["call_binding"]
    assert filter_edge["caller_filter_effect_map"], filter_edge
    assert analysis["interprocedural_filter_effect_count"] == 1
    lookup = next(item for item in analysis["record_filter_analysis"]["lookups"]
                  if item["record_variable"] == "Header")
    assert len(lookup["active_filters"]) == 1
    active_filter = lookup["active_filters"][0]
    assert active_filter["field"] == "Status"
    assert active_filter["operation"] == "SETRANGE"
    assert active_filter["interprocedural"] is True
    assert active_filter["arguments"] == ["Header.Status::Released"]


def test_trace_composes_nested_record_filter_effects_through_two_call_hops(tmp_path):
    parent = """OBJECT Codeunit 60001 Parent
{
  CODE
  {
    VAR
      Header@1 : Record 36;
      Middle@2 : Codeunit 60002;

    PROCEDURE Run@3();
    BEGIN
      Middle.Update(Header);
      IF Header.FINDFIRST THEN
        MESSAGE('found');
    END;
  }
}"""
    middle = """OBJECT Codeunit 60002 Child
{
  CODE
  {
    VAR
      Deep@1 : Codeunit 60003;

    PROCEDURE Update@2(VAR Header@3 : Record 36);
    BEGIN
      Deep.Apply(Header);
    END;
  }
}"""
    deep = """OBJECT Codeunit 60003 Deep
{
  CODE
  {
    PROCEDURE Apply@1(VAR Header@2 : Record 36);
    BEGIN
      Header.SETRANGE(Status,Header.Status::Released);
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
    for name, content in (("parent.txt", parent), ("child.txt", middle),
                          ("deep.txt", deep), ("table36.txt", table)):
        (tmp_path / name).write_text(content, encoding="utf-8")

    db = graph_db()
    db.execute("UPDATE procedures SET name='Run',node='Codeunit 60001.Run' WHERE node='Codeunit 60001.Run'")
    db.execute("UPDATE procedures SET name='Update' WHERE node='Codeunit 60002.Update'")
    db.execute("INSERT INTO objects VALUES(?,?,?,?,?,?,?,?,?,?)",
               ("Codeunit 60003", "Codeunit", 60003, "Deep", "CUSTOM", 0, 0, 1, 0, 1))
    db.execute("INSERT INTO procedures VALUES(?,?,?,?,?,?)",
               ("Codeunit 60003.Apply", "Codeunit 60003", "Apply", 5, 0, "CUSTOM"))
    db.execute("DELETE FROM edges")
    db.executemany("INSERT INTO edges VALUES(?,?,?,?,?,?,?)", [
        ("Codeunit 60001.Run", "Codeunit 60002.Update", "CALL", 1, 1, "Codeunit 60001", "Codeunit 60002"),
        ("Codeunit 60002.Update", "Codeunit 60003.Apply", "CALL", 1, 1, "Codeunit 60002", "Codeunit 60003"),
    ])
    symbols = symbol_db()
    symbols.executemany("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?)", [
        ("procedure", "Run", None, "Codeunit", 60001, "Parent", "Run()", "parent.txt", 8, 13),
        ("procedure", "Apply", None, "Codeunit", 60003, "Deep", "Apply()", "deep.txt", 5, 8),
    ])
    result = trace_call_graph(
        db, "Codeunit 60001", [str(tmp_path)], symbols,
        max_depth=3, analyze_conditions=True, max_interprocedural_depth=2,
    )
    parent_result = next(p for p in result["procedures"]
                         if p["node"] == "Codeunit 60001.Run")
    lookup = next(x for x in parent_result["condition_analysis"]["record_filter_analysis"]["lookups"]
                  if x["record_variable"] == "Header")
    assert len(lookup["active_filters"]) == 1, lookup
    assert lookup["active_filters"][0]["field"] == "Status"
    assert lookup["active_filters"][0]["arguments"] == ["Header.Status::Released"]
    assert lookup["active_filters"][0]["interprocedural"] is True
    assert result["interprocedural_filter_analysis"]["propagated_hops"] >= 2
    assert result["interprocedural_filter_analysis"]["runtime_evaluated"] is False
