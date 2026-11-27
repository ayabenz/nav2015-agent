"""Source-declared NAV entry-point evidence.

This module inventories trigger declarations and object launch properties from
NAV TXT exports. It does not infer that an entry point was invoked at runtime.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from .parser import OBJECT_RE, split_objects

TRIGGER_RE = re.compile(
    r"^\s*(OnRun|OnInsert|OnModify|OnDelete|OnRename|OnValidate|"
    r"OnLookup|OnDrillDown|OnAssistEdit|OnOpenPage|OnClosePage|"
    r"OnAfterGetRecord|OnAfterGetCurrRecord|OnNewRecord|OnQueryClosePage|"
    r"OnPreReport|OnPostReport|OnPreDataItem|OnAfterGetRecord|"
    r"OnPreXMLport|OnPostXMLport|OnInitXMLport|OnAfterInitRecord|"
    r"OnBeforeInsertRecord|OnAfterInsertRecord|OnBeforeModifyRecord|"
    r"OnAfterModifyRecord|OnBeforeDeleteRecord|OnAfterDeleteRecord)"
    r"\s*(?:\([^)]*\))?\s*(?:=|$)", re.I
)
RUN_OBJECT_RE = re.compile(
    r"^\s*RunObject\s*=\s*(Table|Page|Codeunit|Report|XMLport|Query)\s+(\d+)",
    re.I,
)
ON_ACTION_RE = re.compile(r"^\s*OnAction\s*=", re.I)
SECTION_RE = re.compile(r"^  ([A-Z][A-Z0-9 -]*)\s*$")
PROCEDURE_RE = re.compile(r"^\s*(?:LOCAL\s+)?PROCEDURE\s+", re.I)


def _source_files(root: str):
    path = Path(root)
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.suffix.lower() == ".txt":
                yield from _read_text(item)
            elif item.suffix.lower() == ".zip":
                yield from _read_zip(item)
    elif path.is_file() and path.suffix.lower() == ".zip":
        yield from _read_zip(path)
    elif path.is_file():
        yield from _read_text(path)
    else:
        raise FileNotFoundError(f"Source root not found: {root}")


def _read_text(path: Path):
    if path.is_file() and path.suffix.lower() == ".txt":
        yield str(path), path.name, path.read_text(encoding="utf-8-sig", errors="replace")


def _read_zip(path: Path):
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith(".txt"):
                    yield f"{path}!{name}", name, archive.read(name).decode("utf-8-sig", errors="replace")
    except zipfile.BadZipFile:
        return


def discover_source_entrypoints(source_roots: list[str]) -> dict[str, Any]:
    """Return deterministic, source-located entry-point declarations."""
    entries: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, str]] = set()
    for root in source_roots:
        for display_path, source_label, text in _source_files(root):
            identity = (display_path.casefold(), source_label.casefold())
            if identity in seen_sources:
                continue
            seen_sources.add(identity)
            for match, block in split_objects(text):
                header = OBJECT_RE.match(match.group(0).strip())
                if not header:
                    continue
                object_type, object_id, object_name = header.group(1).title(), int(header.group(2)), header.group(3).strip()
                lines = block.splitlines()
                section = ""
                code_started = False
                for line_no, line in enumerate(lines, 1):
                    section_match = SECTION_RE.match(line)
                    if section_match:
                        section = section_match.group(1).strip()
                        code_started = section == "CODE"
                        continue
                    if code_started and PROCEDURE_RE.match(line):
                        code_started = False
                    trigger = TRIGGER_RE.match(line)
                    if trigger:
                        entries.append({
                            "object": f"{object_type} {object_id}",
                            "object_name": object_name,
                            "object_type": object_type,
                            "entry_kind": "object_or_dataitem_trigger",
                            "trigger": trigger.group(1),
                            "source": display_path,
                            "source_label": source_label,
                            "line": line_no,
                            "evidence": "trigger_declaration_in_CODE_section" if code_started else "trigger_property_declaration",
                            "confidence": "source_declaration",
                            "runtime_invoked": False,
                        })
                    run_object = RUN_OBJECT_RE.match(line)
                    if run_object:
                        entries.append({
                            "object": f"{object_type} {object_id}",
                            "object_name": object_name,
                            "object_type": object_type,
                            "entry_kind": "object_launch_property",
                            "target": f"{run_object.group(1).title()} {int(run_object.group(2))}",
                            "source": display_path,
                            "source_label": source_label,
                            "line": line_no,
                            "section": section,
                            "evidence": "RunObject_property",
                            "confidence": "source_declaration",
                            "runtime_invoked": False,
                        })
                    if ON_ACTION_RE.match(line):
                        entries.append({
                            "object": f"{object_type} {object_id}",
                            "object_name": object_name,
                            "object_type": object_type,
                            "entry_kind": "page_action_trigger",
                            "trigger": "OnAction",
                            "source": display_path,
                            "source_label": source_label,
                            "line": line_no,
                            "section": section,
                            "evidence": "OnAction_property",
                            "confidence": "source_declaration",
                            "runtime_invoked": False,
                        })
    entries.sort(key=lambda item: (
        item["object_type"], int(item["object"].rsplit(" ", 1)[1]),
        item["line"], item["entry_kind"], item.get("target", ""),
    ))
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["entry_kind"]] = counts.get(entry["entry_kind"], 0) + 1
    return {
        "entrypoint_count": len(entries),
        "counts_by_kind": dict(sorted(counts.items())),
        "entries": entries,
        "semantics": {
            "runtime_invoked": False,
            "meaning": "Source-declared entry-point evidence, not proof of user invocation or runtime execution.",
            "limitations": [
                "RunObject and OnAction properties are declarations; actual UI visibility, permissions and invocation are not evaluated.",
                "Job Queue execution targets are commonly stored in Job Queue Entry records and configured at runtime; source declarations alone cannot enumerate configured jobs.",
                "Event subscriber invocation and external integration schedules require separate metadata/runtime evidence.",
                "Trigger declarations identify source scopes, not a complete execution sequence.",
            ],
        },
    }
