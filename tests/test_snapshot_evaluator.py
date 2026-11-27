from nav_ai.condition_expression import normalize_condition_expression
from nav_ai.semantic_conditions import parse_record_variables, parse_table_metadata
from nav_ai.snapshot_evaluator import evaluate_condition_snapshot


TABLE = """OBJECT Table 50063 Setting Blocked Stocktake
{
  FIELDS
  {
    { 7 ; ; Jenis Transaksi ; Option ; OptionString=IN,OUT,ALL }
    { 11 ; ; Block Type ; Option ; OptionString=Item,Product Group,Item Category }
    { 12 ; ; Item Category Code ; Code20 }
    { 13 ; ; Blocked ; Boolean }
  }
}
"""


def _context():
    table = parse_table_metadata(TABLE, "Table_50063.txt")
    variables = parse_record_variables("tblStocktake : Record 50063;")
    return variables, {50063: table}


def test_evaluates_option_field_from_sql_style_ordinal_snapshot():
    variables, tables = _context()
    condition = normalize_condition_expression(
        'tblStocktake."Jenis Transaksi" = tblStocktake."Jenis Transaksi"::ALL'
    )
    result = evaluate_condition_snapshot(
        condition, {"tblStocktake": {"Jenis Transaksi": 2}}, variables, tables
    )
    assert result["result"] is True
    assert result["status"] == "evaluated_from_supplied_snapshot"
    assert result["runtime_evaluated"] is False


def test_evaluates_nested_boolean_condition_from_explicit_snapshot():
    variables, tables = _context()
    condition = normalize_condition_expression(
        '(tblStocktake."Block Type" = tblStocktake."Block Type"::"Block Type"::"Item Category") AND (tblStocktake."Item Category Code" <> \'\')'
    )
    result = evaluate_condition_snapshot(
        condition,
        {"tblStocktake": {"Block Type": 2, "Item Category Code": "ELEC"}},
        variables, tables,
    )
    assert result["result"] is True


def test_missing_snapshot_field_returns_indeterminate_not_false():
    variables, tables = _context()
    condition = normalize_condition_expression('tblStocktake."Item Category Code" <> \'\'')
    result = evaluate_condition_snapshot(condition, {"tblStocktake": {}}, variables, tables)
    assert result["result"] is None
    assert result["status"] == "indeterminate"
    assert "snapshot_field_missing:tblStocktake.Item Category Code" in result["missing_or_unsupported"]


def test_missing_table_metadata_does_not_turn_option_mismatch_into_false():
    variables = parse_record_variables("tblStocktake : Record 50063;")
    condition = normalize_condition_expression(
        'tblStocktake."Jenis Transaksi" = tblStocktake."Jenis Transaksi"::ALL'
    )
    result = evaluate_condition_snapshot(
        condition, {"tblStocktake": {"Jenis Transaksi": 2}}, variables, {}
    )
    assert result["result"] is None
    assert result["status"] == "indeterminate"
    assert any(reason.startswith("field_metadata_unresolved:")
               for reason in result["missing_or_unsupported"])


def test_boolean_field_is_evaluated_without_python_bool_integer_coercion():
    variables, tables = _context()
    condition = normalize_condition_expression('tblStocktake.Blocked = FALSE')
    result = evaluate_condition_snapshot(
        condition, {"tblStocktake": {"Blocked": False}}, variables, tables
    )
    assert result["result"] is True


def test_cross_type_comparison_is_indeterminate_not_false():
    variables, tables = _context()
    condition = normalize_condition_expression('tblStocktake."Item Category Code" = 123')
    result = evaluate_condition_snapshot(
        condition, {"tblStocktake": {"Item Category Code": "123"}}, variables, tables
    )
    assert result["result"] is None
    assert "incompatible_value_types:str:int" in result["missing_or_unsupported"]


def test_explanation_reports_each_comparison_and_combined_boolean_result():
    variables, tables = _context()
    condition = normalize_condition_expression(
        '(tblStocktake.Blocked = FALSE) AND (tblStocktake."Item Category Code" <> \'\')'
    )
    result = evaluate_condition_snapshot(
        condition,
        {"tblStocktake": {"Blocked": False, "Item Category Code": "ELEC"}},
        variables, tables,
    )
    comparisons = [item for item in result["explanation"] if item["kind"] == "comparison"]
    assert [item["result"] for item in comparisons] == [True, True]
    assert any(item["kind"] == "boolean" and item["result"] is True
               for item in result["explanation"])
