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


def test_resolves_option_member_against_filter_field_metadata():
    filters = {
        "events": [{
            "operation": "SETRANGE", "line": 14, "path:": [],
            "arguments": ['StocktakeRule."Jenis Transaksi"::IN'],
            "field_resolution": {
                "resolution": "resolved", "field": "Jenis Transaksi",
                "option_values": ["IN", "OUT", "ALL"],
            },
        }],
        "lookups": [],
    }
    enrich_record_filter_values(filters, {"events": []})
    value = filters["events"][0]["argument_value_resolution"][0]
    assert value["status"] == "resolved_option"
    assert value["resolved_value"] == "IN"
    assert value["evaluated"] is False


def test_setfilter_placeholder_is_bound_to_resolved_argument():
    filters = {
        "events": [{
            "operation": "SETFILTER", "line": 20, "path": [],
            "arguments": ["'=%1'", "TargetStatus"],
            "field_resolution": {"resolution": "resolved", "field": "Status",
                                 "option_values": ["Open", "Released"]},
        }],
        "lookups": [],
    }
    assignments = {"events": [{
        "kind": "explicit_assignment", "target_key": "targetstatus",
        "target": "TargetStatus", "expression": "'Released'", "line": 8,
        "source_file": "Codeunit.txt", "path": [],
    }]}
    enrich_record_filter_values(filters, assignments)
    event = filters["events"][0]
    binding = event["setfilter_interpretation"]["placeholder_bindings"][0]
    assert binding["placeholder"] == "%1"
    assert binding["argument"] == "TargetStatus"
    assert binding["argument_resolution"]["upstream"]["resolved_value"] == "'Released'"
    assert event["setfilter_interpretation"]["status"] == "resolved_symbolically"
