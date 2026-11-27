from nav_ai.branch_effects import summarize_all_branch_effects, summarize_branch_effects
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
    nested_if = {
        "type": "if",
        "true_branch": {"type": "statement", "source": "SalesHeader.MODIFY", "line_start": 3, "line_end": 3},
        "false_branch": {"type": "statement", "source": "ERROR('credit');", "line_start": 4, "line_end": 4},
    }
    effects = summarize_branch_effects(nested_if)
    assert {effect["action"] for effect in effects} == {"record_write", "error"}
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
    nested_if = {
        "type": "if",
        "snapshot_evaluation": {"result": True},
        "true_branch": {"type": "statement", "source": "SalesHeader.MODIFY", "line_start": 3, "line_end": 3},
        "false_branch": {"type": "statement", "source": "ERROR('credit');", "line_start": 4, "line_end": 4},
    }
    effects = summarize_branch_effects(nested_if)
    assert [effect["action"] for effect in effects] == ["record_write"]
    assert effects[0]["certainty"] == "selected_by_snapshot"


def test_classifies_record_lookup_calculation_and_bulk_writes():
    nodes = [
        {"type": "statement", "source": "SalesHeader.FINDFIRST;", "line_start": 1, "line_end": 1},
        {"type": "statement", "source": "SalesHeader.CALCFIELDS(Amount);", "line_start": 2, "line_end": 2},
        {"type": "statement", "source": "SalesHeader.MODIFYALL(Blocked, TRUE);", "line_start": 3, "line_end": 3},
        {"type": "statement", "source": "EXIT(TRUE);", "line_start": 4, "line_end": 4},
    ]
    effects = summarize_branch_effects(nodes)
    assert [effect["action"] for effect in effects] == [
        "record_lookup", "record_calculation", "record_write", "exit"
    ]


def test_inventory_keeps_both_if_branches_and_their_conditions():
    tree = analyze_control_flow(
        "IF Released THEN CODEUNIT.RUN(80) ELSE ERROR('not released');"
    )
    effects = summarize_all_branch_effects(tree["nodes"])
    assert [effect["action"] for effect in effects] == ["object_run", "error"]
    assert effects[0]["branch_path"] == ["IF (Released) THEN"]
    assert effects[1]["branch_path"] == ["IF (Released) ELSE"]
    assert all(effect["certainty"] == "condition_not_evaluated" for effect in effects)
    assert all(effect["runtime_executed"] is False for effect in effects)


def test_inventory_preserves_case_arm_and_default_paths():
    tree = analyze_control_flow(
        "CASE Status OF 1: Item.MODIFY; 2: Item.DELETE; ELSE ERROR('invalid'); END;"
    )
    effects = summarize_all_branch_effects(tree["nodes"])
    assert [effect["action"] for effect in effects] == ["record_write", "record_write", "error"]
    assert effects[0]["branch_path"] == ["CASE (Status) = 1"]
    assert effects[1]["branch_path"] == ["CASE (Status) = 2"]
    assert effects[2]["branch_path"] == ["CASE (Status) ELSE"]


def test_inventory_marks_unconditional_procedure_effects_separately():
    tree = analyze_control_flow("Item.MODIFY; IF Ready THEN MESSAGE('ok');")
    effects = summarize_all_branch_effects(tree["nodes"])
    assert effects[0]["certainty"] == "procedure_reachable_not_runtime_proven"
    assert effects[0]["branch_path"] == []
    assert effects[1]["certainty"] == "condition_not_evaluated"
