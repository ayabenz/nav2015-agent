from nav_ai.condition_expression import normalize_condition_expression


def test_normalizes_comparison_and_option_member_operands():
    result = normalize_condition_expression(
        'tblStocktake."Block Type" = tblStocktake."Block Type"::"Item Category"'
    )
    assert result["type"] == "comparison"
    assert result["operator"] == "="
    assert result["left"] == 'tblStocktake."Block Type"'
    assert result["right"] == 'tblStocktake."Block Type"::"Item Category"'


def test_normalizes_boolean_precedence_and_parentheses():
    result = normalize_condition_expression(
        '(R."Item Category Code" <> \'\') OR (R."Product Group Code" <> \'\') AND NOT IsDisabled'
    )
    assert result["type"] == "boolean"
    assert result["operator"] == "OR"
    assert result["operands"][0]["operator"] == "<>"
    assert result["operands"][1]["operator"] == "AND"
    assert result["operands"][1]["operands"][1]["type"] == "not"


def test_normalizes_in_list_values_without_evaluating_them():
    result = normalize_condition_expression(
        'SalesHeader."Document Type" IN [SalesHeader."Document Type"::Order, SalesHeader."Document Type"::Invoice]'
    )
    assert result["operator"] == "IN"
    assert result["values"] == [
        'SalesHeader."Document Type"::Order',
        'SalesHeader."Document Type"::Invoice',
    ]
