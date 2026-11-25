from __future__ import annotations
import argparse
from pathlib import Path
from .ingest import ingest_directory

def main() -> None:
    parser = argparse.ArgumentParser(prog="nav-ai", description="NAV TXT ingestion and first-pass parser")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Ingest all .txt exports from a directory")
    ingest.add_argument("company", type=Path)
    #ingest.add_argument("--output", type=Path, default=Path("data/parsed"))
    #ingest.add_argument("--snapshots", type=Path, default=Path("data/snapshots"))
    args = parser.parse_args()
    if args.command == "ingest":
        input_directory = Path(f"data/input/{args.company}")
        output_directory = Path(f"data/parsed/{args.company}")
        snapshots_directory = Path(f"data/snapshots/{args.company}")
        result = ingest_directory(input_directory, output_directory, snapshots_directory)
        print(f"Parsed {result['object_count']} NAV object(s)")
        for obj in result["objects"]:
            o = obj["object"]
            print(f"- {o['type']} {o['id']} {o['name']}: "
                  f"{len(obj['fields'])} fields, {len(obj['procedures'])} procedures, "
                  f"{len(obj.get('variables', []))} variables, {len(obj['controls'])} controls, "
                  f"{len(obj.get('actions', []))} actions, {len(obj.get('dependencies', []))} dependencies")
        print(f"Output: {output_directory.resolve()}")

if __name__ == "__main__":
    main()
