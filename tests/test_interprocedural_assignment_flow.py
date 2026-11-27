from nav_ai.assignment_flow import analyze_assignment_flow
from nav_ai.control_flow import analyze_control_flow


def test_unconditional_interprocedural_var_mutation_reaches_caller_if():
    source = (
        "Status := 'Old';\n"
        "Mutator.UpdateStatus(Status);\n"
        "IF Status = 'Released' THEN Post;"
    )
    tree = analyze_control_flow(source)
    result = analyze_assignment_flow(
        tree["nodes"], "caller.txt",
        call_effects={
            2: [{
                "target": "Status",
                "expression": "'Released'",
                "callee_line": 8,
                "callee_source_file": "callee.txt",
                "callee_parameter": "Status",
                "mapping": "var_scalar_argument",
            }]
        },
    )
    context = tree["nodes"][-1]["assignment_context"]["alternatives"][0]
    assert context["known_assignments"][0]["target"] == "Status"
    assert context["known_assignments"][0]["expression"] == "'Released'"
    assert context["known_assignments"][0]["interprocedural"] is True
    assert any(event["kind"] == "interprocedural_var_mutation" for event in result["events"])


def test_record_var_field_mutation_maps_to_caller_record_field():
    source = "Mutator.UpdateHeader(Rec);\nIF Rec.Status = Rec.Status::Released THEN Post;"
    tree = analyze_control_flow(source)
    analyze_assignment_flow(
        tree["nodes"], "caller.txt",
        call_effects={1: [{"target": "Rec.Status", "expression": "Status::Released"}]},
    )
    known = tree["nodes"][-1]["assignment_context"]["alternatives"][0]["known_assignments"]
    assert any(item["target"] == "Rec.Status" for item in known)
