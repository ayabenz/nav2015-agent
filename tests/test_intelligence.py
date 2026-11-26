from __future__ import annotations

import sqlite3

from nav_ai.intelligence import graph_neighbors, impact, object_detail, procedure_detail, symbol_search, table_usage


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
            ('Codeunit 80','Codeunit',80,'Sales-Post','MODIFIED_STANDARD',1,1,2,1,1),
            ('Codeunit 50081','Codeunit',50081,'Return Receive','CUSTOM',0,0,1,1,0),
            ('Table 36','Table',36,'Sales Header','STANDARD_UNCHANGED',1,0,0,0,1);
        INSERT INTO procedures VALUES
            ('Codeunit 80.PostItemJnlLine','Codeunit 80','PostItemJnlLine',100,0,'CHANGED'),
            ('Codeunit 50081.Receive','Codeunit 50081','Receive',20,0,'CUSTOM');
        INSERT INTO edges VALUES
            ('Codeunit 50081.Receive','Codeunit 80.PostItemJnlLine','CALL',1,1,'Codeunit 50081','Codeunit 80'),
            ('Codeunit 80.PostItemJnlLine','Table 36','VAR',1,0,'Codeunit 80','Table 36');
        INSERT INTO table_usage VALUES
            ('Codeunit 80.PostItemJnlLine','CHANGED','Table 36','Sales Header','READ',2,1,'Codeunit 80');
    """)
    return db


def test_impact_follows_call_edges_only_by_default():
    db = graph_db()
    assert impact(db, "Codeunit 80.PostItemJnlLine") == ["Codeunit 50081.Receive"]


def test_direct_callers_and_procedure_detail():
    db = graph_db()
    rows = graph_neighbors(db, "Codeunit 80.PostItemJnlLine", "callers")
    assert rows[0]["node"] == "Codeunit 50081.Receive"
    detail = procedure_detail(db, "Codeunit 80.PostItemJnlLine")
    assert detail["origin"] == "CHANGED"
    assert detail["callers"][0]["src"] == "Codeunit 50081.Receive"


def test_object_detail_includes_procedures_and_table_usage():
    db = graph_db()
    detail = object_detail(db, "Codeunit 80")
    assert detail["name"] == "Sales-Post"
    assert detail["top_procedures"][0]["name"] == "PostItemJnlLine"
    assert detail["table_usage"][0]["table_node"] == "Table 36"


def test_table_usage_can_filter_read_write_kind():
    db = graph_db()
    assert len(table_usage(db, "Table 36", "READ")) == 1
    assert table_usage(db, "Table 36", "WRITE") == []


def test_symbol_search_returns_source_location():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE symbols(kind TEXT,name TEXT,num INT,object_type TEXT,object_id INT,
                  object_name TEXT,detail TEXT,source_file TEXT,line INT,line_end INT)""")
    db.execute("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?)",
               ("procedure", "PostItemJnlLine", None, "Codeunit", 80, "Sales-Post",
                "PostItemJnlLine()", "CU80.txt", 120, 180))
    rows = symbol_search(db, ["postitemjnlline"])
    assert rows[0]["source_file"] == "CU80.txt"
    assert rows[0]["line"] == 120
