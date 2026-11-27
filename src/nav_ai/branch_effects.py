"""Summarize source-level effects inside a snapshot-selected control-flow branch.

These are syntactic effects in the selected source branch, not evidence that NAV
executed the statements or that a database write committed.
"""
from __future__ import annotations

import re
from typing import Any


_PATTERNS = (
    ("error", re.compile(r"\bERROR\s*\(", re.I)),
    ("message", re.compile(r"\bMESSAGE\s*\(", re.I)),
    ("confirmation", re.compile(r"\bCONFIRM\s*\(", re.I)),
    ("exit", re.compile(r"\bEXIT\s*;", re.I)),
    ("commit", re.compile(r"\bCOMMIT\s*;", re.I)),
    ("record_write", re.compile(r"\b[A-Za-z_][A-Za-z0-9_@]*\s*\.\s*(?:INSERT|MODIFY|DELETE|RENAME)\s*(?:\(|;|$)", re.I)),
    ("record_validation", re.compile(r"\b[A-Za-z_][A-Za-z0-9_@]*\s*\.\s*(?:VALIDATE|TESTFIELD|FIELDERROR)\s*\(", re.I)),
    ("record_filter", re.compile(r"\b[A-Za-z_][A-Za-z0-9_@]*\s*\.\s*(?:SETRANGE|SETFILTER|RESET|SETCURRENTKEY)\s*(?:\(|;|$)", re.I)),
    ("object_run", re.compile(r"\b(?:CODEUNIT|REPORT|PAGE)\s*\.\s*RUN\w*\s*\(", re.I)),
)


def _classify(source: str) -> list[str]:
    return [name for name, pattern in _PATTERNS if pattern.search(source)]


def summarize_branch_effects(branch: Any, certainty: str = "selected_by_snapshot") -> list[dict[str, Any]]:
    """Return classified statements below a branch, preserving nested uncertainty."""
    effects: list[dict[str, Any]] = []

    def walk(node: Any, state: str) -> None:
        if node is None:
            return
        if isinstance(node, list):
            for child in node:
                walk(child, state)
            return
        if not isinstance(node, dict):
            return
        kind = node.get("type")
        if kind == "statement":
            source = str(node.get("source", ""))
            for action in _classify(source):
                effects.append({
                    "action": action,
                    "source": source,
                    "line_start": node.get("line_start"),
                    "line_end": node.get("line_end"),
                    "certainty": state,
                    "runtime_executed": False,
                })
        elif kind == "block":
            walk(node.get("children", []), state)
        elif kind == "if":
            result = node.get("snapshot_evaluation", {}).get("result")
            if result is True:
                walk(node.get("true_branch"), state)
            elif result is False:
                walk(node.get("false_branch"), state)
            else:
                walk(node.get("true_branch"), "nested_condition_indeterminate")
                walk(node.get("false_branch"), "nested_condition_indeterminate")
        elif kind == "case":
            for arm in node.get("arms", []):
                walk(arm.get("body"), "nested_case_not_evaluated")
            walk(node.get("default"), "nested_case_not_evaluated")

    walk(branch, certainty)
    return effects
