from __future__ import annotations
import csv, hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .parser import parse_file, parse_zip, PARSER_VERSION

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def ingest_directory(input_dir: Path, output_dir: Path, snapshots_dir: Path) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    objects = []
    manifest_files = []

    def _register(path: Path, parsed: dict[str, Any]) -> None:
        source_hash = sha256_file(path)
        snapshot = snapshots_dir / source_hash[:16] / path.name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not snapshot.exists():
            shutil.copy2(path, snapshot)
        parsed["source"]["original_path"] = str(path)
        parsed["source"]["snapshot_path"] = str(snapshot)
        objects.append(parsed)
        manifest_files.append({
            "file": str(path.relative_to(input_dir)),
            "sha256": source_hash,
            "bytes": path.stat().st_size,
            "snapshot": str(snapshot),
            "object_type": parsed["object"]["type"],
            "object_id": parsed["object"]["id"],
            "object_name": parsed["object"]["name"],
        })

    def _collect_paths(root: Path) -> list[Path]:
        """Kumpulkan semua path .txt dan .zip dari file tunggal, ZIP, atau direktori."""
        if root.is_file():
            return [root] if root.suffix.lower() in (".txt", ".zip") else []
        if root.is_dir():
            return sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in (".txt", ".zip")])
        return []

    paths = _collect_paths(input_dir)
    if not paths:
        raise FileNotFoundError(f"No .txt or .zip files found under {input_dir}")

    for path in paths:
        if path.suffix.lower() == ".zip":
            for parsed in parse_zip(path):
                _register(path, parsed)
        else:
            _register(path, parse_file(path))
    seen = set()
    for obj in objects:
        key = (obj["object"]["type"], obj["object"]["id"])
        if key in seen:
            raise ValueError(f"Duplicate object in input: {key}. Use one authoritative export per object.")
        seen.add(key)
    inventory = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parser_version": PARSER_VERSION,
        "object_count": len(objects),
        "objects": objects,
    }
    (output_dir / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "inventory.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "object_type", "object_id", "object_name", "modified", "date",
            "version_list", "field_count", "key_count", "control_count", "action_count",
            "procedure_count", "variable_count", "trigger_count", "dependency_count", "source_file", "sha256"
        ])
        writer.writeheader()
        for obj in objects:
            o, s = obj["object"], obj["source"]
            writer.writerow({
                "object_type": o["type"], "object_id": o["id"], "object_name": o["name"],
                "modified": o["modified"], "date": o["date"], "version_list": o["version_list"],
                "field_count": len(obj["fields"]), "key_count": len(obj["keys"]),
                "control_count": len(obj["controls"]), "action_count": len(obj.get("actions", [])),
                "procedure_count": len(obj["procedures"]), "variable_count": len(obj.get("variables", [])),
                "trigger_count": len(obj["triggers"]), "dependency_count": len(obj.get("dependencies", [])),
                "source_file": s["file"], "sha256": s["sha256"],
            })
    # Flat dependency edge list for later graph loading and review.
    with (output_dir / "dependencies.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_type", "source_id", "source_name", "target_type", "target_id", "evidence_kind", "evidence_lines", "confidence"])
        writer.writeheader()
        for obj in objects:
            for dep in obj.get("dependencies", []):
                writer.writerow({
                    "source_type": obj["object"]["type"], "source_id": obj["object"]["id"], "source_name": obj["object"]["name"],
                    "target_type": dep["object_type"], "target_id": dep["object_id"],
                    "evidence_kind": ";".join(dep.get("evidence_kind", [])),
                    "evidence_lines": ";".join(str(x) for x in dep.get("evidence", [])),
                    "confidence": dep.get("confidence", "static"),
                })

    with (output_dir / "symbols.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["object_type", "object_id", "object_name", "symbol_type", "symbol_name", "signature", "line_start", "line_end", "is_local"])
        writer.writeheader()
        for obj in objects:
            o = obj["object"]
            for proc in obj.get("procedures", []):
                writer.writerow({"object_type": o["type"], "object_id": o["id"], "object_name": o["name"], "symbol_type": "procedure", "symbol_name": proc["name"], "signature": proc["signature"], "line_start": proc["line_start"], "line_end": proc["line_end"], "is_local": proc["local"]})
            for var in obj.get("variables", []):
                writer.writerow({"object_type": o["type"], "object_id": o["id"], "object_name": o["name"], "symbol_type": "variable", "symbol_name": var["name"], "signature": var["data_type"], "line_start": var["line"], "line_end": var["line"], "is_local": ""})

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parser_version": PARSER_VERSION,
        "input_directory": str(input_dir),
        "files": manifest_files,
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return inventory
