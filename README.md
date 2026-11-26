# NAV 2015 Agent

**NAV Enterprise AI — Phase 1**

Deterministic first-pass parser untuk Microsoft Dynamics NAV 2015 C/AL object text exports (`.txt`). Ekstrak metadata, fields, keys, controls/actions, procedures, variables, triggers, dan syntactic object dependencies dari file export NAV. Mendukung input `.txt`, `.zip`, dan folder dengan skema parameter berbasis company (`--company`) yang konsisten di semua CLI tools.

---

## Apa Itu Project Ini?

Project ini adalah seperangkat tools CLI untuk menganalisis source code export Microsoft Dynamics NAV 2015 (C/AL). Tujuannya:

- **Ingest** — Parsing file export NAV (`.txt` dan `.zip`) menjadi inventory terstruktur (JSON + CSV).
- **Symbol Search** — Indexing semua simbol (objek, field, prosedur, variabel, trigger) ke SQLite untuk pencarian cepat.
- **Semantic Diff** — Membandingkan export company terhadap baseline untuk mendeteksi perubahan semantik.
- **Audit** — Verifikasi perubahan: apakah perubahan nyata (`REAL`), hanya whitespace (`WHITESPACE ONLY`), atau artefak batas file (`BOUNDARY ARTIFACT`).
- **Dependency Graph** — Membangun graph dependensi antar objek, klasifikasi objek (CUSTOM / MODIFIED_STANDARD / STANDARD_UNCHANGED), dan analisis impact (transitive dependents).
- **Clean** — Menghapus semua file hasil generate agar working tree kembali bersih.

Tidak memerlukan database eksternal, AI API, atau koneksi internet (Phase 1 milestone).

---

## Tools yang Tersedia

| Tool | Command | Kegunaan |
|------|---------|----------|
| **nav-ai** | `python -m nav_ai.cli ingest <company>` | Ingest export NAV (`.txt`/`.zip`/folder) → inventory JSON/CSV + snapshots |
| **nav-search** | `python -m nav_ai.search <company> index` | Bangun symbol index SQLite |
| | `python -m nav_ai.search <company> find <terms>` | Cari simbol dalam index |
| **nav-diff** | `python -m nav_ai.semantic_diff <company>` | Perbandingan semantik original vs company |
| **nav-audit** | `python -m nav_ai.audit <company>` | Audit perubahan (REAL / WHITESPACE ONLY / BOUNDARY ARTIFACT) |
| **nav-depgraph** | `python -m nav_ai.depgraph <company>` | Dependency graph + klasifikasi objek + impact analysis |
| **clean** | `python clean.py --execute` | Hapus semua file/folder hasil generate |

---

## Skema Parameter (`--company`)

Semua tools menggunakan konvensi `--company` yang konsisten. Path input dan output diturunkan otomatis dari nama company:

| Path | Template |
|------|----------|
| Input company | `data/input/<company>/` |
| Baseline (original) | `data/input/original/` |
| Parsed output | `data/parsed/<company>/` |
| Snapshots | `data/snapshots/<company>/` |
| Search DB | `data/search/<company>/search.db` |
| Reports | `reports/<company>/` |
| Depgraph DB | `data/depgraph/<company>/depgraph.db` |

`--company` wajib di semua tools. Argument `--db`, `--original`, `--output`, `--snapshots` yang lama telah dihapus atau diganti oleh skema berbasis company.

---

## Instalasi

```powershell
# Clone repo
git clone <repo-url>
cd nav2015-agent

# Install package (opsional)
pip install -e .

# Atau gunakan PYTHONPATH untuk development
$env:PYTHONPATH="src"
```

Dependensi utama: `pandas>=2.0`, `openpyxl>=3.1` (dev: `pytest>=8.0`).

---

## Pipeline End-to-End (Contoh)

```powershell
# 1. Ingest export company
python -m nav_ai.cli ingest datascrip

# 2. Build symbol index
python -m nav_ai.search datascrip index

# 3. Cari simbol
python -m nav_ai.search datascrip find --exact "Sales Header" --type Table

# 4. Semantic diff vs baseline
python -m nav_ai.semantic_diff datascrip --output diff.xlsx

# 5. Audit perubahan
python -m nav_ai.audit datascrip --output audit.xlsx

# 6. Dependency graph
python -m nav_ai.depgraph datascrip --diff diff.xlsx --excel NAV_Dependency_Report.xlsx

# 7. Impact analysis (transitive dependents)
python -m nav_ai.depgraph datascrip --impact "Codeunit 80.Sales-Post"

# 8. Clean generated files
python clean.py --execute
```

---

## Struktur Direktori

```
nav2015-agent/
├── clean.py                     # Hapus file hasil generate
├── nav2015_agent.md             # Dokumentasi teknis lengkap
├── README.md                    # Dokumentasi ini
├── pyproject.toml               # Konfigurasi paket
├── .gitignore
├── .env.example
├── src/
│   └── nav_ai/
│       ├── cli.py               # Entry point nav-ai
│       ├── ingest.py            # Orkesrasi ingest
│       ├── parser.py            # Parser inti NAV C/AL
│       ├── semantic_diff.py     # CLI nav-diff
│       ├── audit.py             # CLI nav-audit
│       ├── depgraph.py          # CLI nav-depgraph
│       └── search.py            # CLI nav-search
├── tests/                       # Unit tests (pytest)
├── data/
│   ├── input/original/          # Baseline export
│   ├── input/<company>/         # Export company
│   ├── parsed/<company>/        # Output ingest
│   ├── snapshots/<company>/     # Snapshot sumber
│   ├── search/<company>/        # Symbol index SQLite
│   └── depgraph/<company>/    # Dependency graph DB
├── extra/                       # Data demo
└── reports/<company>/           # Laporan diff/audit/depgraph
```

---

## Klasifikasi Objek (`nav-depgraph`)

Klasifikasi **tidak bergantung** pada `Modified=Yes` atau ID >= 50000. Hanya berdasarkan kehadiran di baseline + hasil diff:

| Kondisi | Klasifikasi |
|---------|-------------|
| Ada di baseline, tidak berubah | `STANDARD_UNCHANGED` |
| Ada di baseline, berubah | `MODIFIED_STANDARD` |
| Tidak ada di baseline (company only) | `CUSTOM` |
| Procedure baru pada standard object | `ADDED` |
| Procedure berubah pada standard object | `CHANGED` |

---

## Hasil Uji

```
44 passed, 4 failed
```

4 kegagalan pada `test_real_exports.py` disebabkan file `data/incoming/*.txt` yang sudah dihapus dari working tree (pre-existing, bukan karena perubahan kode).

Semua tes relevan lolos: parser, ingest, diff, audit, depgraph, search, zip support.

---

## Catatan

- Parser adalah **deterministic first-pass**, bukan full C/AL compiler. Tidak mengekstrak control-flow semantics, indirect calls, dynamic EVALUATE/record references, atau complete dependency resolution.
- `Modified=Yes` disimpan sebagai metadata tapi **tidak bukti** bahwa objek adalah custom atau modified-standard.
- Untuk detail parameter dan usage setiap tool, lihat `nav2015_agent.md`.