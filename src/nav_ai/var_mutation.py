"""Conservative summaries of mutations to VAR procedure parameters."""
from __future__ import annotations

import re
from typing import Any

from .assignment_flow import analyze_assignment_flow
from .control_flow import analyze_control_flow
from .parser import parse_nav_text, split_objects


def analyze_var_parameter_mutations(
    callee_source: str,
    procedure_name: str,
    source_file: str = "<callee>",
) -> dict[str, Any]:
    """Summarize explicit assignments to VAR parameters in one procedure.

    This is a source summary, not a complete side-effect analysis. It does not
    execute expressions, resolve nested calls, or infer database writes.
    """
    objects = split_objects(callee_source)
    if len(objects) != 1:
        raise ValueError(f"{source_file}: expected exactly one NAV object, found {len(objects)}")
    _, block = objects[0]
    parsed = parse_nav_text(block, source_file)
    matches = [p for p in parsed.get("procedures", [])
               if p["name"].casefold() == procedure_name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Expected one procedure {procedure_name!r}; found {len(matches)}")
    procedure = matches[0]
    var_parameters = [p for p in procedure.get("parameters", []) if p.get("by_reference")]
    raw_lines = procedure["raw"].splitlines()
    begin = next((i for i, line in enumerate(raw_lines) if line.strip().upper() == "BEGIN"), None)
    if begin is None:
        raise ValueError(f"Procedure {procedure_name!r} has no BEGIN block")
    body = "\n".join(raw_lines[begin:])
    tree = analyze_control_flow(body, source_file=source_file,
                                line_offset=procedure["line_start"] + begin - 1)
    flow = analyze_assignment_flow(tree["nodes"], source_file)
    summaries = []
    for parameter in var_parameters:
        name = parameter["name"]
        key = re.sub(r"\s+", "", name).casefold()
        effects = []
        for event in flow.get("events", []):
            if event.get("kind") != "explicit_assignment":
                continue
            target_key = event.get("target_key", "")
            # Exact scalar parameter assignment or explicit field mutation on a Record VAR.
            if target_key == key or target_key.startswith(key + "."):
                effects.append({
                    "target": event["target"],
                    "expression": event["expression"],
                    "line": event["line"],
                    "path": event.get("path", []),
                    "source_file": event.get("source_file"),
                    "evaluated": False,
                    "effect_kind": "explicit_var_parameter_assignment" if target_key == key
                                   else "explicit_record_field_mutation",
                })
        summaries.append({
            "parameter": name,
            "formal_type": parameter["data_type"],
            "mutations": effects,
            "mutation_state": "explicit_mutations_found" if effects else "no_explicit_mutation_found",
        })
    return {
        "analysis": "static_var_parameter_mutation_summary",
        "callee": f"{parsed['object']['type']} {parsed['object']['id']}.{procedure['name']}",
        "var_parameters": summaries,
        "runtime_evaluated": False,
        "limitations": [
            "Only explicit := assignments to a VAR parameter or its qualified fields are summarized.",
            "Nested procedure calls, triggers, database writes and implicit side effects are not propagated.",
            "No expression is evaluated; assigned values remain symbolic.",
            "No mutation found means no supported explicit assignment was detected, not proof of immutability.",
        ],
    }
