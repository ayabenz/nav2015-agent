import sqlite3

import pytest

from nav_ai.process_discovery import discover_process_entrypoints


def graph_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE objects(node TEXT,type TEXT,id INT,name TEXT,origin TEXT,
            in_original INT,semantic_change INT,procedures INT,out_edges INT,in_edges INT);
        INSERT INTO objects VALUES
            ('Page 42','Page',42,'Sales Order','MODIFIED_STANDARD',1,1,12,8,0),
            ('Codeunit 60001','Codeunit',60001,'Custom Import','CUSTOM',0,1,4,5,1),
            ('Table 36','Table',36,'Sales Header','STANDARD_UNCHANGED',1,0,0,0,20),
            ('Report 60002','Report',60002,'Custom Report','CUSTOM',0,1,2,0,0),
            ('Page 43','Page',43,'Standard Lookup','STANDARD_UNCHANGED',1,0,3,0,0);
    """)
    return db


def test_discovery_ranks_company_objects_and_excludes_unchanged_standard():
    result = discover_process_entrypoints(graph_db())
    assert result["candidate_count"] == 3
    assert all(item["origin"] != "STANDARD_UNCHANGED" for item in result["candidates"])
    assert result["candidates"][0]["object"] == "Page 42"
    assert result["candidates"][0]["confidence"] == "heuristic_candidate"
    assert result["semantics"]["runtime_evaluated"] is False


def test_discovery_can_include_standard_and_respects_limit():
    result = discover_process_entrypoints(graph_db(), limit=2, include_standard=True)
    assert result["candidate_count"] == 4
    assert result["returned_count"] == 2


def test_discovery_rejects_nonpositive_limit():
    with pytest.raises(ValueError, match="limit"):
        discover_process_entrypoints(graph_db(), limit=0)
