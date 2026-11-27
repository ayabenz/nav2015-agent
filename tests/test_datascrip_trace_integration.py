from pathlib import Path
import sqlite3

import pytest

from nav_ai.source_discovery import trace_call_graph


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "data" / "depgraph" / "datascrip" / "depgraph.db"
SYMBOL_PATH = ROOT / "data" / "search" / "datascrip" / "search.db"
SOURCE_ZIP = ROOT / "data" / "input" / "datascrip" / "datascrip.zip"


@pytest.mark.skipif(
    not (GRAPH_PATH.is_file() and SYMBOL_PATH.is_file() and SOURCE_ZIP.is_file()),
    reason="Datascrip integration artifacts are not present in this checkout",
)
def test_datascrip_stocktake_entrypoint_trace_resolves_real_sources():
    with sqlite3.connect(GRAPH_PATH) as graph, sqlite3.connect(SYMBOL_PATH) as symbols:
        graph.row_factory = sqlite3.Row
        symbols.row_factory = sqlite3.Row
        result = trace_call_graph(
            graph,
            "Codeunit 50107",
            [str(SOURCE_ZIP)],
            symbols,
            max_depth=1,
            max_nodes=100,
            analyze_conditions=False,
        )

    assert result["start"] == "Codeunit 50107"
    assert result["procedure_count"] > 0
    assert result["conditions_analyzed"] is False
    assert any(
        item["source"]["status"] == "resolved"
        for item in result["procedures"]
    )
    assert result["semantics"]["runtime_evaluated"] is False
