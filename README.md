# NAV 2015 Agent

**NAV Enterprise AI — Phase 1**

Deterministic first-pass parser untuk Microsoft Dynamics NAV 2015 C/AL object text exports (`.txt`). Ekstrak metadata, fields, keys, controls/actions, procedures, variables, triggers, dan syntactic object dependencies dari file export NAV. Mendukung input `.txt`, `.zip`, dan folder dengan skema parameter berbasis company (`--company`) yang konsisten di semua CLI tools.

---

## Roadmap dan Status Proyek

Roadmap, progress, riwayat hasil pengujian, dan stocktake runtime test matrix dipelihara di [ROADMAP_TRACKER.md](./ROADMAP_TRACKER.md).

Tracker membedakan hasil automated test, static source audit, keputusan business policy, dan runtime validation. Angka pengujian historis tidak dianggap sebagai hasil full-suite terkini sampai suite dijalankan ulang pada HEAD branch.

---

## Apa Itu Project Ini?

Project ini adalah seperangkat tools CLI untuk menganalisis source code export Microsoft Dynamics NAV 2015 (C/AL). Tujuannya:

- **Ingest** — Parsing file export NAV (`.txt` dan `.zip`) menjadi inventory terstruktur (JSON + CSV).
- **Symbol Search** — Indexing semua simbol (objek, field, prosedur, variabel, trigger) ke SQLite untuk pencarian cepat.
- **Semantic Diff** — Membandingkan export company terhadap baseline untuk mendeteksi perubahan semantik.
- **Audit** — Verifikasi perubahan: apakah perubahan nyata (`REAL`), hanya whitespace (`WHITESPACE ONLY`), atau artefak batas file (`BOUNDARY ARTIFACT`).
- **Dependency Graph** — Membangun graph dependensi antar objek, klasifikasi objek (CUSTOM / MODIFIED_STANDARD / STANDARD_UNCHANGED), dan analisis impact (transitive dependents).\n- **Code Intelligence** — Query object/procedure, callers/callees, impact, symbol search, dan table READ/WRITE usage dari SQLite index yang sudah ada. Lihat [docs/CODE_INTELLIGENCE.md](./docs/CODE_INTELLIGENCE.md).
- **Clean** — Menghapus semua file hasil generate agar working tree kembali bersih.

Tidak memerlukan database eksternal, AI API, atau koneksi internet (Phase 1 milestone).

---

## Tools yang Tersedia

| Tool | Command | Kegunaan |
|------|---------|----------|
| **nav-ai** | `python -m nav_ai.cli ingest <company>` | Ingest export NAV (`.txt`/`.zip`/folder) → inventory JSON/CSV + snapshots |
| **nav-search** | `python -m nav_ai.search index --company <company>` | Bangun symbol index SQLite |
| | `python -m nav_ai.search find --company <company> <terms>` | Cari simbol dalam index |
| **nav-diff** | `python -m nav_ai.semantic_diff --company <company>` | Perbandingan semantik original vs company |
| **nav-audit** | `python -m nav_ai.audit --company <company>` | Audit perubahan (REAL / WHITESPACE ONLY / BOUNDARY ARTIFACT) |
| **nav-depgraph** | `python -m nav_ai.depgraph --company <company>` | Dependency graph + klasifikasi objek + impact analysis |\n| **nav-intel** | `nav-intel --company <company> impact \\\"Codeunit 80.PostItemJnlLine\\\"` | Evidence-oriented object, procedure, caller, impact and table queries |\n| | `nav-intel --company <company> document \\\"Codeunit 50107\\\" --source-root <TXT/ZIP> --analyze-conditions` | Generate business-process Markdown + JSON from dependency graph and source exports |
| **nav-intel discover** | `nav-intel --company <company> discover --limit 200` | Rank candidate business-process entry objects from the dependency graph |\n| **clean** | `python clean.py --execute` | Hapus semua file hasil generate |

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
python -m nav_ai.search index --company datascrip

# 3. Cari simbol
python -m nav_ai.search find --company datascrip --exact "Sales Header" --type Table

# 4. Semantic diff vs baseline
python -m nav_ai.semantic_diff --company datascrip --output diff.xlsx

# 5. Audit perubahan
python -m nav_ai.audit --company datascrip --output audit.xlsx

# 6. Dependency graph
python -m nav_ai.depgraph --company datascrip --diff diff.xlsx --excel NAV_Dependency_Report.xlsx

# 7. Impact analysis (transitive dependents)
python -m nav_ai.depgraph --company datascrip --impact "Codeunit 80.Sales-Post"

# 8. Clean generated files
python clean.py --execute
```

---

## Struktur Direktori

```
nav2015-agent/
├── clean.py
├── nav2015_agent.md
├── README.md
├── ROADMAP_TRACKER.md           # Roadmap, progress and validation tracker
├── pyproject.toml
├── .gitignore
├── .env.example
├── src/nav_ai/                  # Parser, ingest, diff, audit, depgraph, search
├── tests/                       # Unit tests
├── data/                        # Source inputs and generated indexes
└── reports/<company>/           # Analysis reports
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

## Catatan

- Parser adalah **deterministic first-pass**, bukan full C/AL compiler. Tidak mengekstrak control-flow semantics, indirect calls, dynamic EVALUATE/record references, atau complete dependency resolution.
- `Modified=Yes` disimpan sebagai metadata tapi **tidak bukti** bahwa objek adalah custom atau modified-standard.
- Untuk detail parameter dan usage setiap tool, lihat `nav2015_agent.md`.


### Automatic business-process candidate mapping

Rank candidate entry objects and group candidates whose CALL-reachable procedures use overlapping Tables:

```powershell
nav-intel --company datascrip --json discover --limit 300
nav-intel --company datascrip --json map-processes --limit 300 --min-similarity 0.25 --max-depth 5 --max-nodes 5000
```

The mapping follows indexed `CALL` edges to bounded reachable procedures and aggregates their `table_usage` records. Results include call paths, unresolved targets, traversal truncation and contributing procedures. A cluster is a related-candidate group for investigation, not a confirmed end-to-end business process.


### Generate the complete business-process inventory

Run a bounded automatic discovery, map candidates by transitive CALL-reachable Table usage, and create Markdown/JSON reports for every candidate whose source can be resolved:

```powershell
nav-intel --company datascrip inventory --source-root "data\\input\\datascrip\\datascrip.zip" --limit 100 --max-depth 5 --max-nodes 5000
```

Outputs are written under `reports/datascrip/business_process/`: `process_inventory.md/.json`, one `objects/<Type_ID>.md/.json` pair per successfully traced candidate, and cluster summaries under `clusters/`. Missing or ambiguous source is recorded per candidate; it does not abort the inventory. Use `--skip-conditions` for a faster first pass.


### Evidence-backed domain hints

The inventory attaches a heuristic domain hint (for example sales, purchase, inventory, warehouse, transfer, finance, production, service, integration or ownership) from the candidate object name, reachable procedure names and transitive Table names. The JSON preserves matched terms and their evidence category. Ties are reported as `ambiguous`; candidates without lexical evidence remain `unclassified`. A `moderate_heuristic` label is only a vocabulary-based hint, not confirmation of an actual business process. Validate vocabulary and classifications against Datascrip-specific objects before using them as authoritative process labels.
