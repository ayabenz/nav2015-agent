from nav_ai.semantic_conditions import (
    parse_record_variables, parse_table_metadata, resolve_condition,
)


TABLE = """OBJECT Table 50063 Setting Blocked Stocktake
{
  FIELDS
  {
    { 5 ; ; Start Date ; DateTime }
    { 7 ; ; Jenis Transaksi ; Option ; OptionString=IN,OUT,ALL }
    { 11 ; ; Block Type ; Option ; OptionCaptionML=ENU=Item,Product Group,Item Category;
                                  OptionString=Item,Product Group,Item Category }
  }
}
"""


def test_table_metadata_reads_field_ids_and_option_values():
    table = parse_table_metadata(TABLE, "Table_50063.txt")
    assert table["fields"]["start date"]["id"] == 5
    assert table["fields"]["jenis transaksi"]["option_values"] == ["IN", "OUT", "ALL"]
    assert table["fields"]["block type"]["option_values"] == ["Item", "Product Group", "Item Category"]


def test_record_variable_and_option_resolution():
    table = parse_table_metadata(TABLE, "Table_50063.txt")
    variables = parse_record_variables("tblStocktake@1002 : Record 50063;")
    result = resolve_condition(
        'tblStocktake."Block Type" = tblStocktake."Block Type"::"Block Type"::"Item Category"',
        variables, {50063: table},
    )
    assert result["field_references"][0]["resolution"] == "resolved"
    assert result["field_references"][0]["field_id"] == 11
    assert result["option_members"][0]["resolution"] == "resolved"


def test_missing_table_and_field_are_not_guessed():
    variables = parse_record_variables("tblStocktake : Record 50063;")
    result = resolve_condition('tblStocktake."Unknown Field" <> \'\'', variables, {})
    assert result["field_references"][0]["resolution"] == "unresolved"
    assert result["field_references"][0]["reason"] == "table_metadata_not_found"
