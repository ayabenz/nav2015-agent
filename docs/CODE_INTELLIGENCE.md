# NAV Datascrip Code Intelligence

## Purpose

Provide evidence-oriented queries over the existing NAV Datascrip source indexes. This layer reuses:

- `data/search/<company>/search.db` for symbols and source file/line locations.
- `data/depgraph/<company>/depgraph.db` for objects, procedures, dependency edges and table usage.

It does not parse C/AL again, rebuild the dependency graph, or infer runtime behavior.

## Install / run

After installing the project in editable mode, or with `PYTHONPATH=src`:

```powershell
python -m nav_ai.intelligence --company datascrip search stocktake
python -m nav_ai.intelligence --company datascrip object "Codeunit 80"
python -m nav_ai.intelligence --company datascrip procedure "Codeunit 80.PostItemJnlLine"
python -m nav_ai.intelligence --company datascrip callers "Codeunit 80.PostItemJnlLine"
python -m nav_ai.intelligence --company datascrip callees "Codeunit 80.PostItemJnlLine"
python -m nav_ai.intelligence --company datascrip impact "Codeunit 80.PostItemJnlLine"
python -m nav_ai.intelligence --company datascrip table "Table 36"
python -m nav_ai.intelligence --company datascrip table "Table 36" --usage WRITE
```

The installed console command is also available:

```powershell
nav-intel --company datascrip impact "Codeunit 80.PostItemJnlLine"
```

Add `--json` before the subcommand to produce machine-readable JSON.

## Query capabilities

| Command | Uses | Result |
|---|---|---|
| `search` | Symbol index | Objects, fields, procedures, variables and triggers with source file and line ranges |
| `object` | Dependency graph | Object classification, procedures, direct graph neighborhood and table usage |
| `procedure` | Dependency graph | Procedure classification, direct callers and callees |
| `callers` / `callees` | Dependency graph | Direct inbound/outbound edges |
| `impact` | Dependency graph | Transitive callers; follows CALL edges by default |
| `table` | Dependency graph | READ/WRITE and other recorded table usage |

## Evidence and interpretation rules

1. A graph edge is static evidence extracted from exported C/AL source. It is not proof that a branch executes at runtime.
2. `CALL` is the default for call-chain and impact queries. `VAR`, `SOURCE`, `RELATION` and `TABLE_REF` represent different relationships and must not be treated as execution paths.
3. Use `--kinds CALL,REF` only when intentionally broadening an impact query to loose navigation references. Such results are not equivalent to runtime callers.
4. Table usage is limited by what the current dependency engine resolves, including typed Record variables and recognized record methods.
5. Every symbol search result includes source file and line range. Use that source location to verify a conclusion before describing it as a confirmed business rule.
6. The current parser/graph is a deterministic first-pass analysis, not a full C/AL compiler. Dynamic calls, RecordRef/FieldRef patterns and implicit runtime behavior may remain unresolved.

## Recommended investigation workflow

1. Search for the business term, table, object or procedure.
2. Resolve the exact NAV object/procedure identity; do not assume a display name is unique.
3. Inspect the procedure and its direct callers/callees.
4. Trace only CALL edges to reconstruct execution paths.
5. Inspect table READ/WRITE usage to identify data touched by the path.
6. Verify each important conclusion against the cited source file and line range.
7. Record unresolved dynamic references and runtime assumptions separately.

## Current implementation boundary

This is the first query layer, not yet a natural-language AI agent. It provides deterministic retrieval primitives that a later agent can call. A future agent must cite the returned source locations and distinguish static findings, company-confirmed policy, and runtime-verified behavior.
