from nav_ai.control_flow import analyze_control_flow
from nav_ai.record_filters import analyze_record_filter_paths
from nav_ai.semantic_conditions import parse_record_variables, parse_table_metadata


TABLE = """OBJECT Table 50063 Setting Blocked Stocktake
{
  FIELDS
  {
    { 5 ; ; Start Date ; DateTime }
    { 7 ; ; Jenis Transaksi ; Option }
    {
      OptionString=IN,OUT,ALL;
    }
    { 11 ; ; Block Type ; Option }
    {
      OptionString=Item,Product Group,Item Category;
    }
  }
}
"""


def _analyze(code):
    table = parse_table_metadata(TABLE, "Table_50063.txt")
    variables = parse_record_variables("StocktakeRule : Record 50063;")
    flow = analyze_control_flow(code, object_type="Codeunit", object_id=50107,
                                procedure="TestStocktake", source_file="Codeunit50107.txt")
    return analyze_record_filter_paths(flow["nodes"], variables, {50063: table})


def test_findfirst_captures_active_setrange_filters():
    result = _analyze("""BEGIN
  StocktakeRule.SETRANGE("Jenis Transaksi", TransactionType);
  StocktakeRule.SETRANGE("Block Type", StocktakeRule."Block Type"::Item);
  IF StocktakeRule.FINDFIRST THEN
    ERROR('Blocked');
END;
""")

    assert len(result["lookups"]) == 1
    lookup = result["lookups"][0]
    assert lookup["record_variable"] == "StocktakeRule"
    assert lookup["filter_state"] == "path_specific"
    assert lookup["runtime_evaluated"] is False
    assert [item["field"] for item in lookup["active_filters"]] == [
        "Jenis Transaksi", "Block Type"
    ]
    assert lookup["result"] == "unknown_static"


def test_filters_inside_if_are_kept_as_separate_possible_paths():
    result = _analyze("""BEGIN
  IF IsInbound THEN
    StocktakeRule.SETRANGE("Jenis Transaksi", 'IN')
  ELSE
    StocktakeRule.SETRANGE("Jenis Transaksi", 'OUT');
  IF StocktakeRule.FINDFIRST THEN
    ERROR('Blocked');
END;
""")

    lookups = result["lookups"]
    assert len(lookups) == 2
    values = {
        lookup["active_filters"][0]["arguments"][0]
        for lookup in lookups
    }
    assert values == {"'IN'", "'OUT'"}
    assert {lookup["path_conditions"][0]["outcome"] for lookup in lookups} == {
        True, False
    }


def test_reset_clears_filters_before_next_lookup():
    result = _analyze("""BEGIN
  StocktakeRule.SETRANGE("Jenis Transaksi", 'IN');
  StocktakeRule.RESET;
  IF StocktakeRule.FINDFIRST THEN
    ERROR('Blocked');
END;
""")

    assert len(result["lookups"]) == 1
    assert result["lookups"][0]["active_filters"] == []
