from pathlib import Path
import json

from nav_ai.business_docs import (
    default_report_name,
    render_business_process_markdown,
    write_business_process_report,
)


def sample_trace():
    return {
        "start": "Codeunit 60001",
        "max_depth": 2,
        "procedure_count": 2,
        "edge_count": 1,
        "conditions_analyzed": True,
        "condition_analysis_count": 1,
        "table_metadata_count": 1,
        "truncated": False,
        "process_summary": {
            "procedure_count": 2,
            "call_edge_count": 1,
            "table_count": 1,
            "unresolved_call_target_count": 0,
            "table_usage_counts": {"WRITE": 1},
            "branch_effect_counts": {"error": 1, "message": 1},
        },
        "business_flow": [{
            "procedure": "Codeunit 60002.Update",
            "depth": 1,
            "call_path": ["Codeunit 60001.Run", "Codeunit 60002.Update"],
            "source_status": "resolved",
            "source": {"source_label": "child.txt"},
            "condition_analysis_status": "analyzed",
            "effect_count": 2,
            "runtime_executed": False,
            "table_usage": [{"table_node": "Table 36", "table_name": "Sales Header",
                             "usage": "WRITE", "count": 1}],
            "effects": [
                {"action": "message", "source": "MESSAGE('ok')", "line_start": 12,
                 "line_end": 12, "branch_path": ["IF (Ready) THEN"],
                 "certainty": "condition_not_evaluated", "runtime_executed": False},
                {"action": "error", "source": "ERROR('bad')", "line_start": 14,
                 "line_end": 14, "branch_path": ["IF (Ready) ELSE"],
                 "certainty": "condition_not_evaluated", "runtime_executed": False},
            ],
        }],
        "table_usage_summary": [{"table_node": "Table 36", "table_name": "Sales Header",
                                 "usage": "WRITE", "count": 1, "new_vs_original": 1}],
        "origin_transitions": [{
            "src": "Codeunit 60001.Run", "src_origin": "CUSTOM",
            "dst": "Codeunit 60002.Update", "dst_origin": "STANDARD_UNCHANGED",
        }],
        "unresolved_call_targets": [],
        "semantics": {"limitations": ["Only CALL edges already present are traversed."]},
    }


def test_markdown_report_contains_paths_effects_and_evidence():
    report = render_business_process_markdown(sample_trace())
    assert "# NAV Business Process: Codeunit 60001" in report
    assert "Codeunit 60001.Run → Codeunit 60002.Update" in report
    assert "IF (Ready) THEN" in report
    assert "child.txt:12" in report
    assert "runtime executed: `False`" in report
    assert "Custom/standard NAV boundaries" in report
    assert "STANDARD_UNCHANGED" in report
    assert "does not prove runtime execution" in report


def test_report_writer_creates_markdown_and_machine_readable_json(tmp_path):
    markdown, machine = write_business_process_report(sample_trace(), tmp_path / "process.md")
    assert markdown.is_file() and machine.is_file()
    assert "NAV Business Process" in markdown.read_text(encoding="utf-8")
    data = json.loads(machine.read_text(encoding="utf-8"))
    assert data["start"] == "Codeunit 60001"


def test_default_report_name_is_safe_for_paths():
    assert default_report_name("Codeunit 80.Post Item/Jnl Line") == "Codeunit_80.Post_Item_Jnl_Line"
