import sqlite3

from nav_ai.entrypoint_extended import discover_extended_entrypoints


def _graph():
    graph = sqlite3.connect(":memory:")
    graph.execute("CREATE TABLE objects(node TEXT PRIMARY KEY, type TEXT, id INTEGER, name TEXT)")
    graph.execute("CREATE TABLE procedures(node TEXT PRIMARY KEY, object_node TEXT, name TEXT)")
    graph.executemany("INSERT INTO objects VALUES(?,?,?,?)", [
        ("Codeunit 50001", "Codeunit", 50001, "Worker"),
        ("Codeunit 50002", "Codeunit", 50002, "Subscriber"),
    ])
    graph.execute("INSERT INTO procedures VALUES(?,?,?)", ("Codeunit 50001.DoWork", "Codeunit 50001", "DoWork"))
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
