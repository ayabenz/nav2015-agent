"""Regression tests: procedure names inside C/AL strings are not calls."""
from nav_ai.depgraph import Index, scan


def _codeunit():
    return """OBJECT Codeunit 50020 StringCallTest
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
    END.
  }
    PROCEDURE Caller();
  BEGIN
    MESSAGE('OtherProc');
  END;

    PROCEDURE OtherProc();
  BEGIN
  END;
}
"""


def test_procedure_name_inside_string_does_not_create_call_edge():
    block = _codeunit()
    idx = Index({("Codeunit", 50020): block})
    edges, _ = scan(("Codeunit", 50020), block, idx)
    false_edges = [
        (src, dst, kind)
        for (src, dst, kind), _count in edges.items()
        if kind == "CALL" and src == "Codeunit 50020.Caller"
    ]
    assert false_edges == []


def test_real_bare_procedure_call_is_detected():
    block = _codeunit().replace("MESSAGE('OtherProc');", "OtherProc;")
    idx = Index({("Codeunit", 50020): block})
    edges, _ = scan(("Codeunit", 50020), block, idx)
    assert ("Codeunit 50020.Caller", "Codeunit 50020.OtherProc", "CALL") in edges
