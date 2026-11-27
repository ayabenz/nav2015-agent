from nav_ai.branch_effects import summarize_branch_effects
from nav_ai.control_flow import analyze_control_flow


def test_summarizes_error_commit_and_record_write_in_selected_branch():
    tree = analyze_control_flow(
        "IF Ready THEN BEGIN\n"
        "  ERROR('blocked');\n"
        "  Item.MODIFY;\n"
        "  COMMIT;\n"
        "END ELSE MESSAGE('not ready');"
    )
    effects = summarize_branch_effects(tree["nodes"][0]["true_branch"])
    assert [effect["action"] for effect in effects] == ["error", "record_write", "commit"]
    assert all(effect["certainty"] == "selected_by_snapshot" for effect in effects)
    assert all(effect["runtime_executed"] is False for effect in effects)


def test_nested_if_effects_are_not_claimed_when_nested_condition_unknown():
    tree = analyze_control_flow(
        "IF Ready THEN IF CreditOK THEN SalesHeader.MODIFY ELSE ERROR('credit');"
    )
    effects = summarize_branch_effects(tree["nodes"][0]["true_branch"])
    assert len(effects) == 2
    assert {effect["certainty"] for effect in effects} == {"nested_condition_indeterminate"}


def test_indeterminate_outer_condition_labels_both_branches_as_possible():
    tree = analyze_control_flow("IF Ready THEN ERROR('stop') ELSE Item.MODIFY;")
    effects = (
        summarize_branch_effects(tree["nodes"][0]["true_branch"], "possible_true_branch") +
        summarize_branch_effects(tree["nodes"][0]["false_branch"], "possible_false_branch")
    )
    assert [effect["certainty"] for effect in effects] == [
        "possible_true_branch", "possible_false_branch"
    ]


def test_nested_snapshot_selected_if_limits_effects_to_its_selected_path():
    tree = analyze_control_flow(
        "IF Ready THEN IF CreditOK THEN SalesHeader.MODIFY ELSE ERROR('credit');"
    )
    nested = tree["nodes"][0]["true_branch"]
    nested["snapshot_evaluation"] = {"result": True}
    effects = summarize_branch_effects(tree["nodes"][0]["true_branch"])
    assert [effect["action"] for effect in effects] == ["record_write"]
    assert effects[0]["certainty"] == "selected_by_snapshot"
