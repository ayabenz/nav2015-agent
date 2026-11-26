#!/usr/bin/env python3
"""Find and export NAV objects that reference Codeunit 50107 / Block Stocktake."""
from __future__ import annotations

import argparse
import csv
import re
import zipfile
from pathlib import Path

OBJECT_RE = re.compile(
    r"^OBJECT\s+(Table|Page|Codeunit|Report|XMLport|MenuSuite|Form|Dataport|Query)\s+(\d+)\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
REFERENCE_PATTERNS = {
    "Codeunit 50107": re.compile(r'(?i)\b(?:CODEUNIT\s*::\s*|Codeunit\s+)"?50107"?\b'),
    "BlockStocktakeSalesHeader": re.compile(r"(?i)\bBlockStocktakeSalesHeader\b"),
    "BlockStocktakePurchaseHeader": re.compile(r"(?i)\bBlockStocktakePurchaseHeader\b"),
    "BlockStocktakeTransferHeader": re.compile(r"(?i)\bBlockStocktakeTransferHeader\b"),
    "BlockStocktakeWarehouseReceiptHeader": re.compile(r"(?i)\bBlockStocktakeWarehouseReceiptHeader\b"),
}

def source_texts(path: Path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith(".txt"):
                    yield name, archive.read(name).decode("utf-8-sig", errors="replace")
    elif path.suffix.lower() == ".txt":
        yield path.name, path.read_text(encoding="utf-8-sig", errors="replace")
    else:
        raise SystemExit(f"Unsupported source: {path}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--target-codeunit-id", type=int, default=50107)
    args = ap.parse_args()
    target_id = args.target_codeunit_id
    patterns = {
        f"Codeunit {target_id}": re.compile(
            rf'(?i)\\b(?:CODEUNIT\\s*::\\s*|Codeunit\\s+)"?{target_id}"?\\b'
        ),
        f"Codeunit.RUN({target_id})": re.compile(
            rf"(?i)\\bCODEUNIT\\s*\\.\\s*RUN\\s*\\(\\s*{target_id}\\b"
        ),
    }
    if target_id == 90:
        patterns["Purch.-Post symbol"] = re.compile(r'(?i)CODEUNIT\\s*::\\s*"Purch\\.-Post"')
    if target_id == 50107:
        patterns.update(REFERENCE_PATTERNS)
    found = {}
    for source_name, raw in source_texts(args.input):
        text = raw.replace("\r\n", "\n").replace("\r", "\n")
        matches = list(OBJECT_RE.finditer(text))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[m.start():end]
            key = (m.group(1).title(), int(m.group(2)))
            if key == ("Codeunit", target_id):
                continue
            hits = [label for label, pattern in patterns.items() if pattern.search(body)]
            if hits:
                if key in found:
                    if found[key]["body"] != body:
                        raise SystemExit(f"Conflicting duplicate object {key}")
                    found[key]["hits"] = sorted(set(found[key]["hits"] + hits))
                else:
                    found[key] = {"source": source_name, "name": m.group(3), "body": body, "hits": hits}
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = args.output / "callers_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["object_type", "object_id", "object_name", "source_file", "matched_references", "export_file"])
        for (kind, oid), item in sorted(found.items()):
            filename = f"{kind}_{oid}.txt"
            (args.output / filename).write_text(item["body"].rstrip() + "\n", encoding="utf-8")
            w.writerow([kind, oid, item["name"], item["source"], ";".join(item["hits"]), filename])
            print(f"{kind} {oid} {item['name']}: {', '.join(item['hits'])}")
    print(f"Exported {len(found)} caller objects; manifest: {manifest}")

if __name__ == "__main__":
    main()
