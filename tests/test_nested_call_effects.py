from nav_ai.intelligence import _build_nested_call_effects
from nav_ai.var_mutation import analyze_var_parameter_mutations


PARENT = """OBJECT Codeunit 60001 Parent
{
  CODE
  {
    PROCEDURE Process@1(VAR Header@1000 : Record 36;DoUpdate@1001 : Boolean);
    VAR
      Child : Codeunit 60002;
    BEGIN
      Child.Update(Header, FALSE);
    END;
  }
}"""


CHILD = """OBJECT Codeunit 60002 Child
{
  CODE
  {
    PROCEDURE Update@1(VAR Header@1000 : Record 36;DoUpdate@1001 : Boolean);
    BEGIN
      IF DoUpdate THEN
        Header.Status := 'THEN'
      ELSE
        Header.Status := 'ELSE';
    END;
  }
}"""


def test_nested_var_effect_is_included_in_parent_var_summary(tmp_path):
    child_path = tmp_path / "child.txt"
    child_path.write_text(CHILD, encoding="utf-8")
    effects = _build_nested_call_effects(PARENT, "parent.txt", [str(child_path)])
    assert effects
    summary = analyze_var_parameter_mutations(
        PARENT,
        "Process",
        "parent.txt",
        call_effects=effects,
    )
    header = next(item for item in summary["var_parameters"] if item["parameter"] == "Header")
    assert len(header["mutations"]) == 1
    mutation = header["mutations"][0]
    assert mutation["target"] == "Header.Status"
    assert mutation["expression"] == "'ELSE'"
    assert mutation["interprocedural"] is True
    assert mutation["evaluated"] is False
