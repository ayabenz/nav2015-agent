import sqlite3

from nav_ai.entrypoint_extended import discover_extended_entrypoints


def _graph():
    graph = sqlite3.connect(":memory:")
    graph.execute("CREATE TABLE objects(node TEXT PRIMARY KEY, type TEXT, id INTEGER, name TEXT)")
    graph.execute("CREATE TABLE procedures(node TEXT PRIMARY KEY, object_node TEXT, name TEXT)")
    graph.execute("CREATE TABLE edges(src TEXT, dst TEXT, kind TEXT)")
    graph.executemany("INSERT INTO objects VALUES(?,?,?,?)", [
        ("Codeunit 50001", "Codeunit", 50001, "Worker"),
        ("Codeunit 50002", "Codeunit", 50002, "Subscriber"),
        ("Codeunit 50003", "Codeunit", 50003, "Caller"),
    ])
    graph.executemany("INSERT INTO procedures VALUES(?,?,?)", [
        ("Codeunit 50001.DoWork", "Codeunit 50001", "DoWork"),
        ("Codeunit 50001.OnAfterPost", "Codeunit 50001", "OnAfterPost"),
        ("Codeunit 50003.RaiseEvent", "Codeunit 50003", "RaiseEvent"),
    ])
    graph.execute("INSERT INTO edges VALUES(?,?,?)", ("Codeunit 50003.RaiseEvent", "Codeunit 50001.OnAfterPost", "CALL"))
    return graph


def test_resolves_typed_codeunit_variable_method_call(tmp_path):
    source = tmp_path / "typed.txt"
    source.write_text("""OBJECT Codeunit 50002 Subscriber
  CODE
    VAR
      Worker : Codeunit 50001;
    BEGIN
      Worker.DoWork;
    END;
""", encoding="utf-8")
    result = discover_extended_entrypoints([str(source)], _graph())
    assert result["typed_variable_calls"][0]["target_procedure"] == "Codeunit 50001.DoWork"


def test_finds_event_subscriber_declaration(tmp_path):
    source = tmp_path / "subscriber.txt"
    source.write_text("""OBJECT Codeunit 50002 Subscriber
  CODE
    [EventSubscriber(ObjectType::Codeunit, Codeunit::50001, 'OnAfterPost', '', false, false)]
    LOCAL PROCEDURE HandleEvent()
    BEGIN
    END;
""", encoding="utf-8")
    result = discover_extended_entrypoints([str(source)], _graph())
    assert result["event_subscribers"][0]["event_name"] == "OnAfterPost"
    assert result["event_subscribers"][0]["event_object_id"] == 50001


def test_extracts_individual_table_field_onvalidate(tmp_path):
    source = tmp_path / "table.txt"
    source.write_text("""OBJECT Table 50010 Demo
  FIELDS
    { 1 ;   ;Status;Option ; OnValidate=BEGIN
                         MESSAGE('changed');
                       END;
    }
  CODE
""", encoding="utf-8")
    result = discover_extended_entrypoints([str(source)])
    trigger = result["table_field_triggers"][0]
    assert trigger["field_id"] == 1
    assert trigger["field_name"] == "Status"
    assert trigger["trigger"] == "OnValidate"



def test_maps_job_queue_configuration_snapshot_without_claiming_execution():
    from nav_ai.entrypoint_extended import map_job_queue_snapshot

    result = map_job_queue_snapshot({
        "snapshot_at": "2026-11-27T10:00:00+07:00",
        "company": "PT DATASCRIP",
        "entries": [{
            "entry_no": "JOB-001", "object_type": "Codeunit", "object_id": 50001,
            "status": "Ready", "parameter_string": "sensitive-value",
            "recurring": True,
        }],
    }, _graph())
    entry = result["entries"][0]
    assert entry["target_object"] == "Codeunit 50001"
    assert entry["parameter_string_present"] is True
    assert "sensitive-value" not in str(result)
    assert entry["runtime_executed"] is False



def test_resolves_typed_variables_from_nonfinal_procedure_scope(tmp_path):
    source = tmp_path / "scoped.txt"
    source.write_text("""OBJECT Codeunit 50002 Subscriber
  CODE
    LOCAL PROCEDURE First()
    VAR
      Worker : Codeunit 50001;
    BEGIN
      Worker.DoWork;
    END;

    LOCAL PROCEDURE Second()
    VAR
      Another : Codeunit 50002;
    BEGIN
    END;
""", encoding="utf-8")
    result = discover_extended_entrypoints([str(source)], _graph())
    assert any(item["method"] == "DoWork" and item["target_procedure"] == "Codeunit 50001.DoWork"
               for item in result["typed_variable_calls"])



def test_links_event_subscriber_to_publisher_declaration(tmp_path):
    publisher = tmp_path / "publisher.txt"
    publisher.write_text("""OBJECT Codeunit 50001 Worker
  CODE
    [IntegrationEvent(false, false)]
    LOCAL PROCEDURE OnAfterPost()
    BEGIN
    END;
""", encoding="utf-8")
    subscriber = tmp_path / "subscriber.txt"
    subscriber.write_text("""OBJECT Codeunit 50002 Subscriber
  CODE
    [EventSubscriber(ObjectType::Codeunit, Codeunit::50001, 'OnAfterPost', '', false, false)]
    LOCAL PROCEDURE HandleEvent()
    BEGIN
    END;
""", encoding="utf-8")
    result = discover_extended_entrypoints([str(publisher), str(subscriber)], _graph())
    event = result["event_subscribers"][0]
    assert event["publisher_declaration_found"] is True
    assert event["publisher_matches"][0]["publisher_object"] == "Codeunit 50001"
    assert event["publisher_invocation_proven"] is False
    assert event["publisher_matches"][0]["static_callers"] == ["Codeunit 50003.RaiseEvent"]



def test_dynamic_run_with_conflicting_assignments_stays_unresolved(tmp_path):
    source = tmp_path / "dynamic.txt"
    source.write_text("""OBJECT Codeunit 50002 Subscriber
  CODE
    VAR
      RunID : Integer;
    BEGIN
      RunID := 50001;
      IF UseOther THEN
        RunID := 50002;
      CODEUNIT.RUN(RunID);
    END;
""", encoding="utf-8")
    result = discover_extended_entrypoints([str(source)], _graph())
    assert result["dynamic_run_targets"][0]["resolved_target"] is None
    assert result["dynamic_run_targets"][0]["resolution_evidence"] == "unresolved_dynamic_run"


def test_resolves_named_codeunit_run_target(tmp_path):
    source = tmp_path / "named_run.txt"
    source.write_text("""OBJECT Codeunit 50002 Subscriber
  CODE
    BEGIN
      CODEUNIT.RUN(CODEUNIT::"Worker");
    END;
""", encoding="utf-8")
    result = discover_extended_entrypoints([str(source)], _graph())
    assert result["dynamic_run_targets"][0]["resolved_target"] == "Codeunit 50001"
