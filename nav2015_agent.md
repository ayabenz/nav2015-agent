# NAV Enterprise AI — Phase 1

Dokumentasi lengkap untuk proyek **NAV 2015 TXT Source Ingestion and Symbol/Dependency Extraction**.

---

## 1. Ringkasan Proyek

| Item | Nilai |
|------|-------|
| Nama paket | `nav2015-agent` |
| Versi | 0.2.0 (`pyproject.toml`) / 0.1.0 (`__init__.py`) |
| Bahasa | Python 3.11+ |
| Dependensi | `pandas>=2.0`, `openpyxl>=3.1` (dev: `pytest>=8.0`) |
| Deskripsi | Deterministic first-pass parser untuk Microsoft Dynamics NAV 2015 C/AL object text exports (`.txt`). Ekstrak metadata, fields, keys, controls/actions, procedures, variables, triggers, dan syntactic object dependencies. Output: JSON + CSV inventory, symbol index, dan dependency edge list. |
| Constraint | Tidak memerlukan database, AI API, atau koneksi internet (Phase 1 milestone). |

---

## 2. Struktur Direktori

```
nav2015-agent/
├── clean.py                     # Tools untuk menghapus file hasil generate
├── nav2015_agent.md             # Dokumentasi ini
├── pyproject.toml               # Konfigurasi paket dan entry points
├── README.md                    # Dokumentasi asli proyek
├── .gitignore                   # Git ignore
├── .env.example                 # Contoh file environment (tidak diperlukan Phase 1)
├── Roadmap_Tracker.xlsx         # Roadmap pelacakan
├── src/
│   └── nav_ai/
│       ├── __init__.py
│       ├── cli.py               # CLI: nav-ai ingest
│       ├── ingest.py            # Orkesrasi ingest (txt + zip)
│       ├── parser.py            # Parser inti NAV C/AL (.txt dan .zip)
│       ├── semantic_diff.py     # CLI: nav-diff (perbandingan original vs company)
│       ├── audit.py             # CLI: nav-audit (verifikasi perubahan)
│       ├── depgraph.py          # CLI: nav-depgraph (dependency graph + klasifikasi)
│       └── search.py            # CLI: nav-search (symbol index dan pencarian)
├── tests/
│   ├── samples.py               # Synthetic NAV objects untuk tes
│   ├── test_audit.py
│   ├── test_depgraph.py
│   ├── test_depgraph_cli.py
│   ├── test_ingest_cli.py
│   ├── test_parser.py
│   ├── test_real_exports.py     # Memerlukan file data/incoming/*.txt (sudah dihapus)
│   ├── test_search.py
│   └── test_semantic_diff.py
├── data/
│   ├── input/                   # Data asli (git-ignored)
│   │   ├── original/original.zip   # Baseline (~4168 objek)
│   │   └── datascrip/datascrip.zip # Company export (~4696 objek)
│   ├── parsed/<company>/        # Output ingest (dibuat saat dijalankan)
│   ├── snapshots/<company>/     # Salinan byte-for-byte (dibuat saat dijalankan)
│   ├── search/<company>/        # Symbol index SQLite (dibuat saat dijalankan)
│   ├── depgraph/<company>/      # Dependency graph DB (dibuat saat dijalankan)
│   └── comparison/              # Kosong (placeholder)
├── extra/                       # Data demo/tambahan
│   ├── all_original.txt
│   ├── datascrip.zip
│   └── NAV_Enterprise_AI_Phase1_Starter.zip
├── reports/<company>/           # Laporan yang di-generate (beberapa git-ignored)
│   ├── archive/                 # Laporan versi lama
│   ├── .gitkeep
│   └── ...
└── .git/
```

---

## 3. Modul Sumber (`src/nav_ai/`)

| Modul | CLI Command | Tanggung Jawab |
|-------|-------------|----------------|
| `parser.py` | — | Parser inti. Ekstrak OBJECT header, sections, fields, keys, controls, actions, triggers, procedures, variables, dependencies. Mendukung `.txt` dan `.zip`. |
| `ingest.py` | `nav-ai ingest` | Orkesrasi ingest. Memindai folder `.txt`/`.zip`, parse setiap objek, buat snapshot immutable, tulis `inventory.json`, `inventory.csv`, `dependencies.csv`, `symbols.csv`, `run_manifest.json`. |
| `semantic_diff.py` | `nav-diff` | Heuristic semantic diff antara baseline (`data/input/original/`) dan company (`data/input/<company>/`). Bandingkan prosedur, trigger, structural sections. Output Excel. |
| `audit.py` | `nav-audit` | Audit perubahan yang terdeteksi. Klasifikasi sebagai `REAL`, `WHITESPACE ONLY`, atau `BOUNDARY ARTIFACT` menggunakan `difflib.SequenceMatcher`. |
| `depgraph.py` | `nav-depgraph` | Dependency graph engine. Klasifikasi objek (CUSTOM / MODIFIED_STANDARD / STANDARD_UNCHANGED), buat SQLite DB + Excel report. Dukung `--impact` untuk transitive query. |
| `search.py` | `nav-search` | Symbol indexer dan searcher (SQLite). Kinds: object, field, procedure, variable, trigger. Dukung exact match, keyword, by ID, type, object-id. |
| `cli.py` | `nav-ai` | Entry point untuk `nav-ai ingest`. |
| `clean.py` | — | Clean tool (dry-run + `--execute`) untuk menghapus file generated. |

---

## 4. CLI Tools dan Usage

### 4.1 Setup Environment

```powershell
# Opsional: install package
pip install -e .

# Atau set PYTHONPATH (digunakan selama pengembangan)
$env:PYTHONPATH="E:\PROJECT\AI\nav2015-agent\src"
```

### 4.2 Konvensi Parameter `--company`

Seluruh CLI tools menggunakan **`--company`** sebagai parameter wajib. Path input/output diturunkan dari company name:

| Path | Template | Keterangan |
|------|----------|------------|
| Input company | `data/input/<company>/` | Folder atau ZIP berisi export company |
| Baseline | `data/input/original/` | Baseline export (hardcoded di diff/audit/depgraph) |
| Parsed output | `data/parsed/<company>/` | Hasil `nav-ai ingest` |
| Snapshots | `data/snapshots/<company>/` | Salinan byte-for-byte sumber |
| Search DB | `data/search/<company>/search.db` | Symbol index SQLite (selalu path ini, `--db` dihapus) |
| Reports | `reports/<company>/` | Laporan diff/audit/depgraph |

---

### Tool 1: `nav-ai ingest` — Parsing Objek NAV

```powershell
# Input diambil dari data/input/<company>/ secara otomatis
python -m nav_ai.cli ingest <company>
```

**Parameter:**
| Parameter | Tipe | Wajib | Keterangan |
|-----------|------|-------|------------|
| `company` | positional | Ya | Nama company, digunakan untuk `data/input/<company>/` |

**Output:** (`data/parsed/<company>/`)
- `inventory.json` — metadata lengkap + referensi baris sumber
- `inventory.csv` — satu baris per objek
- `dependencies.csv` — daftar edge dependensi
- `symbols.csv` — indeks prosedur dan variabel
- `run_manifest.json` — input file hashes dan parser version

**Output:** (`data/snapshots/<company>/`)
- Salinan byte-for-byte sumber per objek

**Contoh:**
```powershell
python -m nav_ai.cli ingest datascrip
```

---

### Tool 2: `nav-search index` — Bangun Symbol Index

```powershell
python -m nav_ai.search <company> index [inputs...]
```

**Parameter:**
| Parameter | Tipe | Wajib | Keterangan |
|-----------|------|-------|------------|
| `company` | positional | Ya | Nama company, DB di `data/search/<company>/search.db` |
| `inputs` | positional | Tidak | File/folder input (override; default: `data/input/<company>/`) |

**Output:** `data/search/<company>/search.db`

**Contoh:**
```powershell
# Gunakan data/input/datascrip/ secara default
python -m nav_ai.search datascrip index

# Override input path
python -m nav_ai.search datascrip index extra/datascrip.zip
```

---

### Tool 3: `nav-search find` — Cari Simbol

```powershell
python -m nav_ai.search <company> find [terms...] [options]
```

**Parameter:**
| Parameter | Tipe | Wajib | Keterangan |
|-----------|------|-------|------------|
| `company` | positional | Ya | Nama company, DB di `data/search/<company>/search.db` |
| `terms` | positional | Tidak | Kata kunci pencarian (kosong = error) |
| `--exact` | flag | Tidak | Case-insensitive whole-name match |
| `--id` / `--num` | int | Tidak | Object id, field id, atau variable id |
| `--kind` | append | Tidak | Filter jenis: object, field, procedure, trigger, variable |
| `--type` | string | Tidak | Tipe objek: Table, Page, Codeunit, Report, ... |
| `--object-id` | int | Tidak | Filter object ID |
| `--limit` | int | Tidak | Jumlah hasil maksimum (default: 50) |

**Contoh:**
```powershell
# Pencarian eksak (case-insensitive)
python -m nav_ai.search datascrip find --exact "Sales Header" --type Table

# Pencarian kata kunci (semua term harus ada)
python -m nav_ai.search datascrip find sales post --kind procedure

# Pencarian berdasarkan ID
python -m nav_ai.search datascrip find --id 50076

# Filter tipe + limit
python -m nav_ai.search datascrip find "Customer" --type Table --limit 20
```

---

### Tool 4: `nav-diff` — Semantic Diff

```powershell
python -m nav_ai.semantic_diff <company> [--output <file>]
```

**Parameter:**
| Parameter | Tipe | Wajib | Keterangan |
|-----------|------|-------|------------|
| `company` | positional | Ya | Original: `data/input/original/`, Company: `data/input/<company>/` |
| `--output` | string | Tidak | Nama file output (default: `diff.xlsx`); disimpan di `reports/<company>/` |

**Output:** `reports/<company>/<output>` (Excel)
Sheet: Dashboard, Object Semantic Summary, Procedure Changes, Section Changes

**Contoh:**
```powershell
python -m nav_ai.semantic_diff datascrip --output diff.xlsx
# Disimpan di: reports/datascrip/diff.xlsx
```

---

### Tool 5: `nav-audit` — Audit Perubahan

```powershell
python -m nav_ai.audit <company> [--output <file>]
```

**Parameter:**
| Parameter | Tipe | Wajib | Keterangan |
|-----------|------|-------|------------|
| `company` | positional | Ya | Original: `data/input/original/`, Company: `data/input/<company>/` |
| `--output` | string | Tidak | Nama file output (default: `audit.xlsx`); disimpan di `reports/<company>/` |

**Output:** `reports/<company>/<output>` (Excel)
Klasifikasi: `REAL`, `WHITESPACE ONLY`, `BOUNDARY ARTIFACT`

**Contoh:**
```powershell
python -m nav_ai.audit datascrip --output audit.xlsx
# Disimpan di: reports/datascrip/audit.xlsx
```

---

### Tool 6: `nav-depgraph` — Dependency Graph

```powershell
python -m nav_ai.depgraph <company> [--diff <file>] [--excel <file>] [--impact <node>]
```

**Parameter:**
| Parameter | Tipe | Wajib | Keterangan |
|-----------|------|-------|------------|
| `company` | positional | Ya | Digunakan untuk input dan output paths |
| `--diff` | string | Tidak | Nama file diff report di `reports/<company>/` |
| `--excel` | string | Tidak | Nama file Excel output di `reports/<company>/` |
| `--impact` | string | Tidak | Query transitive dependents untuk node (contoh: `Codeunit 80.Sales-Post`) |

**Output:**
- DB: `data/depgraph/<company>/depgraph.db`
- Excel: `reports/<company>/<excel>`
- Sheet: Summary, Objects, Caller-Callee, Procedure Calls, Table Usage, Custom to Standard, Standard Hotspots

**Contoh:**
```powershell
# Build dependency graph
python -m nav_ai.depgraph datascrip --diff NAV_Semantic_Source_Diff_Report.xlsx --excel NAV_Dependency_Report.xlsx

# Query transitive dependents (impact analysis)
python -m nav_ai.depgraph datascrip --impact "Codeunit 80.Sales-Post"
```

---

## 5. Pipeline End-to-End (Contoh Lengkap)

```powershell
# 1. Ingest company export
python -m nav_ai.cli ingest datascrip

# 2. Build symbol index
python -m nav_ai.search datascrip index

# 3. Cari simbol
python -m nav_ai.search datascrip find --exact "Sales Header" --type Table

# 4. Semantic diff (original vs company)
python -m nav_ai.semantic_diff datascrip --output diff.xlsx

# 5. Audit perubahan
python -m nav_ai.audit datascrip --output audit.xlsx

# 6. Dependency graph
python -m nav_ai.depgraph datascrip --diff diff.xlsx --excel NAV_Dependency_Report.xlsx

# 7. Impact analysis (transitive dependents)
python -m nav_ai.depgraph datascrip --impact "Codeunit 80.Sales-Post"
```

---

## 6. Kriteria Klasifikasi Objek (`depgraph.py`)

Klasifikasi **tidak bergantung** pada `Modified=Yes` atau nomor ID (50000). Hanya berdasarkan kehadiran di baseline + hasil diff:

| Kondisi | Klasifikasi |
|---------|-------------|
| Object ada di baseline dan tidak berubah | `STANDARD_UNCHANGED` |
| Object ada di baseline dan terdeteksi berubah (oleh diff) | `MODIFIED_STANDARD` |
| Object tidak ada di baseline (company only) | `CUSTOM` |
| Procedure baru pada standard object | `ADDED` |
| Procedure berubah pada standard object | `CHANGED` |

Logika:
```python
def obj_origin(key):
    if key in orig:
        if key in changed_objs: return "MODIFIED_STANDARD"
        return "STANDARD_UNCHANGED"
    return "CUSTOM"

def origin(node):
    key = key_of(node)
    if "." not in node: return obj_origin(key)          # Objek
    p = node.split(".", 1)[1]                            # Prosedur
    obj_o = obj_origin(key)
    if obj_o == "CUSTOM": return "CUSTOM"
    if (*key, p) in added: return "ADDED"
    if (*key, p) in changed: return "CHANGED"
    return obj_o                                         # Warisi dari objek
```

---

## 7. Kriteria Parser (terverifikasi)

Semua 10 kriteria parser terpenuhi (teruji pada `data/input/datascrip/datascrip.zip` dengan 4.696 objek):

| No | Kriteria | Status |
|----|----------|--------|
| 1 | Object Type, ID, Name terdeteksi benar | ✅ |
| 2 | Batas antar-object terdeteksi benar (tidak ada yang digabung/terlewat) | ✅ |
| 3 | Property object dapat diekstrak | ✅ |
| 4 | Field dan tipe data Table terdeteksi (100% memiliki data_type) | ✅ |
| 5 | Function/prosedur dan parameter C/AL terdeteksi | ✅ |
| 6 | Trigger dan source code tetap utuh (semua prosedur memiliki `raw`) | ✅ |
| 7 | Nomor baris sumber dipertahankan (`line_start`, `line_end`, `line`) | ✅ |
| 8 | Checksum SHA-256 setiap object dihasilkan | ✅ |
| 9 | Tidak ada source code yang hilang (section range tidak melewati batas file) | ✅ |
| 10 | Hasil parsing dapat dibandingkan dengan TXT asli (sha256, line_count, sections, original_path, zip_member) | ✅ |

---

## 8. Hasil Uji (Test Suite)

```
44 passed, 4 failed
```

4 kegagalan adalah `test_real_exports.py` karena file `data/incoming/T50076.txt`, `C80.txt`, `P42.txt` sudah dihapus dari working tree (pre-existing, bukan karena perubahan kode).

Semua tes yang relevan lolos:
- `test_parser.py` — 3/3
- `test_ingest_cli.py` — 5/5
- `test_depgraph.py` — 2/2
- `test_depgraph_cli.py` — 6/6
- `test_semantic_diff.py` — 13/13
- `test_search.py` — 11/11
- `test_audit.py` — 3/3
- `test_zip_support.py` — 6/6

---

## 9. Tools Clean (`clean.py`)

File `clean.py` di root proyek untuk menghapus semua file/folder hasil generate:

```powershell
# Lihat dulu apa yang akan dihapus (dry-run)
python clean.py

# Hapus sebenarnya
python clean.py --execute
```

**Folder yang akan dihapus:** `data/parsed/`, `data/snapshots/`, `data/search/`, `data/depgraph/`

**File yang dilestarikan:** `data/input/`, `extra/`, `src/`, `tests/`, `reports/archive/`, konfigurasi (`pyproject.toml`, `README.md`, `.gitignore`, dll.)

---

## 10. Catatan Penting

- `data/incoming/` dirujuk dalam README tetapi tidak ada sebagai direktori saat ini (file sebelumnya sudah terhapus: `D data/incoming/C80.txt`, `P42.txt`, `T50076.txt`)
- Data asli tersedia di `data/input/original/original.zip` dan `data/input/datascrip/datascrip.zip`
- Data demo tersedia di `extra/all_original.txt` dan `extra/datascrip.zip`
- Parser adalah deterministic first-pass, **bukan** full C/AL compiler. Tidak mengekstrak control-flow semantics, indirect calls, dynamic EVALUATE/record references, atau complete dependency resolution.
- `Modified=Yes` disimpan sebagai metadata tapi **tidak bukti** bahwa objek adalah custom atau modified-standard.
- Untuk menjalankan modul tanpa install: setel `$env:PYTHONPATH="src"` sebelum menjalankan perintah `python -m nav_ai.<modul>`.
