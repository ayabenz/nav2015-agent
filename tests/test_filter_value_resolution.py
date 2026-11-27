from nav_ai.filter_value_resolution import enrich_record_filter_values


def test_resolves_filter_argument_from_prior_literal_assignment():
    filters = {
        "events": [{
            "operation": "SETRANGE", "line": 12, "path": [],
            "arguments": ["TransactionType"],
        }],
        "lookups": [],
    }
    assignments = {
        "events": [{
            "kind": "explicit_assignment", "target_key": "transactiontype",
            "target": "TransactionType", "expression": "'IN'", "line": 8,
            "source_file": "Codeunit50107.txt", "path": [],
        }]
    }

    enrich_record_filter_values(filters, assignments)

    value = filters["events"][0]["argument_value_resolution"][0]
    assert value["status"] == "resolved_symbolically"
    assert value["upstream"]["status"] == "literal"
    assert value["upstream"]["resolved_value"] == "'IN'"


def test_does_not_use_assignment_from_incompatible_if_branch():
    filters = {
        "events": [{
            "operation": "SETRANGE", "line": 20,
            "path": [{"if": "IsInbound", "outcome": False}],
            "arguments": ["TransactionType"],
        }],
        "lookups": [],
    }
    assignments = {
        "events": [{
            "kind": "explicit_assignment", "target_key": "transactiontype",
            "expression": "'IN'", "line": 10,
            "path": [{"if": "IsInbound", "outcome": True}],
        }]
    }

    enrich_record_filter_values(filters, assignments)

    value = filters["events"][0]["argument_value_resolution"][0]
    assert value["status"] == "unresolved_variable"


def test_lookup_filter_resolution_uses_assignment_at_filter_line():
    record_filter = {
        "operation": "SETRANGE", "line": 12,
        "arguments": ["TransactionType"],
    }
    filters = {"events": [], "lookups": [{
        "line": 18, "path_conditions": [],
        "active_filters": [record_filter],
    }]}
    assignments = {"events": [{
        "kind": "explicit_assignment", "target_key": "transactiontype",
        "expression": "'OUT'", "line": 8, "path": [],
    }]}

    enrich_record_filter_values(filters, assignments)

    value = filters["lookups"][0]["active_filters"][0]["argument_value_resolution"][0]
    assert value["upstream"]["resolved_value"] == "'OUT'"
