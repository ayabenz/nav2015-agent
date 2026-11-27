from nav_ai.process_classification import classify_process_candidate


def test_sales_candidate_uses_object_procedure_and_table_evidence():
    result = classify_process_candidate({
        "object": "Codeunit 60001",
        "name": "Sales Order Posting",
        "type": "Codeunit",
        "reachable_procedures": [
            {"node": "Codeunit 60001.PostSalesOrder"},
            {"node": "Codeunit 60001.CheckShipment"},
        ],
        "tables": [
            {"table": "Table 36", "name": "Sales Header"},
            {"table": "Table 37", "name": "Sales Line"},
        ],
    })
    assert result["primary_domain"] == "sales"
    assert result["confidence"] == "moderate_heuristic"
    assert result["evidence"]["sales"]
    assert result["business_process_validated"] is False


def test_unrelated_candidate_is_not_forced_into_a_domain():
    result = classify_process_candidate({
        "object": "Codeunit 69999",
        "name": "ZXY Internal Handler",
        "type": "Codeunit",
        "reachable_procedures": [{"node": "Codeunit 69999.RunTask"}],
        "tables": [],
    })
    assert result["primary_domain"] == "unclassified"
    assert result["confidence"] == "insufficient_lexical_evidence"


def test_competing_domain_evidence_is_reported_as_ambiguous():
    result = classify_process_candidate({
        "object": "Page 70000",
        "name": "Sales Purchase Overview",
        "type": "Page",
        "reachable_procedures": [],
        "tables": [],
    })
    assert result["primary_domain"] == "ambiguous"
    assert result["confidence"] == "ambiguous"
    assert len(result["ranked_domains"]) >= 2
