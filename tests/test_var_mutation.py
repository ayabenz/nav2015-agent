from nav_ai.var_mutation import analyze_var_parameter_mutations

CALLEE = """OBJECT Codeunit 50107 Mutator
{
  CODE
  {
    PROCEDURE UpdateHeader@1(VAR SalesHeader@1000 : Record 36;VAR Status@1001 : Text[30];DoUpdate@1002 : Boolean);
    BEGIN
      IF DoUpdate THEN BEGIN
        SalesHeader.Status := SalesHeader.Status::Released;
        Status := 'Released';
      END ELSE
        Status := 'Open';
    END;
  }
}"""


def test_summarizes_var_record_field_and_scalar_mutations_by_path():
    result = analyze_var_parameter_mutations(CALLEE, "UpdateHeader", "mutator.txt")
    params = {item["parameter"]: item for item in result["var_parameters"]}
    assert set(params) == {"SalesHeader", "Status"}
    header = params["SalesHeader"]["mutations"]
    assert len(header) == 1
    assert header[0]["target"] == "SalesHeader.Status"
    assert header[0]["effect_kind"] == "explicit_record_field_mutation"
    status = params["Status"]["mutations"]
    assert {item["expression"] for item in status} == {"'Released'", "'Open'"}
    assert all(item["evaluated"] is False for item in status)
    assert status[0]["path"]


def test_non_var_parameters_are_not_reported_as_mutable_parameters():
    result = analyze_var_parameter_mutations(CALLEE, "UpdateHeader")
    assert all(item["parameter"] != "DoUpdate" for item in result["var_parameters"])


def test_no_explicit_mutation_is_not_claimed_as_immutable():
    source = CALLEE.replace("Status := 'Released';", "MESSAGE('updated');").replace("Status := 'Open';", "MESSAGE('unchanged');")
    result = analyze_var_parameter_mutations(source, "UpdateHeader")
    status = next(item for item in result["var_parameters"] if item["parameter"] == "Status")
    assert status["mutation_state"] == "no_explicit_mutation_found"
    assert status["mutations"] == []



def test_summarizes_mapped_nested_call_mutation_to_var_parameter():
    nested_effect = {
        "target": "SalesHeader.Status",
        "expression": "SalesHeader.Status::Released",
        "callee_line": 24,
        "callee_source_file": "child.txt",
        "callee_parameter": "Header",
        "mapping": "var_record_field_argument",
    }
    # The procedure body starts immediately after BEGIN; call line is the
    # next physical line in this fixture.
    result = analyze_var_parameter_mutations(
        CALLEE.replace(
            "        SalesHeader.Status := SalesHeader.Status::Released;",
            "        Child.Change(SalesHeader);",
        ).replace(
            "    PROCEDURE UpdateHeader@1(VAR SalesHeader@1000 : Record 36;VAR Status@1001 : Text[30];DoUpdate@1002 : Boolean);",
            "    PROCEDURE UpdateHeader@1(VAR SalesHeader@1000 : Record 36;VAR Status@1001 : Text[30];DoUpdate@1002 : Boolean);",
        ),
        "UpdateHeader",
        "parent.txt",
        call_effects={9: [nested_effect]},
    )
    header = next(item for item in result["var_parameters"] if item["parameter"] == "SalesHeader")
    assert any(item["target"] == "SalesHeader.Status"
               and item["interprocedural"]
               and item["expression"] == "SalesHeader.Status::Released"
               for item in header["mutations"])
