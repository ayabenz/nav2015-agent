from nav_ai.interprocedural import analyze_direct_call_bindings

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
