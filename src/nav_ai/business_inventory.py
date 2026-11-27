"""Automatic inventory and documentation for ranked NAV process candidates."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .business_docs import write_business_process_report
from .process_mapping import map_candidate_processes
from .process_classification import classify_process_candidates
from .source_discovery import trace_call_graph
from .entrypoint_intelligence import discover_source_entrypoints
from .entrypoint_tracing import trace_entrypoint_graph
from .entrypoint_bodies import discover_entrypoint_bodies
from .entrypoint_call_mapping import map_entrypoint_calls


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-") or "nav_process"


def render_inventory_markdown(inventory: dict[str, Any]) -> str:
    mapping = inventory["mapping"]
    lines = [
        "# NAV Business Process Inventory",
        "",
        "> Automatically generated from ranked object candidates, static CALL dependencies,",
        "> source exports and indexed Table usage. Candidate groups are heuristic, not confirmed",
        "> business processes or proof of runtime execution.",
        "",
        "## Scope",
        "",
        f"- Candidates selected: {mapping['candidate_count']}",
        f"- Candidate clusters: {mapping['cluster_count']}",
        f"- Source traces completed: {inventory['trace_success_count']}",
        f"- Source traces unavailable: {inventory['trace_failure_count']}",
        f"- CALL depth limit: {inventory['limits']['max_depth']}",
        f"- Per-candidate node limit: {inventory['limits']['max_nodes']}",
        f"- Condition analysis: {inventory['limits']['analyze_conditions']}",
        "",
        "## Candidate clusters",
        "",
    ]
    if mapping["clusters"]:
        for index, cluster in enumerate(mapping["clusters"], 1):
            lines += [
                f"### Cluster {index}: {', '.join(cluster['members'])}",
                "",
                f"- Basis: `{cluster['basis']}`",
                f"- Confidence: `{cluster['confidence']}`",
                f"- Shared Table universe: {', '.join(cluster['shared_table_universe']) or 'none'}",
                "",
            ]
    else:
        lines += ["No multi-candidate clusters met the configured similarity threshold.", ""]
    lines += [
        "## Candidate inventory",
        "",
        "| Candidate | Domain hint | Role hint | Origin | Score | Procedures | Tables | Trace status |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    traces = inventory["traces"]
    for candidate in mapping["candidates"]:
        trace = traces.get(candidate["object"], {})
        lines.append(
            f"| {candidate['object']} — {candidate.get('name') or ''} "
            f"| {candidate.get('domain_classification', {}).get('primary_domain', 'unclassified')} "
            f"({candidate.get('domain_classification', {}).get('confidence', 'unknown')}) "
            f"| {candidate.get('domain_classification', {}).get('operational_profile', {}).get('role_hint', 'undetermined')} "
            f"| {candidate['origin']} | {candidate['score']} "
            f"| {candidate.get('reachable_procedure_count', 0)} "
            f"| {len(candidate.get('table_ids', []))} "
            f"| {trace.get('status', 'not_traced')} |"
        )
    lines += [
        "",
        "## Evidence and limitations",
        "",
        "- CALL paths are static dependency-graph edges; they are not runtime call logs.",
        "- Table footprints aggregate indexed usage from procedures reached within configured limits.",
        "- A Table shared by multiple candidates does not prove they are one business process.",
        "- Dynamic RUN targets, UI navigation, job queues and external integration triggers may be missing.",
        "- Each successful candidate trace has a separate Markdown and JSON report with source references and branch effects when requested.",
        "- Missing or ambiguous source exports are reported; no source object is guessed.",
        "",
        "## Reproduction",
        "",
        "See the command and limits recorded in the companion JSON inventory.",
        "",
    ]
    return "\n".join(lines)


def generate_business_process_inventory(
    graph,
    symbols,
    source_roots: list[str],
    output_dir: str | Path,
    *,
    limit: int = 100,
    include_standard: bool = False,
    min_similarity: float = 0.25,
    max_depth: int = 5,
    max_nodes: int = 5000,
    analyze_conditions: bool = True,
    max_interprocedural_depth: int = 2,
) -> dict[str, Any]:
    """Map candidates, trace each one, and write a complete evidence inventory."""
    if not source_roots:
        raise ValueError("At least one source root is required")
    if limit < 1 or max_nodes < 1 or max_depth < 0:
        raise ValueError("limit/max_nodes must be positive and max_depth non-negative")
    output = Path(output_dir)
    objects_dir = output / "objects"
    clusters_dir = output / "clusters"
    objects_dir.mkdir(parents=True, exist_ok=True)
    clusters_dir.mkdir(parents=True, exist_ok=True)

    mapping = map_candidate_processes(
        graph, limit=limit, include_standard=include_standard,
        min_similarity=min_similarity, max_depth=max_depth,
        max_nodes_per_candidate=max_nodes,
    )
    mapping["candidates"] = classify_process_candidates(mapping["candidates"])
    entrypoints = discover_source_entrypoints(source_roots)
    entrypoint_bodies = discover_entrypoint_bodies(source_roots)
    entrypoint_call_mapping = map_entrypoint_calls(
        graph, entrypoint_bodies, max_depth=max_depth, max_nodes=max_nodes
    )
    (output / "entrypoint_call_mapping.json").write_text(
        json.dumps(entrypoint_call_mapping, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8"
    )
    (output / "entrypoint_bodies.json").write_text(json.dumps(entrypoint_bodies, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "entrypoints.json").write_text(json.dumps(entrypoints, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    entrypoint_traces = trace_entrypoint_graph(
        graph, entrypoints["entries"], max_depth=max_depth, max_nodes=max_nodes
    )
    (output / "entrypoint_traces.json").write_text(
        json.dumps(entrypoint_traces, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    traces: dict[str, dict[str, Any]] = {}
    failures: dict[str, dict[str, str]] = {}
    for candidate in mapping["candidates"]:
        node = candidate["object"]
        try:
            trace = trace_call_graph(
                graph, node, source_roots, symbols,
                max_depth=max_depth, max_nodes=max_nodes,
                analyze_conditions=analyze_conditions,
                max_interprocedural_depth=max_interprocedural_depth,
            )
            write_business_process_report(
                trace, objects_dir / f"{_slug(node)}.md"
            )
            resolved_sources = trace.get("process_summary", {}).get("source_status_counts", {}).get("resolved", 0)
            if resolved_sources:
                traces[node] = {"status": "generated", "report": f"objects/{_slug(node)}.md"}
            else:
                error = "No reachable procedure source exports resolved"
                failures[node] = {"error": error}
                traces[node] = {"status": "unavailable", "error": error, "report": f"objects/{_slug(node)}.md"}
        except (ValueError, FileNotFoundError) as exc:
            failures[node] = {"error": str(exc)}
            traces[node] = {"status": "unavailable", "error": str(exc)}

    for index, cluster in enumerate(mapping["clusters"], 1):
        cluster_name = f"cluster_{index:03d}_{_slug(cluster['members'][0])}"
        lines = [
            f"# Related NAV Process Candidates: {cluster_name}",
            "",
            "> Heuristic cluster based on shared Tables in bounded CALL-reachable procedures.",
            "> This is not a validated business-process boundary.",
            "",
            "## Members",
            "",
        ]
        for member in cluster["members"]:
            lines.append(f"- [{member}](../objects/{_slug(member)}.md) — {traces.get(member, {}).get('status', 'not_traced')}")
        lines += ["", "## Shared Table universe", ""]
        lines.extend(f"- {table}" for table in cluster["shared_table_universe"])
        lines += ["", "## Pairwise evidence", ""]
        member_set = set(cluster["members"])
        for pair in mapping["similarities"]:
            if pair["left"] in member_set and pair["right"] in member_set:
                lines.append(
                    f"- {pair['left']} ↔ {pair['right']}: "
                    f"Jaccard={pair['jaccard_similarity']}; shared={', '.join(pair['shared_tables'])}"
                )
        (clusters_dir / f"{cluster_name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    inventory = {
        "company": output.parent.name,
        "mapping": mapping,
        "entrypoints": entrypoints,
        "entrypoint_bodies": entrypoint_bodies,
        "entrypoint_call_mapping": entrypoint_call_mapping,
        "entrypoint_traces": entrypoint_traces,
        "traces": traces,
        "trace_failures": failures,
        "trace_success_count": sum(item["status"] == "generated" for item in traces.values()),
        "trace_failure_count": len(failures),
        "limits": {
            "limit": limit, "include_standard": include_standard,
            "min_similarity": min_similarity, "max_depth": max_depth,
            "max_nodes": max_nodes, "analyze_conditions": analyze_conditions,
            "max_interprocedural_depth": max_interprocedural_depth,
            "source_roots": source_roots,
        },
        "semantics": {
            "runtime_evaluated": False,
            "process_boundaries_validated": False,
            "trace_method": "bounded static CALL graph plus source export analysis",
        },
    }
    (output / "process_inventory.md").write_text(
        render_inventory_markdown(inventory), encoding="utf-8"
    )
    (output / "process_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return inventory
