from nav_ai.condition_expression import normalize_condition_expression
from nav_ai.intelligence import _attach_snapshot_evaluations
from nav_ai.semantic_conditions import parse_record_variables, parse_table_metadata


def test_cli_snapshot_annotation_marks_source_and_keeps_runtime_false():
    table_source = """OBJECT Table 50063 Setting Blocked Stocktake
{
  FIELDS
  {
    { 7 ; ; Jenis Transaksi ; Option ; OptionString=IN,OUT,ALL }
  }
}
"""
    from nav_ai.semantic_conditions import parse_table_metadata
    variables = parse_record_variables(
        'PROCEDURE Check@1(tblStocktake : Record 50063);'
    )
    tables = {50063: parse_table_metadata(table_source)}
    nodes = [{
        "type": "if",
        "normalized_condition": normalize_condition_expression(
            'tblStocktake."Jenis Transaksi" = tblStocktake."Jenis Transaksi"::ALL'
        ),
    }]
    _attach_snapshot_evaluations(
        nodes, {"tblStocktake": {"Jenis Transaksi": 2}}, variables, tables
    )
    assert nodes[0]["snapshot_evaluation"]["result"] is True
    assert nodes[0]["snapshot_evaluation"]["provenance"] == "caller_supplied_snapshot"
    assert nodes[0]["snapshot_evaluation"]["runtime_evaluated"] is False
