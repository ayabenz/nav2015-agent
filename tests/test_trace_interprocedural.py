from nav_ai.trace_interprocedural import analyze_trace_call_edges


CALLER = """OBJECT Codeunit 50000 Caller
{
  CODE
  {
    VAR
      SalesHeader@1 : Record 36;
      Mutator@2 : Codeunit 50107;

    PROCEDURE Run@3();
    BEGIN
      Mutator.UpdateHeader(SalesHeader,TRUE);
    END;
  }
}"""

CALLEE = """OBJECT Codeunit 50107 Mutator
{
  CODE
  {
    PROCEDURE UpdateHeader@1(VAR SalesHeader@1000 : Record 36;DoUpdate@1002 : Boolean);
    BEGIN
      IF DoUpdate THEN
        SalesHeader.Status := SalesHeader.Status::Released;
    END;
  }
}"""


def _source(text, path, procedure):
    from nav_ai.parser import parse_nav_text
    parsed = parse_nav_text(text, path)
    return {
        "status": "resolved",
        "source_path": path,
        "source_label": path,
        "object_name": parsed["object"]["name"],
        "raw_block": text,
        "procedures": {procedure.casefold(): {"name": procedure}},
    }


def test_trace_edges_bind_direct_call_and_report_boolean_specialized_var_effect():
    catalog = {
        ("codeunit", 50000): [_source(CALLER, "caller.txt", "Run")],
        ("codeunit", 50107): [_source(CALLEE, "callee.txt", "UpdateHeader")],
    }
    result = analyze_trace_call_edges(
        [{"src": "Codeunit 50000.Run", "dst": "Codeunit 50107.UpdateHeader"}],
        catalog,
    )
    assert result["edge_count"] == 1
    edge = result["edges"][0]
    assert edge["status"] == "analyzed"
    assert edge["call_binding"]["call_sites"]
    effects = edge["caller_state_effect_map"]
    assert effects
    mapped = next(iter(effects.values()))[0]
    assert mapped["target"] == "SalesHeader.Status"
    assert mapped["path_specialization"] == "call_site_boolean_arguments"
    assert mapped["runtime_evaluated"] is False


def test_trace_edge_keeps_missing_source_explicit():
    result = analyze_trace_call_edges(
        [{"src": "Codeunit 50000.Run", "dst": "Codeunit 50107.UpdateHeader"}],
        {},
    )
    assert result["edges"][0]["status"] == "source_unavailable"
    assert result["runtime_evaluated"] is False
