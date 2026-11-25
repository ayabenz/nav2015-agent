"""Regression tests for ambiguous object name resolution in Index.names."""
from nav_ai.depgraph import Index, scan

KIND = {"record": "Table", "codeunit": "Codeunit", "page": "Page", "report": "Report",
        "xmlport": "XMLport", "query": "Query", "database": "Table"}

TABLE_TMPL = """OBJECT Table {id} Customer
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

CODEUNIT_TMPL = """OBJECT Codeunit {id} TestCU
{
  PROPERTIES
  {
  END.
  CODE
  {
    BEGIN
        DATABASE::"Customer";
    END.
  }
  PROCEDURE P();
  BEGIN
  END;
}
"""


def _make_table(id_):
    return TABLE_TMPL.replace("{id}", str(id_))


def _make_codeunit(id_):
    return CODEUNIT_TMPL.replace("{id}", str(id_))


def test_index_names_stores_multiple_ids_for_same_name():
    # Two tables both named "Customer" with different IDs
    block1 = _make_table(18)
    block2 = _make_table(50000)
    objs = {("Table", 18): block1, ("Table", 50000): block2}
    idx = Index(objs)

    # names should map to a list of IDs
    key = ("table", "customer")
    assert key in idx.names
    assert 18 in idx.names[key]
    assert 50000 in idx.names[key]


def test_resolve_returns_none_for_ambiguous_name():
    block1 = _make_table(18)
    block2 = _make_table(50000)
    objs = {("Table", 18): block1, ("Table", 50000): block2}
    idx = Index(objs)

    assert idx.resolve("record", "Customer") is None
    assert idx.resolve("record", "Missing") is None


def test_scan_with_ambiguous_table_reference():
    # Codeunit references "Table 18 Customer" which exists as ID 18 (and also 50000)
    block_cu = _make_codeunit(50010)
    block_t18 = _make_table(18)
    block_t50000 = _make_table(50000)
    objs = {
        ("Codeunit", 50010): block_cu,
        ("Table", 18): block_t18,
        ("Table", 50000): block_t50000,
    }
    idx = Index(objs)
    edges, tops = scan(("Codeunit", 50010), block_cu, idx)

    # Should resolve to one of the Customer table IDs
    ref_edges = [(s, d, k) for (s, d, k), _ in edges.items() if k in ("REF", "TABLE_REF")]
    assert len(ref_edges) > 0, f"Expected REF edges, got {ref_edges}"
    dst = ref_edges[0][1]
    assert dst in ("Table 18", "Table 50000"), f"Unexpected dst: {dst}"


def test_resolve_returns_unique_object():
    block = _make_table(18)
    idx = Index({("Table", 18): block})
    assert idx.resolve("record", "Customer") == "Table 18"


def test_index_names_single_id_unchanged():
    # Single object should still work as before (list with one element)
    block = """OBJECT Codeunit 80 Sales-Post
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
    objs = {("Codeunit", 80): block}
    idx = Index(objs)
    assert idx.names[("codeunit", "sales-post")] == [80]
