import sqlite3

import pytest

from nav_ai.process_mapping import map_candidate_processes


def graph_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE objects(node TEXT,type TEXT,id INT,name TEXT,origin TEXT,
            in_original INT,semantic_change INT,procedures INT,out_edges INT,in_edges INT);
        CREATE TABLE table_usage(src_object TEXT,table_node TEXT,table_name TEXT,
            usage TEXT,count INT,new_vs_original INT);
        INSERT INTO objects VALUES
            ('Page 42','Page',42,'Sales Order','MODIFIED_STANDARD',1,1,12,8,0),
            ('Codeunit 60001','Codeunit',60001,'Sales Import','CUSTOM',0,1,4,5,1),
            ('Report 60002','Report',60002,'Sales Report','CUSTOM',0,1,2,0,0),
            ('Page 43','Page',43,'Lookup','STANDARD_UNCHANGED',1,0,3,0,0);
        INSERT INTO table_usage VALUES
            ('Page 42','Table 36','Sales Header','READ',3,0),
            ('Page 42','Table 37','Sales Line','READ',2,0),
            ('Codeunit 60001','Table 36','Sales Header','WRITE',4,1),
            ('Codeunit 60001','Table 37','Sales Line','WRITE',2,1),
            ('Report 60002','Table 36','Sales Header','READ',1,0);
    """)
    return db


def test_mapping_groups_candidates_with_overlapping_direct_tables():
    result = map_candidate_processes(graph_db())
    assert result["candidate_count"] == 3
    assert result["cluster_count"] == 1
    assert set(result["clusters"][0]["members"]) == {
        "Page 42", "Codeunit 60001", "Report 60002"
    }
    pair = next(item for item in result["similarities"]
                if item["left"] == "Page 42" and item["right"] == "Codeunit 60001")
    assert pair["shared_tables"] == ["Table 36", "Table 37"]
    assert pair["runtime_executed"] is False


def test_mapping_excludes_unchanged_standard_and_preserves_unclustered_candidates():
    result = map_candidate_processes(graph_db(), limit=10)
    assert all("Page 43" not in cluster["members"] for cluster in result["clusters"])
    assert result["semantics"]["runtime_evaluated"] is False


def test_mapping_validates_similarity_threshold():
    with pytest.raises(ValueError, match="min_similarity"):
        map_candidate_processes(graph_db(), min_similarity=0)
