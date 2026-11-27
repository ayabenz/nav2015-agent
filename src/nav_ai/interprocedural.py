"""Conservative direct-call argument binding for NAV C/AL source exports.

This module reports syntactic call-site bindings only. It does not execute code,
resolve dynamic dispatch, or infer runtime values.
"""
from __future__ import annotations

import re
from typing import Any

from .parser import parse_nav_text, split_objects


_CALL = re.compile(
    r'(?P<receiver>"[^"]+"|[A-Za-z_][A-Za-z0-9_@]*)\s*\.\s*'
    r'(?P<procedure>"[^"]+"|[A-Za-z_][A-Za-z0-9_@]*)\s*\(',
    re.I,
)
_VAR = re.compile(
    r'(?m)^\s*(?:"(?P<quoted>[^"]+)"|(?P<name>[A-Za-z_][A-Za-z0-9_ ./-]*?))'
    r'(?:@\d+)?\s*:\s*(?P<type>Record\s+\d+|Boolean|Integer|Codeunit\s+\d+)\s*;',
    re.I,
)


def _split_args(value: str) -> list[str]:
    args, current = [], []
    depth, quoted = 0, False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "'":
            if quoted and i + 1 < len(value) and value[i + 1] == "'":
                current.extend([ch, value[i + 1]])
                i += 2
                continue
            quoted = not quoted
        elif not quoted:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
                i += 1
                continue
        current.append(ch)
        i += 1
    if current or value.strip():
        args.append("".join(current).strip())
    return args


def _calls(source: str):
    """Yield balanced call argument lists, ignoring parentheses inside quoted strings."""
    for match in _CALL.finditer(source):
        depth, quoted, i = 1, False, match.end()
        while i < len(source) and depth:
            ch = source[i]
            if ch == "'":
                if quoted and i + 1 < len(source) and source[i + 1] == "'":
                    i += 2
                    continue
                quoted = not quoted
            elif not quoted:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        if depth == 0:
            yield match, _split_args(source[match.end():i - 1])


def _object(source: str, source_file: str) -> tuple[dict[str, Any], str]:
    objects = split_objects(source)
    if len(objects) != 1:
        raise ValueError(f"{source_file}: expected exactly one NAV object, found {len(objects)}")
    _, block = objects[0]
    return parse_nav_text(block, source_file), block


def _record_types(parsed: dict[str, Any], block: str) -> dict[str, str]:
    result = {}
    for variable in parsed.get("variables", []):
        match = re.search(r"\bRecord\s+(\d+)\b", variable.get("data_type", ""), re.I)
        if match:
            result[variable["name"].casefold()] = f"Table {match.group(1)}"
    for procedure in parsed.get("procedures", []):
        for parameter in procedure.get("parameters", []):
            match = re.search(r"\bRecord\s+(\d+)\b", parameter.get("data_type", ""), re.I)
            if match:
                result[parameter["name"].casefold()] = f"Table {match.group(1)}"
    props = re.search(r"\bTableNo\s*=\s*(\d+)", block, re.I)
    if props:
        result["rec"] = f"Table {props.group(1)}"
    return result


def analyze_direct_call_bindings(
    caller_source: str,
    callee_source: str,
    callee_procedure: str,
    caller_file: str = "<caller>",
    callee_file: str = "<callee>",
) -> dict[str, Any]:
    """Bind caller actual arguments to one callee procedure's formal parameters."""
    caller, caller_block = _object(caller_source, caller_file)
    callee, _ = _object(callee_source, callee_file)
    targets = [p for p in callee.get("procedures", [])
               if p["name"].casefold() == callee_procedure.casefold()]
    if len(targets) != 1:
        raise ValueError(f"Expected one callee procedure {callee_procedure!r}; found {len(targets)}")
    target = targets[0]
    receiver_types = _record_types(caller, caller_block)
    code = caller_block
    bindings = []
    for match, actuals in _calls(code):
        if match.group("procedure").strip('"').casefold() != callee_procedure.casefold():
            continue
        formals = target.get("parameters", [])
        mapped = []
        for index, formal in enumerate(formals):
            if index >= len(actuals):
                mapped.append({"parameter": formal["name"], "state": "missing_argument",
                               "formal_type": formal["data_type"], "by_reference": formal["by_reference"]})
                continue
            actual = actuals[index]
            record_type = receiver_types.get(actual.strip('"').casefold())
            literal = actual.upper() in {"TRUE", "FALSE"}
            formal_record = re.search(r"Record\s+(\d+)", formal["data_type"], re.I)
            mapped.append({
                "parameter": formal["name"],
                "formal_type": formal["data_type"],
                "by_reference": formal["by_reference"],
                "argument": actual,
                "argument_record_type": record_type,
                "type_match": (
                    record_type == f"Table {formal_record.group(1)}"
                    if record_type and formal_record
                    else ("compatible_literal" if literal and formal["data_type"].casefold() == "boolean"
                          else "unresolved")
                ),
                "binding_kind": "record_variable" if record_type else ("boolean_literal" if literal else "symbolic_expression"),
                "runtime_value_known": False,
            })
        bindings.append({
            "caller_object": f"{caller['object']['type']} {caller['object']['id']}",
            "caller_object_name": caller["object"]["name"],
            "callee_procedure": target["name"],
            "receiver": match.group("receiver").strip('"'),
            "line": code.count("\n", 0, match.start()) + 1,
            "arguments": mapped,
            "source_file": caller_file,
            "evidence": "direct_static_call_syntax",
            "runtime_evaluated": False,
        })
    return {
        "analysis": "direct_interprocedural_argument_binding",
        "callee": f"{callee['object']['type']} {callee['object']['id']}.{target['name']}",
        "formal_parameters": target.get("parameters", []),
        "call_sites": bindings,
        "runtime_evaluated": False,
        "limitations": [
            "Only direct receiver.Procedure(...) call syntax is recognized.",
            "WITH-scoped calls, unqualified calls, dynamic dispatch and indirect callbacks are not resolved.",
            "Argument expressions are preserved symbolically; no runtime value is inferred.",
            "VAR parameters are marked by-reference, but post-call mutations are not propagated.",
            "Source line numbers are relative to the supplied caller export.",
        ],
    }
