from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import Any

PARSER_VERSION = "0.2.0"
OBJECT_RE = re.compile(r"^OBJECT\s+(Table|Page|Codeunit|Report|XMLport|MenuSuite|Form|Dataport|Query)\s+(\d+)\s+(.+?)\s*$", re.I | re.M)
SECTION_RE = re.compile(r"^  ([A-Z][A-Z0-9 -]*)\s*$")
PROC_RE = re.compile(r"^\s*(LOCAL\s+)?PROCEDURE\s+(.+?)\s*$", re.I)
# A field starts on one line but its body (CaptionML, OnValidate, ...) usually spans many; "}" closes it.
FIELD_RE = re.compile(r"^\s*\{\s*(\d+)\s*;\s*;\s*([^;]+?)\s*;\s*([^;}]+?)\s*(?:;|\}|$)")
KEY_RE = re.compile(r"^\s*\{\s*;\s*(.+?)\s*\}\s*$")
CONTROL_RE = re.compile(r"^\s*\{\s*(\d+)\s*;\s*(\d+)\s*;\s*([A-Za-z][A-Za-z0-9_]*)\s*;?\s*$")
PROPERTY_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 .()/-]*)=(.*?);?\s*$")
VAR_RE = re.compile(r"^\s*(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9 ._/-]*?))(?:@(\d+))?\s*:\s*(.+?)\s*;\s*$")
TYPE_REF_RE = re.compile(r"\b(Record|Codeunit|Page|Report|XMLport|Query)\s+(\d+)\b", re.I)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _section_ranges(lines: list[str]) -> dict[str, tuple[int, int]]:
    starts: list[tuple[str, int]] = []
    allowed = {"OBJECT-PROPERTIES", "PROPERTIES", "FIELDS", "KEYS", "FIELDGROUPS", "CONTROLS", "ACTIONS", "CODE", "REQUESTPAGE", "DATAITEMS", "ELEMENTS"}
    for idx, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if match and match.group(1).strip() in allowed:
            starts.append((match.group(1).strip(), idx))
    ranges: dict[str, tuple[int, int]] = {}
    for i, (label, start) in enumerate(starts):
        end = starts[i + 1][1] - 1 if i + 1 < len(starts) else len(lines) - 1
        ranges[label] = (start, end)
    return ranges


def _extract_properties(lines: list[str], start: int, end: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for idx in range(start + 1, end):
        line = lines[idx]
        m = PROPERTY_RE.match(line)
        if m and not line.lstrip().startswith("//"):
            result[m.group(1).strip()] = {"value": m.group(2).strip(), "line": idx + 1}
    return result


def _extract_fields(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    fields = []
    idx = start + 1
    while idx < end:
        m = FIELD_RE.match(lines[idx])
        if not m:
            idx += 1
            continue
        # shortcut: brace depth ignores braces inside string literals; fine unless a text constant holds an unbalanced one.
        depth, stop = 0, idx
        while stop < end:
            depth += lines[stop].count("{") - lines[stop].count("}")
            if depth <= 0:
                break
            stop += 1
        fields.append({"id": int(m.group(1)), "name": m.group(2).strip(), "data_type": m.group(3).strip(), "line_start": idx + 1, "line_end": stop + 1, "raw": lines[idx]})
        idx = stop + 1
    return fields


def _extract_keys(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    keys = []
    for idx in range(start + 1, end):
        line = lines[idx]
        if line.strip().startswith("{") and ";" in line:
            m = KEY_RE.match(line)
            if m:
                keys.append({"definition": m.group(1).strip(), "line": idx + 1, "raw": line})
    return keys


def _split_top_level(value: str, delimiter: str = ";") -> list[str]:
    parts, current = [], []
    depth = 0
    quoted = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == '"':
            if quoted and i + 1 < len(value) and value[i + 1] == '"':
                current.extend([ch, value[i + 1]])
                i += 2
                continue
            quoted = not quoted
        elif not quoted:
            if ch in "[({": depth += 1
            elif ch in "])}": depth = max(0, depth - 1)
            elif ch == delimiter and depth == 0:
                parts.append("".join(current).strip())
                current = []
                i += 1
                continue
        current.append(ch)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def _parse_parameters(signature: str) -> list[dict[str, Any]]:
    open_idx = signature.find("(")
    close_idx = signature.rfind(")")
    if open_idx < 0 or close_idx < open_idx:
        return []
    params = []
    for part in _split_top_level(signature[open_idx + 1:close_idx]):
        m = re.match(r"^(VAR\s+)?(.+?)\s*:\s*(.+)$", part, re.I)
        if not m:
            continue
        raw_name = m.group(2).strip()
        raw_name = re.sub(r"@\d+$", "", raw_name)
        params.append({"name": raw_name.strip('"'), "by_reference": bool(m.group(1)), "data_type": m.group(3).strip(), "raw": part})
    return params


def _extract_procedures(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    declarations: list[tuple[int, str, bool]] = []
    for idx in range(start + 1, end):
        m = PROC_RE.match(lines[idx])
        if m:
            declarations.append((idx, m.group(2).strip(), bool(m.group(1))))
    procedures = []
    for i, (decl_idx, declaration, is_local) in enumerate(declarations):
        stop = declarations[i + 1][0] if i + 1 < len(declarations) else end
        if i == len(declarations) - 1:
            # NAV exports commonly place a final BEGIN/comment block after the last procedure.
            for j in range(decl_idx + 1, end - 1):
                if lines[j].strip() == "BEGIN" and j + 1 < end and lines[j + 1].strip() == "{":
                    stop = j
                    break
        signature = declaration.rstrip(";").strip()
        name_match = re.match(r"([^(@]+)", signature)
        name = name_match.group(1).strip() if name_match else signature
        procedures.append({"name": name, "signature": signature, "parameters": _parse_parameters(signature), "return_type": (re.search(r"\)\s*:\s*(.+)$", signature).group(1).strip() if re.search(r"\)\s*:\s*(.+)$", signature) else None), "local": is_local, "line_start": decl_idx + 1, "line_end": stop, "raw": "\n".join(lines[decl_idx:stop])})
    return procedures


def _extract_variables(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    variables = []
    in_var_block = False
    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if re.match(r"^(VAR|LOCAL VAR)$", stripped, re.I):
            in_var_block = True
            continue
        if in_var_block and stripped.upper() in {"BEGIN", "END;", "END."}:
            in_var_block = False
        if not in_var_block:
            continue
        m = VAR_RE.match(lines[idx])
        if m:
            variables.append({"name": (m.group(1) or m.group(2)).strip(), "nav_id": int(m.group(3)) if m.group(3) else None, "data_type": m.group(4).strip(), "line": idx + 1, "raw": stripped})
    return variables


def _extract_triggers(lines: list[str], ranges: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    triggers = []
    for section in ("PROPERTIES", "CONTROLS", "ACTIONS"):
        if section not in ranges:
            continue
        start, end = ranges[section]
        for idx in range(start + 1, end):
            m = re.match(r"^\s*(On[A-Za-z0-9]+)\s*=", lines[idx])
            if m:
                triggers.append({"name": m.group(1), "section": section, "line": idx + 1, "raw": lines[idx].strip()})
    return triggers


def _extract_controls(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    controls = []
    for idx in range(start + 1, end):
        m = CONTROL_RE.match(lines[idx])
        if m:
            controls.append({"id": int(m.group(1)), "indent": int(m.group(2)), "control_type": m.group(3), "line": idx + 1, "raw": lines[idx].strip()})
    return controls


def _extract_dependencies(text: str) -> list[dict[str, Any]]:
    """Extract explicit object references from C/AL variable declarations and object properties.

    This deliberately avoids searching arbitrary comments/source text, which would create
    misleading edges. These are syntactic references, not proof of runtime execution.
    """
    dependencies: dict[tuple[str, int], dict[str, Any]] = {}

    def add(object_type: str, object_id: int, line: int, evidence_kind: str) -> None:
        key = (object_type, object_id)
        entry = dependencies.setdefault(key, {"object_type": object_type, "object_id": object_id, "evidence": [], "evidence_kind": [], "confidence": "static"})
        if line not in entry["evidence"]:
            entry["evidence"].append(line)
        if evidence_kind not in entry["evidence_kind"]:
            entry["evidence_kind"].append(evidence_kind)

    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        var_match = VAR_RE.match(line)
        if var_match:
            data_type = var_match.group(4)
            ref = TYPE_REF_RE.search(data_type)
            if ref:
                kind = ref.group(1).title()
                add("Table" if kind == "Record" else kind, int(ref.group(2)), line_no, "variable_declaration")
        # NAV object-level properties that directly bind another object.
        prop = re.match(r"^(?:SourceTable|TableNo)\s*=\s*(\d+)", stripped, re.I)
        if prop:
            add("Table", int(prop.group(1)), line_no, "object_property")
        run_obj = re.match(r"^RunObject\s*=\s*(Table|Page|Codeunit|Report|XMLport|Query)\s+(\d+)", stripped, re.I)
        if run_obj:
            add(run_obj.group(1).title(), int(run_obj.group(2)), line_no, "object_property")
    return sorted(dependencies.values(), key=lambda x: (x["object_type"], x["object_id"]))


def parse_nav_text(text: str, source_file: str = "<memory>") -> dict[str, Any]:
    lines = text.splitlines()
    header = next((line for line in lines if line.strip()), "")
    match = OBJECT_RE.match(header.strip())
    if not match:
        raise ValueError(f"{source_file}: first non-empty line is not a recognized NAV OBJECT header")
    obj_type, obj_id, obj_name = match.group(1).title(), int(match.group(2)), match.group(3).strip()
    ranges = _section_ranges(lines)
    object_props = _extract_properties(lines, *ranges["OBJECT-PROPERTIES"]) if "OBJECT-PROPERTIES" in ranges else {}
    properties = _extract_properties(lines, *ranges["PROPERTIES"]) if "PROPERTIES" in ranges else {}
    fields = _extract_fields(lines, *ranges["FIELDS"]) if "FIELDS" in ranges else []
    keys = _extract_keys(lines, *ranges["KEYS"]) if "KEYS" in ranges else []
    controls = _extract_controls(lines, *ranges["CONTROLS"]) if "CONTROLS" in ranges else []
    actions = _extract_controls(lines, *ranges["ACTIONS"]) if "ACTIONS" in ranges else []
    # In NAV 2015 Page exports, the ACTIONS collection is nested inside PROPERTIES,
    # rather than always appearing as an object-level section.
    if "PROPERTIES" in ranges:
        ps, pe = ranges["PROPERTIES"]
        actions.extend(c for c in _extract_controls(lines, ps, pe) if c["control_type"].lower().startswith("action"))
    if "CONTROLS" in ranges:
        cs, ce = ranges["CONTROLS"]
        controls = [c for c in _extract_controls(lines, cs, ce) if not c["control_type"].lower().startswith("action")]
    code_range = ranges.get("CODE")
    procedures = _extract_procedures(lines, *code_range) if code_range else []
    variables = _extract_variables(lines, *code_range) if code_range else []
    triggers = _extract_triggers(lines, ranges)
    return {
        "parser_version": PARSER_VERSION,
        "object": {"type": obj_type, "id": obj_id, "name": obj_name, "modified": object_props.get("Modified", {}).get("value", "").lower() == "yes", "date": object_props.get("Date", {}).get("value"), "time": object_props.get("Time", {}).get("value"), "version_list": object_props.get("Version List", {}).get("value"), "classification": "unclassified"},
        "source": {"file": source_file, "line_count": len(lines), "sha256": _sha256(text.encode("utf-8")), "encoding": "utf-8 (decoded with replacement if invalid bytes)"},
        "sections": {k: {"line_start": v[0] + 1, "line_end": v[1] + 1} for k, v in ranges.items()},
        "properties": properties, "fields": fields, "keys": keys, "controls": controls, "actions": actions,
        "triggers": triggers, "variables": variables, "procedures": procedures,
        "dependencies": _extract_dependencies(text),
    }


def split_objects(text: str) -> list[tuple[re.Match[str], str]]:
    """Pisahkan teks yang berisi banyak objek NAV menjadi daftar objek individual.

    Mencari semua header ``OBJECT <type> <id> <name>`` dan mengembalikan
    pasangan (match, teks_objek) untuk setiap objek yang ditemukan.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(OBJECT_RE.finditer(text))
    objects = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        objects.append((m, text[m.start():end]))
    return objects


def parse_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    parsed = parse_nav_text(text, path.name)
    parsed["source"]["sha256"] = _sha256(raw)
    parsed["source"]["bytes"] = len(raw)
    return parsed


def parse_zip(zip_path: Path) -> list[dict[str, Any]]:
    """Parse every .txt NAV object export inside a ZIP file.

    Setiap member .txt dibaca, lalu dipisah menjadi objek-objek NAV individual
    (karena sebuah file .txt di dalam ZIP dapat berisi banyak objek yang
    digabungkan). Hasilnya adalah list parsed object dicts.

    Setiap parsed record carries ``source["zip_member"]`` dengan nama member
    sehingga asal objek dapat ditelusuri kembali ke arsip.
    """
    zip_path = Path(zip_path)
    results: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            if not name.lower().endswith(".txt"):
                continue
            raw = zf.read(name)
            text = raw.decode("utf-8-sig", errors="replace")
            file_sha256 = _sha256(raw)
            for match, obj_text in split_objects(text):
                parsed = parse_nav_text(obj_text, name)
                parsed["source"]["sha256"] = file_sha256
                parsed["source"]["bytes"] = len(raw)
                parsed["source"]["original_path"] = str(zip_path)
                parsed["source"]["zip_member"] = name
                results.append(parsed)
    return results
