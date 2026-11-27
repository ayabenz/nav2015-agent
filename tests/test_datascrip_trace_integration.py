import os
from pathlib import Path
import sqlite3

import pytest

from nav_ai.source_discovery import trace_call_graph


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "data" / "depgraph" / "datascrip" / "depgraph.db"
SYMBOL_PATH = ROOT / "data" / "search" / "datascrip" / "search.db"
SOURCE_ZIP = ROOT / "data" / "input" / "datascrip" / "datascrip.zip"
STOCKTAKE_OBJECT = ROOT / "reports" / "datascrip" / "ownership" / "Codeunit_50107.txt"


def open_indexes():
    graph = sqlite3.connect(GRAPH_PATH)
    symbols = sqlite3.connect(SYMBOL_PATH)
    graph.row_factory = sqlite3.Row
    symbols.row_factory = sqlite3.Row
    return graph, symbols


@pytest.mark.skipif(
    not (GRAPH_PATH.is_file() and SYMBOL_PATH.is_file() and STOCKTAKE_OBJECT.is_file()),
    reason="Datascrip graph, symbol index, or Stocktake source export is absent",
)
def test_datascrip_stocktake_entrypoint_source_and_conditions_resolve():
    graph, symbols = open_indexes()
    try:
        result = trace_call_graph(
            graph,
            "Codeunit 50107",
            [str(STOCKTAKE_OBJECT)],
            symbols,
            max_depth=0,
            max_nodes=100,
            analyze_conditions=True,
        )
    finally:
        graph.close()
        symbols.close()

    assert result["start"] == "Codeunit 50107"
    assert result["procedure_count"] > 0
    assert result["condition_analysis_count"] > 0
    assert any(item["source"]["status"] == "resolved" for item in result["procedures"])
    assert result["semantics"]["runtime_evaluated"] is False


@pytest.mark.skipif(
    os.environ.get("NAV_RUN_FULL_DATASCRIP_TRACE") != "1"
    or not (GRAPH_PATH.is_file() and SYMBOL_PATH.is_file() and SOURCE_ZIP.is_file()),
    reason="Set NAV_RUN_FULL_DATASCRIP_TRACE=1 to run the full 4,696-object source ZIP trace",
)
def test_full_datascrip_zip_trace_resolves_reachable_sources():
    graph, symbols = open_indexes()
    try:
        result = trace_call_graph(
            graph,
            "Codeunit 50107",
            [str(SOURCE_ZIP)],
            symbols,
            max_depth=1,
            max_nodes=300,
            analyze_conditions=True,
        )
    finally:
        graph.close()
        symbols.close()

    assert result["start"] == "Codeunit 50107"
    assert result["procedure_count"] > 0
    assert result["condition_analysis_count"] > 0
    assert any(item["source"]["status"] == "resolved" for item in result["procedures"])
    assert result["semantics"]["runtime_evaluated"] is False
