"""Extended NAV entry-point evidence: typed calls, RUN targets, subscribers,
Job Queue contracts, and individual Table field triggers.

All results are static source/configuration evidence, never runtime invocation proof.
"""
from __future__ import annotations

import re
from typing import Any

from .entrypoint_intelligence import _source_files
from .parser import OBJECT_RE, split_objects

SECTION_RE = re.compile(r"^\s{2,}([A-Z][A-Z0-9 -]*)\s*$")
VAR_RE = re.compile(r'^\s*(?:"([^"]+)"|([A-Za-z_][\w ]*?))(?:@\d+)?\s*:\s*(Codeunit|Page|Report|XMLport|Query|Record)\s+(\d+)\s*;', re.I)
PROC_RE = re.compile(r"^\s*(?:LOCAL\s+)?PROCEDURE\s+([^ (]+)", re.I)
PUBLISHER_RE = re.compile(r"\[(IntegrationEvent|BusinessEvent|InternalEvent)\s*\(", re.I)
EVENT_RE = re.compile(r"""EventSubscriber\s*\(\s*ObjectType\s*::\s*(Codeunit|Page|Table|Report|XMLport)\s*,\s*(?:\1\s*::\s*)?(\d+|"([^"]+)")\s*,\s*'([^']+)'""", re.I)
RUN_RE = re.compile(r"\b(CODEUNIT|PAGE|REPORT|XMLPORT)\s*\.\s*RUN(?:MODAL)?\s*\(\s*([^,;)]+)", re.I)
ASSIGN_RE = re.compile(r'\b([A-Za-z_][\w ]*)\s*:=\s*(\d+)\s*;', re.I)
FIELD_START_RE = re.compile(r'^\s*\{\s*(\d+)\s*;\s*;\s*([^;]+?)\s*;', re.I)
TRIGGER_LINE_RE = re.compile(r"\b(OnValidate|OnLookup|OnDrillDown|OnAssistEdit)\s*=\s*(.*)$", re.I)

def _mask(text: str) -> str:
    text = re.sub(r"'(?:[^']|'')*'", " ", text)
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r"\{[^{}]*\}", " ", text)

def discover_extended_entrypoints(source_roots: list[str], graph=None) -> dict[str, Any]:
    typed_calls, dynamic_runs, subscribers, publishers, job_queue, field_triggers = [], [], [], [], [], []
    object_sources: list[dict[str, Any]] = []
    for root in source_roots:
        for display, label, source in _source_files(root):
            for match, block in split_objects(source):
                hm = OBJECT_RE.match(match.group(0).strip())
                if not hm:
                    continue
                typ, oid, name = hm.group(1).title(), int(hm.group(2)), hm.group(3).strip()
                node = f"{typ} {oid}"
                offset = source.count("\n", 0, match.start())
                lines = block.splitlines()
                section = ""
                vars_by_name: dict[str, dict[str, Any]] = {}
                current_proc = "<object>"
                pending_publisher = None
                proc_vars_by_scope: dict[str, dict[str, Any]] = {}
                for i, line in enumerate(lines):
                    sm = SECTION_RE.match(line)
                    if sm:
                        section = sm.group(1).strip()
                    publisher_match = PUBLISHER_RE.search(line)
                    if publisher_match:
                        pending_publisher = publisher_match.group(1)
                    pm = PROC_RE.match(line)
                    if pm:
                        current_proc = pm.group(1).strip('"')
                        proc_vars_by_scope.setdefault(current_proc, {})
                        if pending_publisher:
                            publishers.append({
                                "publisher_object": node, "publisher_object_type": typ,
                                "publisher_object_id": oid, "event_name": current_proc,
                                "event_kind": pending_publisher, "source": display,
                                "line": i + 1 + offset, "evidence": "event_publisher_attribute",
                                "runtime_raised": False,
                            })
                            pending_publisher = None
                    vm = VAR_RE.match(line)
                    if vm:
                        vname = (vm.group(1) or vm.group(2)).strip()
                        kind = vm.group(3).title().replace("Xmlport", "XMLport")
                        var = {"name": vname, "type": kind, "object_id": int(vm.group(4)), "line": i + 1 + offset, "scope": current_proc}
                        (proc_vars_by_scope.setdefault(current_proc, {}) if current_proc != "<object>" else vars_by_name)[vname.casefold()] = var
                    # EventSubscriber attributes are commonly in procedure declaration attributes.
                    em = EVENT_RE.search(line)
                    if em:
                        target_type = em.group(1).title()
                        target_id = int(em.group(2)) if em.group(2).isdigit() else None
                        target_name = em.group(3)
                        subscribers.append({
                            "subscriber_object": node, "subscriber_procedure": current_proc,
                            "event_object_type": target_type, "event_object_id": target_id,
                            "event_object_name": target_name, "event_name": em.group(4),
                            "source": display, "line": i + 1 + offset,
                            "evidence": "EventSubscriber_attribute", "runtime_invoked": False,
                        })
                    if typ == "Table" and section == "FIELDS":
                        fm = FIELD_START_RE.match(line)
                        if fm:
                            field_id, field_name = int(fm.group(1)), fm.group(2).strip().strip('"')
                            # Scan this field's brace block only; do not absorb other fields.
                            depth, end = 0, i
                            while end < len(lines):
                                depth += lines[end].count("{") - lines[end].count("}")
                                if end > i and depth <= 0:
                                    break
                                end += 1
                            for j in range(i, min(end + 1, len(lines))):
                                tm = TRIGGER_LINE_RE.search(lines[j])
                                if tm:
                                    trigger_body = [tm.group(2)]
                                    k = j + 1
                                    if "BEGIN" in tm.group(2).upper():
                                        d = 0
                                        while k < min(end + 1, len(lines)):
                                            trigger_body.append(lines[k])
                                            clean = _mask(lines[k]).upper()
                                            d += len(re.findall(r"\bBEGIN\b", clean)) - len(re.findall(r"\bEND\b", clean))
                                            if d <= 0 and re.search(r"\bEND\s*;?", clean):
                                                break
                                            k += 1
                                    field_triggers.append({
                                        "entry_id": f"{node}.Field[{field_id}].{tm.group(1)}",
                                        "object": node, "object_name": name, "field_id": field_id,
                                        "field_name": field_name, "trigger": tm.group(1),
                                        "source": display, "line_start": j + 1 + offset,
                                        "line_end": k + 1 + offset, "body": "\n".join(trigger_body),
                                        "evidence": "table_field_trigger_body", "runtime_invoked": False,
                                    })
                object_sources.append({"node": node, "name": name, "source": display, "text": block,
                                       "object_vars": vars_by_name})
                # Second pass uses object + procedure-local declarations and literal assignments.
                all_vars = dict(vars_by_name)
                for scoped_vars in proc_vars_by_scope.values():
                    for variable_key, variable in scoped_vars.items():
                        previous = all_vars.get(variable_key)
                        if previous is None:
                            all_vars[variable_key] = variable
                        elif (previous["type"], previous["object_id"]) != (variable["type"], variable["object_id"]):
                            all_vars.pop(variable_key, None)
                clean = _mask(block)
                literal_values = {m.group(1).strip().casefold(): int(m.group(2)) for m in ASSIGN_RE.finditer(clean)}
                for m in RUN_RE.finditer(clean):
                    kind = m.group(1).title().replace("Xmlport", "XMLport")
                    expr = m.group(2).strip()
                    normalized_expr = re.sub(r"^(?:CODEUNIT|PAGE|REPORT|XMLPORT)\\s*::\\s*", "", expr, flags=re.I).strip()
                    variable_name = normalized_expr.strip('"')
                    var = all_vars.get(variable_name.casefold())
                    value = int(normalized_expr) if normalized_expr.isdigit() else literal_values.get(variable_name.casefold())
                    resolved = None
                    reason = None
                    if var and var["type"] == kind:
                        resolved = f"{kind} {var['object_id']}"
                        evidence = "typed_variable_object_reference"
                    elif value is not None:
                        resolved = f"{kind} {value}"
                        evidence = "constant_or_assigned_numeric_run_target"
                    elif normalized_expr.startswith('"') and normalized_expr.endswith('"') and graph is not None:
                        object_rows = graph.execute(
                            "SELECT node FROM objects WHERE type=? COLLATE NOCASE AND name=? COLLATE NOCASE",
                            (kind, variable_name),
                        ).fetchall()
                        if len(object_rows) == 1:
                            resolved = str(object_rows[0][0])
                            evidence = "explicit_named_object_reference"
                        else:
                            reason = "Named RUN target is not unique in graph metadata"
                            evidence = "unresolved_dynamic_run"
                    else:
                        reason = "RUN target is variable/expression without a unique static numeric or typed-object resolution"
                        evidence = "unresolved_dynamic_run"
                    dynamic_runs.append({
                        "caller_object": node, "run_kind": kind, "expression": expr,
                        "resolved_target": resolved, "resolution_evidence": evidence,
                        "unresolved_reason": reason, "source": display,
                        "runtime_executed": False,
                    })
                # Typed receiver calls: receiver.Method(...); match method on declared target object.
                for receiver, var in all_vars.items():
                    if var["type"] not in {"Codeunit", "Page", "Report", "XMLport", "Query"}:
                        continue
                    for call in re.finditer(r"\b" + re.escape(receiver) + r"\s*\.\s*([A-Za-z_][\w]*)\s*(?:\(|;)", clean, re.I):
                        target = f"{var['type']} {var['object_id']}"
                        method = call.group(1)
                        target_node = None
                        if graph is not None:
                            rows = graph.execute("SELECT node FROM procedures WHERE object_node=? COLLATE NOCASE AND name=? COLLATE NOCASE", (target, method)).fetchall()
                            if len(rows) == 1:
                                target_node = str(rows[0][0])
                        typed_calls.append({
                            "caller_object": node, "caller_scope": var["scope"],
                            "receiver": var["name"], "receiver_type": var["type"],
                            "target_object": target, "method": method,
                            "target_procedure": target_node,
                            "resolution": "unique_typed_procedure" if target_node else "typed_object_resolved_procedure_unresolved",
                            "source": display, "runtime_executed": False,
                        })
                # Job Queue contracts: identify standard Job Queue Entry consumers and
                # explicit object fields/dispatcher references, not live configured rows.
                if typ == "Table" and oid == 472:
                    job_queue.append({"kind": "standard_job_queue_entry_table", "object": node,
                                      "source": display, "evidence": "Table 472 source export",
                                      "runtime_configured": False})
                if re.search(r"\bJob\s*Queue\s*Entry\b|\bJobQueueEntry\b", block, re.I) or re.search(r"\bCODEUNIT\s*::\s*448\b", block, re.I):
                    job_queue.append({"kind": "job_queue_source_consumer_candidate", "object": node,
                                      "source": display, "evidence": "Job Queue Entry / Codeunit 448 source reference",
                                      "runtime_configured": False})
    # Attach static graph callers to publisher procedures as candidate call sites.
    for publisher in publishers:
        publisher_node = None
        if graph is not None:
            rows = graph.execute(
                "SELECT node FROM procedures WHERE object_node=? COLLATE NOCASE AND name=? COLLATE NOCASE",
                (publisher["publisher_object"], publisher["event_name"]),
            ).fetchall()
            if len(rows) == 1:
                publisher_node = str(rows[0][0])
        callers = []
        if publisher_node:
            callers = [
                str(row[0]) for row in graph.execute(
                    "SELECT src FROM edges WHERE dst=? COLLATE NOCASE AND kind='CALL' ORDER BY src",
                    (publisher_node,),
                ).fetchall()
            ]
        publisher["procedure_node"] = publisher_node
        publisher["static_callers"] = callers
        publisher["call_site_evidence"] = "dependency_graph_CALL_edge" if callers else "no_indexed_CALL_callers"
        publisher["runtime_invoked"] = False
    # Link subscriber attributes to matching publisher declarations where identity is unique.
    for subscriber in subscribers:
        target_id = subscriber.get("event_object_id")
        target_name = subscriber.get("event_object_name")
        target_type = subscriber.get("event_object_type")
        if target_id is None and target_name and graph is not None:
            rows = graph.execute(
                "SELECT id FROM objects WHERE type=? COLLATE NOCASE AND name=? COLLATE NOCASE",
                (target_type, target_name),
            ).fetchall()
            if len(rows) == 1:
                target_id = int(rows[0][0])
        matches = [
            publisher for publisher in publishers
            if publisher["publisher_object_type"].casefold() == str(target_type).casefold()
            and publisher["publisher_object_id"] == target_id
            and publisher["event_name"].casefold() == str(subscriber["event_name"]).casefold()
        ]
        subscriber["publisher_matches"] = matches
        subscriber["publisher_declaration_found"] = bool(matches)
        subscriber["publisher_invocation_proven"] = False
    # Attach graph existence to statically resolved RUN object targets.
    for item in dynamic_runs:
        if item["resolved_target"] and graph is not None:
            rows = graph.execute("SELECT node FROM objects WHERE node=? COLLATE NOCASE", (item["resolved_target"],)).fetchall()
            item["target_indexed"] = len(rows) == 1
        else:
            item["target_indexed"] = None
    return {
        "typed_variable_calls": typed_calls,
        "dynamic_run_targets": dynamic_runs,
        "event_subscribers": subscribers,
        "event_publishers": publishers,
        "job_queue_evidence": job_queue,
        "table_field_triggers": field_triggers,
        "counts": {"typed_variable_calls": len(typed_calls), "dynamic_run_targets": len(dynamic_runs),
                   "event_subscribers": len(subscribers), "event_publishers": len(publishers), "job_queue_evidence": len(job_queue),
                   "table_field_triggers": len(field_triggers)},
        "semantics": {"runtime_executed": False, "job_queue_runtime_configured": False,
                      "limitations": [
                          "Typed variable resolution requires explicit object-ID declarations; aliases and dynamic object IDs remain unresolved.",
                          "EventSubscriber attributes prove subscription declarations, not event publication or invocation.",
                          "Job Queue source references do not enumerate configured Job Queue Entry records or prove scheduling.",
                          "Table field trigger bodies are source declarations; field validation/invocation depends on NAV execution path.",
                          "Procedure-local variable parsing is conservative and currently recognizes declarations visible in the containing object text."
                      ]}
    }

def map_job_queue_snapshot(snapshot: dict[str, Any], graph) -> dict[str, Any]:
    """Map an explicitly supplied Job Queue Entry configuration snapshot to NAV objects.

    Expected input: {"snapshot_at": "...", "entries": [{"entry_no": "...",
    "object_type": "Codeunit", "object_id": 50000, ...}]}. Parameter String is
    deliberately redacted; this is configuration evidence, not execution telemetry.
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("entries"), list):
        raise ValueError("Job Queue snapshot must be an object with an entries array")
    mapped = []
    for index, row in enumerate(snapshot["entries"]):
        if not isinstance(row, dict):
            mapped.append({"row_index": index, "resolution": "invalid_row"})
            continue
        raw_type = str(row.get("object_type", "")).strip()
        raw_id = row.get("object_id")
        try:
            object_id = int(raw_id)
        except (TypeError, ValueError):
            object_id = None
        target_type = raw_type.title().replace("Xmlport", "XMLport")
        target = f"{target_type} {object_id}" if object_id is not None else None
        valid_types = {"Codeunit", "Page", "Report", "XMLport"}
        target_rows = graph.execute(
            "SELECT node FROM objects WHERE type=? COLLATE NOCASE AND id=?",
            (target_type, object_id),
        ).fetchall() if target and target_type in valid_types else []
        target_node = str(target_rows[0][0]) if len(target_rows) == 1 else None
        procedure_count = 0
        if target_node:
            procedure_count = graph.execute(
                "SELECT COUNT(*) FROM procedures WHERE object_node=? COLLATE NOCASE",
                (target_node,),
            ).fetchone()[0]
        parameter = row.get("parameter_string")
        mapped.append({
            "row_index": index,
            "entry_no": row.get("entry_no"),
            "object_type": target_type,
            "object_id": object_id,
            "target_object": target_node,
            "target_indexed": bool(target_node),
            "target_procedure_count": int(procedure_count),
            "status": row.get("status"),
            "earliest_start_datetime": row.get("earliest_start_datetime"),
            "next_run_datetime": row.get("next_run_datetime"),
            "recurring": row.get("recurring"),
            "parameter_string_present": bool(parameter),
            "parameter_string_length": len(str(parameter)) if parameter is not None else 0,
            "resolution": "unique_object_match" if target_node else "unresolved_or_missing_target",
            "configuration_snapshot_only": True,
            "runtime_executed": False,
        })
    return {
        "snapshot_at": snapshot.get("snapshot_at"),
        "company": snapshot.get("company"),
        "entry_count": len(mapped),
        "entries": mapped,
        "semantics": {
            "configuration_snapshot_only": True,
            "runtime_executed": False,
            "limitations": [
                "A configured or enabled Job Queue Entry does not prove that its next run occurred or completed.",
                "Parameter String values are intentionally redacted; only presence and length are retained.",
                "Historical execution requires separate Job Queue Log / telemetry evidence.",
                "The supplied snapshot must be exported from the intended NAV company and time window."
            ]
        }
    }
