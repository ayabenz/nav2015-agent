import sqlite3

from nav_ai.entrypoint_call_mapping import map_entrypoint_calls


def _graph():
    graph = sqlite3.connect(":memory:")
    graph.execute("CREATE TABLE objects(node TEXT PRIMARY KEY, type TEXT, id INTEGER, name TEXT)")
    graph.execute("CREATE TABLE procedures(node TEXT PRIMARY KEY, object_node TEXT, name TEXT)")
    graph.execute("CREATE TABLE edges(src TEXT, dst TEXT, kind TEXT)")
    graph.executemany(
        "INSERT INTO objects VALUES(?,?,?,?)",
        [
            ("Page 50000", "Page", 50000, "Entry"),
            ("Codeunit 50001", "Codeunit", 50001, "Worker"),
        ],
    )
    graph.executemany(
        "INSERT INTO procedures VALUES(?,?,?)",
        [
            ("Page 50000.DoPost", "Page 50000", "DoPost"),
            ("Page 50000.DoPreview", "Page 50000", "DoPreview"),
            ("Codeunit 50001.RunWork", "Codeunit 50001", "RunWork"),
        ],
    )
    graph.executemany(
        "INSERT INTO edges VALUES(?,?,?)",
        [
            ("Codeunit 50001.RunWork", "Missing Target", "CALL"),
        ],
    )
    return graph


def test_maps_local_action_call_and_traverses_only_its_procedure_root():
    result = map_entrypoint_calls(
        _graph(),
        {
            "entries": [
                {
                    "entry_id": "Page 50000.Action[10].OnAction",
                    "object": "Page 50000",
                    "entry_kind": "page_action_body",
                    "line_start": 10,
                    "line_end": 12,
                    "body": "BEGIN DoPost; END;",
                },
                {
                    "entry_id": "Page 50000.Action[20].OnAction",
                    "object": "Page 50000",
                    "entry_kind": "page_action_body",
                    "line_start": 20,
                    "line_end": 22,
                    "body": "BEGIN DoPreview; END;",
                },
            ]
        },
    )

    post, preview = result["entries"]
    assert post["direct_targets"][0]["target"] == "Page 50000.DoPost"
    assert [item["node"] for item in post["reachable_procedures"]] == ["Page 50000.DoPost"]
    assert preview["direct_targets"][0]["target"] == "Page 50000.DoPreview"
    assert [item["node"] for item in preview["reachable_procedures"]] == ["Page 50000.DoPreview"]
    assert result["semantics"]["runtime_executed"] is False


def test_resolves_explicit_codeunit_run_by_numeric_object_id():
    result = map_entrypoint_calls(
        _graph(),
        {
            "entries": [{
                "entry_id": "Page 50000.Action[10].OnAction",
                "object": "Page 50000",
                "entry_kind": "page_action_body",
                "body": "CODEUNIT.RUN(50001);",
                "line_start": 1,
                "line_end": 1,
            }]
        },
    )
    entry = result["entries"][0]
    assert entry["direct_targets"] == [{
        "target": "Codeunit 50001",
        "kind": "explicit_run_object",
        "confidence": "explicit_object_reference",
    }]
    assert entry["reachable_procedures"] == []

def test_ignores_procedure_names_inside_comments_and_string_literals():
    result = map_entrypoint_calls(
        _graph(),
        {
            "entries": [{
                "entry_id": "Page 50000.Action[30].OnAction",
                "object": "Page 50000",
                "entry_kind": "page_action_body",
                "body": "// DoPost;\nMESSAGE('DoPreview;');",
                "line_start": 1,
                "line_end": 2,
            }]
        },
    )
    assert result["entries"][0]["direct_targets"] == []

