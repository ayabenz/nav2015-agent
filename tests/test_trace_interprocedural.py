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


A_SOURCE = """OBJECT Codeunit 50010 A
{
  CODE
  {
    VAR
      Header@1 : Record 36;
      Middle@2 : Codeunit 50011;

    PROCEDURE Run@3();
    BEGIN
      Middle.Mutate(Header,TRUE);
    END;
  }
}"""

B_SOURCE = """OBJECT Codeunit 50011 B
{
  CODE
  {
    VAR
      Deep@1 : Codeunit 50012;

    PROCEDURE Mutate@2(VAR Header@3 : Record 36;DoMutate@4 : Boolean);
    BEGIN
      Deep.Apply(Header,TRUE);
    END;
  }
}"""

C_SOURCE = """OBJECT Codeunit 50012 C
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


def test_trace_composes_var_effects_across_two_call_hops():
    catalog = {
        ("codeunit", 50010): [_source(A_SOURCE, "a.txt", "Run")],
        ("codeunit", 50011): [_source(B_SOURCE, "b.txt", "Mutate")],
        ("codeunit", 50012): [_source(C_SOURCE, "c.txt", "Apply")],
    }
    result = analyze_trace_call_edges(
        [
            {"src": "Codeunit 50010.Run", "dst": "Codeunit 50011.Mutate"},
            {"src": "Codeunit 50011.Mutate", "dst": "Codeunit 50012.Apply"},
        ],
        catalog,
        max_call_depth=2,
    )
    assert result["propagated_hops"] == 2
    a_to_b = next(edge for edge in result["edges"]
                  if edge["src"] == "Codeunit 50010.Run")
    mapped = next(iter(a_to_b["caller_state_effect_map"].values()))[0]
    assert mapped["target"] == "Header.Status"
    assert mapped["runtime_evaluated"] is False
    b_summary = next(item["summary"] for item in result["procedure_summaries"]
                     if item["procedure"] == "Codeunit 50011.Mutate")
    mutations = b_summary["var_parameters"][0]["mutations"]
    assert any(item["target"] == "Header.Status" and item["interprocedural"]
               for item in mutations)


def test_trace_interprocedural_depth_zero_keeps_direct_effects_only():
    catalog = {
        ("codeunit", 50010): [_source(A_SOURCE, "a.txt", "Run")],
        ("codeunit", 50011): [_source(B_SOURCE, "b.txt", "Mutate")],
        ("codeunit", 50012): [_source(C_SOURCE, "c.txt", "Apply")],
    }
    result = analyze_trace_call_edges(
        [
            {"src": "Codeunit 50010.Run", "dst": "Codeunit 50011.Mutate"},
            {"src": "Codeunit 50011.Mutate", "dst": "Codeunit 50012.Apply"},
        ],
        catalog,
        max_call_depth=0,
    )
    a_to_b = next(edge for edge in result["edges"]
                  if edge["src"] == "Codeunit 50010.Run")
    assert a_to_b.get("caller_state_effect_map", {}) == {}
