"""Extract individual NAV Page Action and C/AL trigger source bodies.

The extractor preserves source locations and raw body text. It intentionally does
not claim that a declaration is invoked or that a textual call was executed.
"""
from __future__ import annotations

import re
from typing import Any

from .parser import OBJECT_RE, split_objects

SECTION_RE = re.compile(r"^  ([A-Z][A-Z0-9 -]*)\s*$")
ACTION_START_RE = re.compile(r"^\s*\{\s*(\d+)\s*;\s*(\d+)\s*;\s*Action(?:Container|Group|)?\s*;?", re.I)
ACTION_ID_RE = re.compile(r"^\s*\{\s*(\d+)\s*;\s*(?:\d+)?\s*;\s*Action\s*;?", re.I)
ON_ACTION_RE = re.compile(r"^\s*OnAction\s*=\s*(.*)$", re.I)
TRIGGER_RE = re.compile(
    r"^\s*(OnRun|OnInsert|OnModify|OnDelete|OnRename|OnValidate|OnLookup|"
    r"OnDrillDown|OnAssistEdit|OnOpenPage|OnClosePage|OnAfterGetRecord|"
    r"OnAfterGetCurrRecord|OnNewRecord|OnQueryClosePage|OnPreReport|"
    r"OnPostReport|OnPreDataItem|OnPreXMLport|OnPostXMLport|OnInitXMLport|"
    r"OnAfterInitRecord|OnBeforeInsertRecord|OnAfterInsertRecord|"
    r"OnBeforeModifyRecord|OnAfterModifyRecord|OnBeforeDeleteRecord|"
    r"OnAfterDeleteRecord)\s*(?:\([^)]*\))?\s*$", re.I
)
PROC_RE = re.compile(r"^\s*(?:LOCAL\s+)?PROCEDURE\s+", re.I)


def _code_depth(line: str, depth: int) -> int:
    """Update BEGIN/END depth while ignoring quoted strings and // comments."""
    line = re.sub(r"'(?:[^']|'')*'", "''", line)
    line = line.split("//", 1)[0]
    for token in re.findall(r"\b(BEGIN|END)\b", line, re.I):
        depth += 1 if token.upper() == "BEGIN" else -1
    return depth


def _capture_body(lines: list[str], start: int, *, property_mode: bool = False) -> tuple[str, int]:
    """Capture one C/AL body; return body and inclusive ending line index."""
    body: list[str] = []
    depth = 0
    seen_begin = False
    for idx in range(start, len(lines)):
        line = lines[idx]
        body.append(line)
        depth = _code_depth(line, depth)
        if re.search(r"\bBEGIN\b", re.sub(r"'(?:[^']|'')*'", "''", line), re.I):
            seen_begin = True
        if seen_begin and depth <= 0 and re.search(r"\bEND\s*;?", line, re.I):
            return "\n".join(body), idx
        if not seen_begin:
            # Single-line property expressions end at their property delimiter.
            if property_mode and idx == start and ";" in line:
                return line, idx
            if idx > start and (SECTION_RE.match(line) or PROC_RE.match(line)):
                return "\n".join(body[:-1]), idx - 1
    return "\n".join(body), len(lines) - 1


def discover_entrypoint_bodies(source_roots: list[str]) -> dict[str, Any]:
    """Return individual action/trigger bodies with exact source ranges."""
    from .entrypoint_intelligence import _source_files

    results: list[dict[str, Any]] = []
    for root in source_roots:
        for display_path, source_label, text in _source_files(root):
            for match, block in split_objects(text):
                header = OBJECT_RE.match(match.group(0).strip())
                if not header:
                    continue
                object_type, object_id, object_name = header.group(1).title(), int(header.group(2)), header.group(3).strip()
                object_node = f"{object_type} {object_id}"
                offset = text.count("\n", 0, match.start())
                lines = block.splitlines()
                section = ""
                current_action: dict[str, Any] | None = None
                idx = 0
                while idx < len(lines):
                    line = lines[idx]
                    section_match = SECTION_RE.match(line)
                    if section_match:
                        section = section_match.group(1).strip()
                        current_action = None
                        idx += 1
                        continue
                    action = ACTION_ID_RE.match(line) if section == "ACTIONS" else None
                    if action:
                        current_action = {"id": int(action.group(1)), "indent": int(action.group(2))}
                        idx += 1
                        continue
                    action_start = ON_ACTION_RE.match(line) if section == "ACTIONS" else None
                    trigger = TRIGGER_RE.match(line) if section == "CODE" else None
                    if action_start:
                        body, end_idx = _capture_body(lines, idx, property_mode=True)
                        results.append({
                            "entry_id": f"{object_node}.Action[{current_action['id'] if current_action else 'unknown'}].OnAction",
                            "object": object_node, "object_name": object_name,
                            "entry_kind": "page_action_body",
                            "action_id": current_action["id"] if current_action else None,
                            "trigger": "OnAction", "source": display_path,
                            "source_label": source_label,
                            "line_start": idx + 1 + offset, "line_end": end_idx + 1 + offset,
                            "body": body, "body_extracted": bool(body.strip()),
                            "runtime_invoked": False,
                            "evidence": "source_action_body",
                        })
                        idx = max(idx + 1, end_idx + 1)
                        continue
                    if trigger:
                        body_start = idx + 1
                        while body_start < len(lines) and not lines[body_start].strip():
                            body_start += 1
                        body, end_idx = _capture_body(lines, body_start)
                        results.append({
                            "entry_id": f"{object_node}.{trigger.group(1)}",
                            "object": object_node, "object_name": object_name,
                            "entry_kind": "object_trigger_body",
                            "trigger": trigger.group(1), "source": display_path,
                            "source_label": source_label,
                            "line_start": idx + 1 + offset, "line_end": end_idx + 1 + offset,
                            "body": body, "body_extracted": bool(body.strip()),
                            "runtime_invoked": False,
                            "evidence": "source_trigger_body",
                        })
                        idx = max(idx + 1, end_idx + 1)
                        continue
                    idx += 1
    results.sort(key=lambda x: (x["object"], x["line_start"], x["entry_id"]))
    return {
        "entry_body_count": len(results),
        "entries": results,
        "semantics": {
            "runtime_invoked": False,
            "meaning": "Individual source bodies extracted from NAV declarations; extraction is not proof of invocation.",
            "limitations": [
                "C/AL body extraction is syntax-oriented and may be incomplete for unusual formatting or malformed exports.",
                "CALL target resolution and interprocedural reachability are separate evidence stages.",
                "Action visibility, permissions, user invocation and runtime order are not evaluated.",
            ],
        },
    }
