from nav_ai.control_flow import analyze_control_flow
from nav_ai.filter_value_resolution import analyze_record_filter_value_flow
from nav_ai.semantic_conditions import parse_record_variables, parse_table_metadata


TABLE = """OBJECT Table 50063 Stocktake Rule
{
  FIELDS
  {
    { 7 ; ; Jenis Transaksi ; Code10 }
  }
}
"""


def test_combined_analysis_connects_assignment_to_filter_and_lookup():
    table = parse_table_metadata(TABLE, "Table50063.txt")
    variables = parse_record_variables("StocktakeRule : Record 50063;")
    parsed = analyze_control_flow("""BEGIN
  TransactionType := 'IN';
  StocktakeRule.SETRANGE("Jenis Transaksi", TransactionType);
  IF StocktakeRule.FINDFIRST THEN
    ERROR('Blocked');
END;
""", "Codeunit", 50107, "Stocktake Test", "Check", "Codeunit50107.txt")

    result = analyze_record_filter_value_flow(
        parsed["nodes"], variables, {50063: table}, "Codeunit50107.txt"
    )

    lookup = result["record_filter_analysis"]["lookups"][0]
    argument = lookup["active_filters"][0]["argument_value_resolution"][0]
    assert argument["status"] == "resolved_symbolically"
    assert argument["upstream"]["resolved_value"] == "'IN'"
    assert result["runtime_evaluated"] is False
