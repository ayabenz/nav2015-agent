"""Conservative direct-call argument binding for NAV C/AL source exports.

This module reports syntactic call-site bindings only. It does not execute code,
resolve dynamic dispatch, or infer runtime values.
"""
from __future__ import annotations

import re
from typing import Any

from .parser import parse_nav_text, split_objects


_CALL = re.compile(
    r'(?P<receiver>"[^"]+"|[A-Za-z_][A-Za-z0-9_@]*)\\s*\\.\\s*'
    r'(?P<procedure>"[^"]+"|[A-Za-z_][A-Za-z0-9_@]*)\\s*\\(',
    re.I,
)
_VAR = re.compile(
    r'(?m)^\\s*(?:"(?P<quoted>[^"]+)"|(?P<name>[A-Za-z_][A-Za-z0-9_ ./-]*?))'
    r'(?:@\\d+)?\\s*:\\s*(?P<type>Record\\s+\\d+|Boolean|Integer|Codeunit\\s+\\d+)\\s*;',
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


def _mask_non_code(source: str) -> str:
    """Mask C/AL strings and comments, preserving structural NAV braces and offsets."""
    chars = list(source)
    for pattern in (r"'(?:''|[^'])*'", r"//[^\\n]*", r"\\{[^{}]*\\}"):
        for match in re.finditer(pattern, source):
            if pattern.startswith(r"\\{"):
                start_line = source.rfind("\\n", 0, match.start()) + 1
                end_line = source.find("\\n", match.end())
                if end_line < 0:
                    end_line = len(source)
                structural = (
                    "\\n" in match.group(0)
                    and not source[start_line:match.start()].strip()
                    and not source[match.end():end_line].strip()
                )
                if structural:
                    continue
            for pos in range(match.start(), match.end()):
                if chars[pos] != "\\n":
                    chars[pos] = " "
    return "".join(chars)


def _calls(source: str):
    """Yield call matches from masked code and arguments from original source."""
    masked = _mask_non_code(source)
    for match in _CALL.finditer(masked):
        depth, i = 1, match.end()
        while i < len(masked) and depth:
            if masked[i] == "(":
                depth += 1
            elif masked[i] == ")":
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
        match = re.search(r"\\bRecord\\s+(\\d+)\\b", variable.get("data_type", ""), re.I)
        if match:
            result[variable["name"].casefold()] = f"Table {match.group(1)}"
    for procedure in parsed.get("procedures", []):
        for parameter in procedure.get("parameters", []):
            match = re.search(r"\\bRecord\\s+(\\d+)\\b", parameter.get("data_type", ""), re.I)
            if match:
                result[parameter["name"].casefold()] = f"Table {match.group(1)}"
    props = re.search(r"\\bTableNo\\s*=\\s*(\\d+)", block, re.I)
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
    for variable in _VAR.finditer(caller_block):
        name = (variable.group("quoted") or variable.group("name") or "").strip()
        data_type = variable.group("type")
        if name:
            receiver_types[name.casefold()] = data_type.title()
    target_object = f"{callee['object']['type']} {callee['object']['id']}"
    bindings = []
    for match, actuals in _calls(caller_block):
        if match.group("procedure").strip('"').casefold() != callee_procedure.casefold():
            continue
        receiver_type = receiver_types.get(match.group("receiver").strip('"').casefold())
        if receiver_type != target_object:
            continue
        formals = target.get("parameters", [])
        mapped = []
        for index, formal in enumerate(formals):
            if index >= len(actuals):
                mapped.append({
                    "parameter": formal["name"], "state": "missing_argument",
                    "formal_type": formal["data_type"], "by_reference": formal["by_reference"],
                })
                continue
            actual = actuals[index]
            record_type = receiver_types.get(actual.strip('"').casefold())
            literal = actual.upper() in {"TRUE", "FALSE"}
            formal_record = re.search(r"Record\\s+(\\d+)", formal["data_type"], re.I)
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
                "binding_kind": "record_variable" if record_type else (
                    "boolean_literal" if literal else "symbolic_expression"
                ),
                "runtime_value_known": False,
            })
        bindings.append({
            "caller_object": f"{caller['object']['type']} {caller['object']['id']}",
            "caller_object_name": caller["object"]["name"],
            "callee_procedure": target["name"],
            "receiver": match.group("receiver").strip('"'),
            "line": caller_block.count("\\n", 0, match.start()) + 1,
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
            "VAR parameters are marked by-reference; conditional and nested side effects are not fully propagated.",
            "Source line numbers are relative to the supplied caller export.",
        ],
    }


def build_caller_var_effect_map(binding: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    """Map unconditional callee VAR assignments back to simple caller variables.

    Conditional callee mutations are not asserted as definite caller assignments.
    """
    result: dict[int, list[dict[str, Any]]] = {}
    simple_name = re.compile(r'^(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_@]*)$')
    for site in binding.get("call_sites", []):
        line = int(site.get("line", 0))
        if line <= 0:
            continue
        for effect_group in site.get("var_parameter_effects", []):
            actual = str(effect_group.get("caller_argument", "")).strip()
            if not simple_name.fullmatch(actual):
                continue
            formal = str(effect_group.get("parameter", "")).strip()
            prefix = formal.casefold()
            for mutation in effect_group.get("mutations", []):
                if mutation.get("path"):
                    continue
                target = str(mutation.get("target", "")).strip()
                if target.casefold() == prefix:
                    caller_target = actual
                    mapping = "var_scalar_argument"
                elif target.casefold().startswith(prefix + "."):
                    caller_target = actual + target[len(formal):]
                    mapping = "var_record_field_argument"
                else:
                    continue
                result.setdefault(line, []).append({
                    "target": caller_target,
                    "expression": mutation.get("expression", ""),
                    "callee_line": mutation.get("line"),
                    "callee_source_file": mutation.get("source_file"),
                    "callee_parameter": formal,
                    "mapping": mapping,
                    "conditional": False,
                })
    return result
