from nav_ai.intelligence import _analyze_caller_effect_flows


CALLER = """OBJECT Codeunit 50081 Caller
{
  CODE
  {
    PROCEDURE RunPosting();
    VAR
      CUBlockStocktake : Codeunit 50107;
    BEGIN
      CUBlockStocktake.BlockStocktakeSalesHeader(Rec, FALSE);
      IF Rec.Status = Rec.Status::Released THEN BEGIN
        MESSAGE('released');
      END;
    END;
  }
}"""


def test_callee_var_effect_is_visible_in_callers_following_if():
    flow = _analyze_caller_effect_flows(
        CALLER,
        "caller.txt",
        {
            9: [{
                "target": "Rec.Status",
                "expression": "Status::Released",
                "callee_line": 19,
                "callee_source_file": "callee.txt",
                "callee_parameter": "SalesHeader",
                "mapping": "var_record_field_argument",
                "path_specialization": "call_site_boolean_arguments",
                "runtime_evaluated": False,
            }]
        },
    )
    assert len(flow) == 1
    assert flow[0]["caller"] == "Codeunit 50081.RunPosting"
    nodes = flow[0]["assignment_flow_analysis"]["events"]
    propagated = [event for event in nodes if event.get("kind") == "interprocedural_var_mutation"]
    assert len(propagated) == 1
    assert propagated[0]["target"] == "Rec.Status"
    assert propagated[0]["expression"] == "Status::Released"
    assert propagated[0]["evaluated"] is False
    assert propagated[0]["interprocedural"] is True
    def find_if(nodes):
        for node in nodes:
            if node.get("type") == "if":
                return node
            found = find_if(node.get("children", [])) if node.get("type") == "block" else None
            if found:
                return found
        return None

    condition = find_if(flow[0]["control_flow_nodes"])
    assert condition is not None
    incoming = condition["assignment_context"]["alternatives"][0]["known_assignments"]
    assert any(item["target"] == "Rec.Status" for item in incoming)
