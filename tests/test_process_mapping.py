import sqlite3

import pytest

from nav_ai.process_mapping import map_candidate_processes


def graph_db():
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
            ('Page 42','Page',42,'Sales Order','MODIFIED_STANDARD',1,1,1,1,0),
            ('Codeunit 60001','Codeunit',60001,'Sales Import','CUSTOM',0,1,1,0,1),
            ('Report 60002','Report',60002,'Sales Report','CUSTOM',0,1,1,0,0),
            ('Page 43','Page',43,'Lookup','STANDARD_UNCHANGED',1,0,1,0,0);
        INSERT INTO procedures VALUES
            ('Page 42.OnOpen','Page 42','OnOpen',1,0,'MODIFIED_STANDARD'),
            ('Codeunit 60001.Run','Codeunit 60001','Run',1,0,'CUSTOM'),
            ('Codeunit 60001.Write','Codeunit 60001','Write',2,0,'CUSTOM'),
            ('Report 60002.OnPreReport','Report 60002','OnPreReport',1,0,'CUSTOM'),
            ('Page 43.OnOpen','Page 43','OnOpen',1,0,'STANDARD_UNCHANGED');
        INSERT INTO edges VALUES
            ('Page 42.OnOpen','Codeunit 60001.Run','CALL',1,1,'Page 42','Codeunit 60001'),
            ('Codeunit 60001.Run','Codeunit 60001.Write','CALL',1,1,'Codeunit 60001','Codeunit 60001');
        INSERT INTO table_usage VALUES
            ('Page 42.OnOpen','MODIFIED_STANDARD','Table 36','Sales Header','READ',3,0,'Page 42'),
            ('Codeunit 60001.Write','CUSTOM','Table 36','Sales Header','WRITE',4,1,'Codeunit 60001'),
            ('Codeunit 60001.Write','CUSTOM','Table 37','Sales Line','WRITE',2,1,'Codeunit 60001'),
            ('Report 60002.OnPreReport','CUSTOM','Table 36','Sales Header','READ',1,0,'Report 60002');
    """)
    return db


def test_mapping_groups_candidates_using_transitive_call_reachable_tables():
    result = map_candidate_processes(graph_db())
    assert result["candidate_count"] == 3
    assert result["cluster_count"] == 1
    assert set(result["clusters"][0]["members"]) == {
        "Page 42", "Codeunit 60001", "Report 60002"
    }
    page = next(item for item in result["candidates"] if item["object"] == "Page 42")
    assert page["table_ids"] == ["Table 36", "Table 37"]
    assert page["reachable_procedure_count"] == 3
    assert page["reachable_procedures"][1]["call_path"] == [
        "Page 42.OnOpen", "Codeunit 60001.Run"
    ]
    pair = next(item for item in result["similarities"]
                if item["left"] == "Page 42" and item["right"] == "Codeunit 60001")
    assert pair["shared_tables"] == ["Table 36", "Table 37"]
    assert pair["runtime_executed"] is False


def test_mapping_excludes_unchanged_standard_and_keeps_runtime_claims_false():
    result = map_candidate_processes(graph_db(), limit=10)
    assert all("Page 43" not in cluster["members"] for cluster in result["clusters"])
    assert result["semantics"]["runtime_evaluated"] is False
    assert "dynamic RUN targets" in " ".join(result["semantics"]["limitations"])


def test_mapping_validates_similarity_and_traversal_limits():
    with pytest.raises(ValueError, match="min_similarity"):
        map_candidate_processes(graph_db(), min_similarity=0)
    with pytest.raises(ValueError, match="max_depth"):
        map_candidate_processes(graph_db(), max_depth=-1)
    with pytest.raises(ValueError, match="max_nodes"):
        map_candidate_processes(graph_db(), max_nodes_per_candidate=0)


def test_mapping_reports_depth_truncation_and_unresolved_call_targets():
    db = graph_db()
    db.execute("INSERT INTO edges VALUES(?,?,?,?,?,?,?)", (
        "Codeunit 60001.Write", "Codeunit 99999", "CALL", 1, 1,
        "Codeunit 60001", "Codeunit 99999",
    ))
    result = map_candidate_processes(db, max_depth=2)
    page = next(item for item in result["candidates"] if item["object"] == "Page 42")
    assert page["unresolved_call_targets"] == [{
        "src": "Codeunit 60001.Write",
        "dst": "Codeunit 99999",
        "reason": "CALL target is not an indexed procedure",
    }]
    assert page["reachable_procedure_count"] == 2
