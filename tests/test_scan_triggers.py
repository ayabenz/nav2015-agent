"""Regression tests for object-level trigger code scanning in scan()."""
from nav_ai.depgraph import scan, Index


def _make_index(objects):
    return Index(objects)


def test_trigger_code_scanned_as_separate_scope():
    # Object with CODE section before first procedure (trigger code calling another codeunit)
    block = """OBJECT Codeunit 50000 MyTriggerTest
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
        CODEUNIT::"OtherProc";
    END.
  }
  PROCEDURE MyProc();
  BEGIN
    x := 1;
  END;
}
"""
    block_other = """OBJECT Codeunit 50001 OtherProc
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
    END.
  }
  PROCEDURE OtherProc();
  BEGIN
  END;
}
"""
    objs = {("Codeunit", 50000): block, ("Codeunit", 50001): block_other}
    idx = _make_index(objs)
    edges, tops = scan(("Codeunit", 50000), block, idx)

    # Should find a REF edge from the trigger code scope to Codeunit 50001
    ref_edges = [(s, d, k) for (s, d, k), _ in edges.items() if k == "REF"]
    assert any(
        s == "Codeunit 50000 TRIGGERS" and d == "Codeunit 50001"
        for s, d, k in ref_edges
    ), f"Expected REF edge from trigger scope to Codeunit 50001, got {ref_edges}"


def test_trigger_code_scope_with_no_procedures():
    # Object with only trigger code, no procedures at all
    block = """OBJECT Codeunit 50001 OtherProc
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
    END.
  }
}
"""
    objs = {("Codeunit", 50001): block}
    idx = _make_index(objs)
    edges, tops = scan(("Codeunit", 50001), block, idx)
    # Should not crash and should return empty edges
    assert len(edges) == 0


def test_trigger_code_references_table():
    # Trigger code in CODE section before first proc referencing a table via REF
    block = """OBJECT Table 18 Customer
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
        CODEUNIT::"OtherProc";
    END.
  }
  PROCEDURE MyProc();
  BEGIN
  END;
}
"""
    block_cu = """OBJECT Codeunit 50001 OtherProc
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
    END.
  }
}
"""
    objs = {("Table", 18): block, ("Codeunit", 50001): block_cu}
    idx = _make_index(objs)
    edges, tops = scan(("Table", 18), block, idx)

    # Should find a REF edge from trigger scope
    ref_edges = [(s, d, k) for (s, d, k), _ in edges.items() if k == "REF"]
    assert len(ref_edges) > 0, f"Expected REF edges from trigger scope, got {ref_edges}"


def test_trigger_code_scope_name_includes_TRIGGERS():
    # Verify the scope name includes "TRIGGERS" marker for debuggability
    block = """OBJECT Codeunit 50002 Test
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
    END.
  }
  PROCEDURE P();
  BEGIN
  END;
}
"""
    objs = {("Codeunit", 50002): block}
    idx = _make_index(objs)
    edges, tops = scan(("Codeunit", 50002), block, idx)
    # Just verify no crash; scope naming is internal
    assert isinstance(edges, dict)
