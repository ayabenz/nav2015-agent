from nav_ai.record_filters import analyze_record_filters, annotate_record_lookup_conditions
from nav_ai.semantic_conditions import parse_record_variables, parse_table_metadata


TABLE = """OBJECT Table 50063 Setting Blocked Stocktake
{
  FIELDS
  {
    { 5 ; ; Start Date ; DateTime }
    { 6 ; ; End Date ; DateTime }
    { 7 ; ; Jenis Transaksi ; Option ; OptionString=IN,OUT,ALL }
  }
}
"""


def test_setfilter_and_setrange_accumulate_until_findfirst():
    source = """tblStocktake.RESET;
tblStocktake.SETFILTER("Start Date", '<=%1', CURRENTDATETIME);
tblStocktake.SETFILTER("End Date", '>=%1', CURRENTDATETIME);
tblStocktake.SETFILTER("Jenis Transaksi", 'OUT|ALL');
IF tblStocktake.FINDFIRST THEN
  DoSomething;"""
    table = parse_table_metadata(TABLE, "Table_50063.txt")
    variables = parse_record_variables("tblStocktake@1002 : Record 50063;")
    result = analyze_record_filters(source, variables, {50063: table}, "Codeunit_50107.txt")
    lookup = result["lookups"][0]
    assert lookup["operation"] == "FINDFIRST"
    assert [item["field"] for item in lookup["active_filters"]] == [
        "Start Date", "End Date", "Jenis Transaksi"
    ]
    assert lookup["active_filters"][0]["arguments"] == ["'<=%1'", "CURRENTDATETIME"]
    assert lookup["filter_state"] == "branch_ambiguous"
    assert result["runtime_evaluated"] is False


def test_setrange_without_values_clears_only_that_field():
    source = """R.SETRANGE("Document No.", 'SO-1');
R.SETRANGE("Document No.");
R.SETRANGE("Document Type", 1);
R.FINDFIRST;"""
    result = analyze_record_filters(source, {}, {})
    lookup = result["lookups"][0]
    assert [item["field"] for item in lookup["active_filters"]] == ["Document Type"]


def test_reset_invalidates_all_previous_filters():
    source = """R.SETFILTER("No.", 'A*');
R.RESET;
R.FINDFIRST;"""
    result = analyze_record_filters(source, {}, {})
    assert result["lookups"][0]["active_filters"] == []


def test_not_findfirst_annotation_describes_possible_false_branch():
    nodes = [{"type": "if", "condition": "NOT R.FINDFIRST",
              "condition_span": {"line_start": 4}, "true_branch": None, "false_branch": None}]
    lookup = {"operation": "FINDFIRST", "record_variable": "R", "line": 4,
              "active_filters": [], "result": "unknown_static"}
    annotate_record_lookup_conditions(nodes, [lookup])
    assert nodes[0]["record_lookup"]["branch_meaning"] == "no_matching_record"
    assert nodes[0]["record_lookup"]["runtime_evaluated"] is False
