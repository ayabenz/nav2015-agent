#!/usr/bin/env python3
"""Extract selected NAV C/AL objects from a TXT export or ZIP archive.

Example:
  python scripts/export_nav_objects.py \
    --input data/input/datascrip/datascrip.zip \
    --output reports/datascrip/ownership \
    --objects Table:50035 Table:14 Codeunit:50107 Codeunit:50035
"""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

OBJECT_RE = re.compile(
    r"^OBJECT\s+(Table|Page|Codeunit|Report|XMLport|MenuSuite|Form|Dataport|Query)\s+(\d+)\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def iter_source_texts(source: Path):
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith(".txt"):
                    raw = archive.read(name)
                    yield name, raw.decode("utf-8-sig", errors="replace")
    elif source.is_file() and source.suffix.lower() == ".txt":
        yield source.name, source.read_text(encoding="utf-8-sig", errors="replace")
    else:
        raise FileNotFoundError(f"Input must be an existing .txt or .zip file: {source}")


def extract_objects(text: str):
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(OBJECT_RE.finditer(normalized))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        yield (match.group(1).title(), int(match.group(2))), normalized[match.start():end]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract selected NAV objects from a TXT or ZIP export.")
    parser.add_argument("--input", required=True, type=Path, help="NAV AllObjects.txt or ZIP containing TXT exports")
    parser.add_argument("--output", required=True, type=Path, help="Directory for extracted object files")
    parser.add_argument("--objects", nargs="+", required=True, help="Object selectors, e.g. Table:50035 Codeunit:50107")
    args = parser.parse_args()

    requested = set()
    for value in args.objects:
        try:
            object_type, object_id = value.split(":", 1)
            requested.add((object_type.title(), int(object_id)))
        except ValueError as exc:
            parser.error(f"Invalid object selector {value!r}; expected Type:ID")

    found: dict[tuple[str, int], tuple[str, str]] = {}
    for source_name, text in iter_source_texts(args.input):
        for key, object_text in extract_objects(text):
            if key not in requested:
                continue
            if key in found:
                raise RuntimeError(
                    f"Duplicate object {key[0]} {key[1]} found in "
                    f"{found[key][0]!r} and {source_name!r}; refusing ambiguous export."
                )
            found[key] = (source_name, object_text)

    missing = sorted(requested - set(found))
    if missing:
        missing_text = ", ".join(f"{kind}:{object_id}" for kind, object_id in missing)
        raise SystemExit(f"Objects not found in {args.input}: {missing_text}")

    args.output.mkdir(parents=True, exist_ok=True)
    for (object_type, object_id), (source_name, object_text) in sorted(found.items()):
        destination = args.output / f"{object_type}_{object_id}.txt"
        destination.write_text(object_text.rstrip() + "\n", encoding="utf-8")
        print(f"{object_type} {object_id}: {source_name} -> {destination}")

    print(f"Extracted {len(found)} object(s) to {args.output}")


if __name__ == "__main__":
    main()
