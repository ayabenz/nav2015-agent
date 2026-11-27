from nav_ai.interprocedural import (analyze_direct_call_bindings, build_caller_var_effect_map,
                                    annotate_callsite_boolean_branches)

CALLEE = """OBJECT Codeunit 50107 Block Stocktake
{
  CODE
  {
    PROCEDURE BlockStocktakeSalesHeader@1(SalesHeader@1003 : Record 36;CreateWhseShipment@1000 : Boolean);
    BEGIN
      IF SalesHeader."No." <> '' THEN;
    END;
  }
}"""

CALLER = """OBJECT Codeunit 50081 Sales-Post (Y/N) Ship
{
  PROPERTIES
  {
    TableNo=36;
    OnRun=VAR
            CUBlockStocktake@1000 : Codeunit 50107;
          BEGIN
            CUBlockStocktake.BlockStocktakeSalesHeader(Rec, FALSE);
          END;
  }
  CODE
  {
  }
}"""


def test_direct_call_binds_record_rec_and_boolean_argument():
    result = analyze_direct_call_bindings(
        CALLER, CALLEE, "BlockStocktakeSalesHeader", "caller.txt", "callee.txt"
    )
    assert len(result["call_sites"]) == 1
    args = result["call_sites"][0]["arguments"]
    assert args[0]["parameter"] == "SalesHeader"
    assert args[0]["argument"] == "Rec"
    assert args[0]["argument_record_type"] == "Table 36"
    assert args[0]["type_match"] is True
    assert args[1]["argument"] == "FALSE"
    assert args[1]["type_match"] == "compatible_literal"
    assert args[1]["by_reference"] is False


def test_ignores_commented_call_sites():
    caller = CALLER.replace(
        "CUBlockStocktake.BlockStocktakeSalesHeader(Rec, FALSE);",
        "// CUBlockStocktake.BlockStocktakeSalesHeader(Rec, FALSE);"
    )
    result = analyze_direct_call_bindings(
        caller, CALLEE, "BlockStocktakeSalesHeader", "caller.txt", "callee.txt"
    )
    assert result["call_sites"] == []


def test_does_not_bind_same_named_method_on_wrong_codeunit():
    caller = CALLER.replace(
        "CUBlockStocktake@1000 : Codeunit 50107;",
        "CUBlockStocktake@1000 : Codeunit 80;"
    )
    result = analyze_direct_call_bindings(
        caller, CALLEE, "BlockStocktakeSalesHeader", "caller.txt", "callee.txt"
    )
    assert result["call_sites"] == []



def test_maps_only_unconditional_var_mutations_to_caller_state():
    binding = {
        "call_sites": [{
            "line": 12,
            "var_parameter_effects": [{
                "parameter": "SalesHeader",
                "caller_argument": "Rec",
                "mutations": [
                    {"target": "SalesHeader.Status", "expression": "Status::Released",
                     "line": 8, "source_file": "callee.txt", "path": []},
                    {"target": "SalesHeader.Blocked", "expression": "TRUE",
                     "line": 10, "source_file": "callee.txt",
                     "path": [{"if": "DoBlock", "outcome": True}]},
                ],
            }],
        }],
    }
    mapped = build_caller_var_effect_map(binding)
    assert len(mapped[12]) == 1
    assert mapped[12][0]["target"] == "Rec.Status"
    assert mapped[12][0]["mapping"] == "var_record_field_argument"


def test_does_not_map_complex_var_argument_expression():
    binding = {
        "call_sites": [{
            "line": 4,
            "var_parameter_effects": [{
                "parameter": "Status",
                "caller_argument": "GetStatus()",
                "mutations": [{"target": "Status", "expression": "'Released'", "path": []}],
            }],
        }],
    }
    assert build_caller_var_effect_map(binding) == {}



def test_boolean_literal_call_specializes_matching_if_branch():
    nodes = [{
        "type": "if",
        "condition": "CreateWhseShipment",
        "true_branch": {"type": "statement", "source": "CreateShipment;"},
        "false_branch": {"type": "statement", "source": "NormalShip;"},
    }]
    binding = {
        "call_sites": [{
            "caller_object": "Codeunit 50081",
            "source_file": "caller.txt",
            "line": 14,
            "arguments": [{
                "parameter": "CreateWhseShipment",
                "formal_type": "Boolean",
                "argument": "FALSE",
                "type_match": "compatible_literal",
            }],
        }],
    }
    annotate_callsite_boolean_branches(nodes, binding)
    annotation = nodes[0]["call_site_specializations"][0]
    assert annotation["compatible_if_outcome"] is False
    assert annotation["incompatible_if_outcome"] is True
    assert annotation["actual_argument"] == "FALSE"
    assert annotation["runtime_evaluated"] is False


def test_boolean_specialization_does_not_guess_complex_condition():
    nodes = [{"type": "if", "condition": "CreateWhseShipment OR IsPreview"}]
    binding = {"call_sites": [{
        "arguments": [{
            "parameter": "CreateWhseShipment", "formal_type": "Boolean",
            "argument": "FALSE", "type_match": "compatible_literal",
        }],
    }]}
    annotate_callsite_boolean_branches(nodes, binding)
    assert "call_site_specializations" not in nodes[0]



def test_datascrip_style_false_argument_selects_else_path():
    callee = CALLEE.replace(
        "IF SalesHeader.",
        "IF CreateWhseShipment THEN CreateShipment;\\n      IF SalesHeader.",
    )
    binding = analyze_direct_call_bindings(CALLER, callee, "BlockStocktakeSalesHeader")
    nodes = [{"type": "if", "condition": "CreateWhseShipment"}]
    annotate_callsite_boolean_branches(nodes, binding)
    annotation = nodes[0]["call_site_specializations"][0]
    assert annotation["actual_argument"] == "FALSE"
    assert annotation["compatible_if_outcome"] is False
