from nav_ai.interprocedural import build_caller_var_effect_map


def _binding(actual, path):
    return {
        "call_sites": [{
            "line": 42,
            "arguments": [{
                "parameter": "DoUpdate",
                "formal_type": "Boolean",
                "argument": actual,
                "type_match": "compatible_literal",
            }],
            "var_parameter_effects": [{
                "parameter": "Header",
                "caller_argument": "SalesHeader",
                "mutations": [{
                    "target": "Header.Status",
                    "expression": "Header.Status::Released",
                    "line": 18,
                    "source_file": "callee.txt",
                    "path": path,
                }],
            }],
        }]
    }


def test_conditional_var_mutation_propagates_when_callsite_selects_path():
    binding = _binding(
        "FALSE",
        [{"if": "DoUpdate", "outcome": False}],
    )
    effects = build_caller_var_effect_map(binding)
    assert len(effects[42]) == 1
    assert effects[42][0]["target"] == "SalesHeader.Status"
    assert effects[42][0]["path_specialization"] == "call_site_boolean_arguments"
    assert effects[42][0]["runtime_evaluated"] is False


def test_conditional_var_mutation_discards_incompatible_path():
    binding = _binding(
        "FALSE",
        [{"if": "DoUpdate", "outcome": True}],
    )
    assert build_caller_var_effect_map(binding) == {}


def test_conditional_var_mutation_is_not_propagated_when_predicate_unknown():
    binding = _binding(
        "FALSE",
        [{"if": "SomeOtherCondition", "outcome": True}],
    )
    assert build_caller_var_effect_map(binding) == {}


def test_mixed_resolved_and_unknown_path_is_not_claimed_definite():
    binding = _binding(
        "FALSE",
        [
            {"if": "DoUpdate", "outcome": False},
            {"if": "DatabaseFlag", "outcome": True},
        ],
    )
    assert build_caller_var_effect_map(binding) == {}


def test_unconditional_var_mutation_still_propagates():
    binding = _binding("FALSE", [])
    effects = build_caller_var_effect_map(binding)
    assert len(effects[42]) == 1
    assert effects[42][0]["path_specialization"] == "unconditional"
