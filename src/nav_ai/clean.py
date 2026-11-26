#!/usr/bin/env python3
"""Clean semua file dan folder hasil generate dari tools NAV.

Hapus output dari nav-ai ingest, nav-search, nav-diff, nav-audit, dan nav-depgraph,
sambil melestarikan file sumber, konfigurasi, dan data input asli.

Usage:
    python -m nav_ai.clean              # Tampilkan daftar yang akan dihapus (dry-run)
    python -m nav_ai.clean --execute    # Hapus sebenarnya
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Folder yang akan dihapus (hasil generate)
TO_DELETE_DIRS = [
    ROOT / "data" / "parsed",
    ROOT / "data" / "snapshots",
    ROOT / "data" / "search",
    ROOT / "data" / "depgraph",
    ROOT / "reports" ,
]

# File yang akan dihapus (hasil generate)
TO_DELETE_FILES = [
    # Reports yang di-generate oleh nav-diff, nav-audit, nav-depgraph (versi baru)
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v4.xlsx",
    ROOT / "reports" / "NAV_Audit_Report_v3.xlsx",
    ROOT / "reports" / "NAV_Dependency_Report_v2.xlsx",
    # Reports CSV dari konversi xlsx (jika ada)
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v3_Dashboard.csv",
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v3_Object_Semantic_Summary.csv",
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v3_Procedure_Changes.csv",
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v3_Section_Changes.csv",
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v3_Object Semantic Summary.csv",
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v3_Procedure Changes.csv",
    ROOT / "reports" / "NAV_Semantic_Source_Diff_Report_v3_Section Changes.csv",
]

# File yang TIDAK boleh dihapus (dilestarikan)
PRESERVE = {
    ROOT / "data" / "input",
    ROOT / "src",
    ROOT / "tests",
    ROOT / "pyproject.toml",
    ROOT / "README.md",
    ROOT / ".gitignore",
    ROOT / ".env.example",
    ROOT / ".git",
    ROOT / ".pytest_cache",
    ROOT / ".venv",
}

def format_bytes(size: float, decimal: bool = False) -> str:
    step = 1000.0 if decimal else 1024.0
    units = ["B", "KB", "MB", "GB", "TB", "PB"] if decimal else ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    
    for unit in units:
        if abs(size) < step:
            return f"{size:.2f} {unit}"
        size /= step
    return f"{size:.2f} {'EB' if decimal else 'EiB'}"


def list_to_delete():
    """Kembalikan daftar path yang akan dihapus."""
    items = []
    for d in TO_DELETE_DIRS:
        if d.exists():
            items.append(("DIR", d))
    for f in TO_DELETE_FILES:
        if f.exists():
            items.append(("FILE", f))
    return items


def main(execute: bool = False) -> None:
    items = list_to_delete()

    if not items:
        print("Tidak ada file/folder hasil generate yang ditemukan.")
        return

    print("=" * 60)
    print("DAFTAR YANG AKAN DIHAPUS (clean)")
    print("=" * 60)
    total_size = 0
    for kind, path in items:
        size = 0
        if kind == "DIR":
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        size += f.stat().st_size
                        print(f"{f}  ({format_bytes(f.stat().st_size)})")
                    except OSError:
                        pass
        else:
            try:
                size = path.stat().st_size
                print(f"  [{kind}] {path}  ({format_bytes(f.stat().st_size)})")
            except OSError:
                pass
        total_size += size

    print("-" * 60)
    print(f"Total: ({format_bytes(total_size)})")
    print("=" * 60)

    if not execute:
        print("\n[DRY-RUN] Tidak ada yang dihapus. Jalankan dengan --execute untuk menghapus.")
        return

    for kind, path in items:
        try:
            if kind == "DIR":
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"  [DELETED] {path}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERROR]   {path}: {exc}")

    print("\nSelesai.")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Clean semua file hasil generate dari tools NAV")
    ap.add_argument("--execute", action="store_true", help="Hapus sebenarnya (default: dry-run)")
    args = ap.parse_args()
    main(execute=args.execute)
