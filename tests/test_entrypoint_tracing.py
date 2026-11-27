import sqlite3

from nav_ai.entrypoint_tracing import trace_entrypoint_graph


def _graph():
    graph = sqlite3.connect(":memory:")
    graph.execute("CREATE TABLE objects(node TEXT PRIMARY KEY, type TEXT, id INTEGER, name TEXT)")
    graph.execute("CREATE TABLE procedures(node TEXT PRIMARY KEY, object_node TEXT)")
    graph.execute("CREATE TABLE edges(src TEXT, dst TEXT, kind TEXT)")
    graph.executemany(
        "INSERT INTO objects VALUES(?,?,?,?)",
        [("Page 50000", "Page", 50000, "Entry"), ("Codeunit 50001", "Codeunit", 50001, "Worker")],
    )
    graph.executemany(
        "INSERT INTO procedures VALUES(?,?)",
        [("Page 50000.OnAction", "Page 50000"), ("Codeunit 50001.RunWork", "Codeunit 50001")],
    )
    graph.executemany(
        "INSERT INTO edges VALUES(?,?,?)",
        [("Page 50000 TRIGGERS", "Page 50000.OnAction", "CALL"),
         ("Page 50000.OnAction", "Codeunit 50001.RunWork", "CALL"),
         ("Codeunit 50001.RunWork", "Missing Target", "CALL")],
    )
    return graph


def test_traces_entrypoint_object_call_paths_and_runobject_target():
    result = trace_entrypoint_graph(
        _graph(),
        [
            {"object": "Page 50000", "entry_kind": "page_action_trigger"},
            {"object": "Page 50000", "entry_kind": "object_launch_property", "target": "Page 42"},
        ],
    )

    assert result["traced_object_count"] == 1
    trace = result["traces"][0]
    assert trace["reachable_procedure_count"] == 2
    worker = next(item for item in trace["reachable_procedures"] if item["procedure"] == "Codeunit 50001.RunWork")
    assert worker["call_path"] == ["Page 50000.OnAction", "Codeunit 50001.RunWork"]
    assert trace["runobject_targets"] == [{
        "target": "Page 42", "indexed": False,
        "evidence": "RunObject_property", "runtime_invoked": False,
    }]
    assert trace["unresolved_call_targets"] == [
        {"source": "Codeunit 50001.RunWork", "target": "Missing Target"}
    ]
    assert result["semantics"]["runtime_executed"] is False


def test_unindexed_entrypoint_object_is_not_guessed():
    result = trace_entrypoint_graph(
        _graph(), [{"object": "Report 50002", "entry_kind": "report_trigger"}]
    )
    assert result["unindexed_object_count"] == 1
    assert result["traces"][0]["status"] == "object_not_indexed"
