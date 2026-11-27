"""Evidence-oriented Markdown reports for traced NAV business processes."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import re


def _cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\\n", " ")


def _source_reference(flow: dict[str, Any], effect: dict[str, Any]) -> str:
    source = effect.get("source", "").strip()
    line_start = effect.get("line_start")
    line_end = effect.get("line_end")
    source_info = flow.get("source", {})
    label = source_info.get("source_label") or source_info.get("source_path") or "source unavailable"
    if line_start is not None:
        line = str(line_start) if line_end in (None, line_start) else f"{line_start}-{line_end}"
        return f"`{label}:{line}` — `{source}`" if source else f"`{label}:{line}`"
    return f"`{label}` — `{source}`" if source else f"`{label}`"


def render_business_process_markdown(trace: dict[str, Any]) -> str:
    """Render a trace result as a navigable, evidence-qualified process report."""
    summary = trace.get("process_summary", {})
    lines = [
        f"# NAV Business Process: {trace.get('start', 'Unknown start')}",
        "",
        "> Static source and dependency-graph analysis. This report does not prove runtime execution,",
        "> transaction commit, or actual business outcome.",
        "",
        "## 1. Analysis scope",
        "",
        f"- Start: `{trace.get('start', 'unknown')}`",
        f"- Maximum call depth: {trace.get('max_depth', 'unknown')}",
        f"- Procedures discovered: {trace.get('procedure_count', 0)}",
        f"- CALL edges: {trace.get('edge_count', 0)}",
        f"- Procedures with condition analysis: {trace.get('condition_analysis_count', 0)}",
        f"- Table metadata loaded: {trace.get('table_metadata_count', 0)}",
        f"- Traversal truncated: {bool(trace.get('truncated', False))}",
        "",
        "## 2. Process summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Procedures | {summary.get('procedure_count', 0)} |",
        f"| Call edges | {summary.get('call_edge_count', 0)} |",
        f"| Tables referenced | {summary.get('table_count', 0)} |",
        f"| Unresolved call targets | {summary.get('unresolved_call_target_count', 0)} |",
    ]
    for usage, count in sorted(summary.get("table_usage_counts", {}).items()):
        lines.append(f"| Table usage {usage} | {count} |")
    for action, count in sorted(summary.get("branch_effect_counts", {}).items()):
        lines.append(f"| Source effect {action} | {count} |")
    lines += ["", "## 3. Procedure call paths", ""]
    for flow in trace.get("business_flow", []):
        lines += [
            f"### {flow.get('procedure', 'Unknown procedure')}",
            "",
            f"- Depth: {flow.get('depth', 0)}",
            f"- Call path: {' → '.join(flow.get('call_path', [])) or 'not available'}",
            f"- Object origin: {flow.get('origin', 'unknown')}",
            f"- Source resolution: {flow.get('source_status', 'unknown')}",
            f"- Condition analysis: {flow.get('condition_analysis_status', 'not requested')}",
            f"- Effects inventoried: {flow.get('effect_count', 0)}",
            "",
        ]
        usages = flow.get("table_usage", [])
        if usages:
            lines += ["**Direct table usage**", "", "| Table | Usage | Count |", "|---|---|---:|"]
            for item in usages:
                lines.append(
                    f"| {_cell(item.get('table_node') or item.get('table_name'))} "
                    f"| {_cell(item.get('usage'))} | {item.get('count', 0)} |"
                )
            lines.append("")
        effects = flow.get("effects", [])
        if effects:
            lines += ["**Source-level effects by branch**", ""]
            for effect in effects:
                branch = " → ".join(effect.get("branch_path", [])) or "Unconditional within procedure"
                lines.append(
                    f"- **{_cell(effect.get('action'))}** — {_cell(branch)} "
                    f"(certainty: `{_cell(effect.get('certainty'))}`; "
                    f"runtime executed: `{bool(effect.get('runtime_executed', False))}`)"
                )
                lines.append(f"  - Evidence: {_source_reference(flow, effect)}")
            lines.append("")
        elif flow.get("condition_analysis_status") != "analyzed":
            lines += ["No branch effects were inventoried because source/condition analysis was unavailable or not requested.", ""]
        lines.append("---")
        lines.append("")
    lines += ["## 4. Aggregate table usage", ""]
    aggregate = trace.get("table_usage_summary", [])
    if aggregate:
        lines += ["| Table | Usage | Count | New vs original |", "|---|---|---:|---:|"]
        for item in aggregate:
            lines.append(
                f"| {_cell(item.get('table_node'))} — {_cell(item.get('table_name'))} "
                f"| {_cell(item.get('usage'))} | {item.get('count', 0)} "
                f"| {item.get('new_vs_original', 0)} |"
            )
    else:
        lines.append("No table-usage rows were returned by the dependency graph.")
    lines += ["", "## 5. Unresolved call targets", ""]
    unresolved = trace.get("unresolved_call_targets", [])
    if unresolved:
        for item in unresolved:
            lines.append(f"- `{item.get('src')}` → `{item.get('dst')}`: {item.get('reason')}")
    else:
        lines.append("No unresolved object-level CALL targets were reported.")
    lines += ["", "## 6. Custom/standard NAV boundaries", ""]
    transitions = trace.get("origin_transitions", [])
    if transitions:
        lines += ["| Caller | Origin | Callee | Origin |",
                  "|---|---|---|---|"]
        for edge in transitions:
            lines.append(
                f"| {_cell(edge.get('src'))} | {_cell(edge.get('src_origin'))} "
                f"| {_cell(edge.get('dst'))} | {_cell(edge.get('dst_origin'))} |"
            )
        lines.append("")
        lines.append("These are dependency-graph CALL edges crossing object-origin classifications, not proof that the call executed.")
    else:
        lines.append("No cross-origin procedure CALL transitions were found in the traced subgraph.")
    lines += ["", "## 7. Evidence limitations", ""]
    for limitation in trace.get("semantics", {}).get("limitations", []):
        lines.append(f"- {limitation}")
    lines += [
        "- Branch-effect counts are syntactic source occurrences, not execution counts.",
        "- A source-level MODIFY/INSERT/DELETE is not proof that the database change committed.",
        "- Record filter and snapshot conclusions require explicit supported input values; absent values remain unknown.",
        "",
        "## 8. Reproducibility",
        "",
        "The companion JSON file contains the full trace payload, including source-resolution status,",
        "condition trees, assignment/filter analysis, graph edges, and branch-effect evidence.",
        "",
    ]
    return "\n".join(lines)


def write_business_process_report(trace: dict[str, Any], output: str | Path) -> tuple[Path, Path]:
    """Write Markdown report and machine-readable JSON beside one another."""
    import json

    markdown_path = Path(output)
    if markdown_path.suffix.lower() != ".md":
        markdown_path = markdown_path.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = markdown_path.with_suffix(".json")
    markdown_path.write_text(render_business_process_markdown(trace), encoding="utf-8")
    json_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return markdown_path, json_path


def default_report_name(start: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", start).strip("._-")
    return slug or "nav_business_process"
