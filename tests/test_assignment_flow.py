from nav_ai.assignment_flow import analyze_assignment_flow
from nav_ai.control_flow import analyze_control_flow


def run(source):
    tree = analyze_control_flow(source)
    result = analyze_assignment_flow(tree["nodes"], "sample.txt")
    return tree["nodes"], result


def test_literal_assignment_is_attached_to_later_condition():
    nodes, result = run("Status := 'Released';\nIF Status = 'Released' THEN Post;")
    context = nodes[-1]["assignment_context"]["alternatives"][0]
    assert context["known_assignments"][0]["target"] == "Status"
    assert context["known_assignments"][0]["expression"] == "'Released'"
    assert context["known_assignments"][0]["evaluated"] is False


def test_record_field_assignment_is_tracked():
    nodes, _ = run('SalesHeader.Status := SalesHeader.Status::Released;\nIF SalesHeader.Status = SalesHeader.Status::Released THEN Post;')
    known = nodes[-1]["assignment_context"]["alternatives"][0]["known_assignments"]
    assert any(x["target"] == "SalesHeader.Status" for x in known)


def test_reassignment_uses_latest_assignment():
    nodes, _ = run("Status := 'Open';\nStatus := 'Released';\nIF Status = 'Released' THEN Post;")
    known = nodes[-1]["assignment_context"]["alternatives"][0]["known_assignments"]
    status = next(x for x in known if x["target"] == "Status")
    assert status["expression"] == "'Released'"
    assert status["line"] == 2


def test_if_else_assignments_remain_separate_after_branch():
    nodes, _ = run("IF Flag THEN Status := 'Open' ELSE Status := 'Released';\nIF Status = 'Open' THEN Post;")
    context = nodes[1]["assignment_context"]
    assert context["state"] == "multiple_incoming_paths"
    values = {a["known_assignments"][0]["expression"] for a in context["alternatives"]}
    assert values == {"'Open'", "'Released'"}


def test_unknown_call_invalidates_known_assignments():
    nodes, result = run("Status := 'Open';\nMutate(Status);\nIF Status = 'Open' THEN Post;")
    context = nodes[-1]["assignment_context"]["alternatives"][0]
    assert context["known_assignments"] == []
    assert any(e["kind"] == "unknown_call_invalidation" for e in result["events"])


def test_call_inside_assignment_invalidates_other_tracked_values():
    nodes, result = run("Status := 'Open';\nOther := GetStatus();\\nIF Status = 'Open' THEN Post;")
    context = nodes[-1]["assignment_context"]["alternatives"][0]
    assert context["known_assignments"] == []
    assert any(e["kind"] == "unknown_call_invalidation" for e in result["events"])
