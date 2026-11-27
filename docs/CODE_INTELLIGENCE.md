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

## Planned extension: Conditional Logic Intelligence

The next source-analysis layer will explain C/AL branch logic and connect predicates to NAV table values. It will reuse the existing parsed source, symbol index and dependency graph. The first implementation is static and deterministic; it will not claim to know which branch executed for a live or historical document.

### Supported control-flow scope

- IF / THEN, ELSE, ELSEIF and nested blocks.
- CASE / OF, individual value/range arms and default ELSE.
- Boolean composition (AND, OR, NOT), comparisons, parentheses, literals and Option members.
- Mapping of Record variables and qualified field references to NAV Table / Field definitions.
- Option metadata resolution from the table field's OptionString / parsed option members.
- Source-backed branch tree with TRUE/FALSE or CASE-match/default paths.

### Example explanation

```pascal
IF SalesHeader."Document Type" = SalesHeader."Document Type"::Order THEN BEGIN
    IF SalesHeader.Status = SalesHeader.Status::Released THEN
        CODEUNIT.RUN(CODEUNIT::"Sales-Post", SalesHeader)
    ELSE
        ERROR('Document is not released');
END ELSE
    ERROR('Invalid document type');
```

The analyzer should explain the outer predicate, its resolved table/field and Option member, then the nested predicate and both outcomes. It should associate the TRUE branch with the posting call and the FALSE branches with their respective errors, each backed by source line ranges. This is a source explanation, not proof of runtime execution.

### Resolution and data-flow stages

1. Parse branch structure and retain raw source expressions.
2. Normalize expressions into operands and operators.
3. Resolve Record variable types, field identities and Option/Enum members using parsed metadata and the symbol index.
4. Track local assignments and record-field mutations before predicates.
5. Trace direct-call parameters and relevant record values across procedures when statically resolvable.
6. Preserve unresolved expressions (including dynamic RecordRef/FieldRef, EVALUATE and indirect data flow) with explicit diagnostics instead of guessing.

### Static versus runtime conclusions

- **Static:** describes conditions, possible outcomes and source statements reached by each outcome.
- **Runtime:** evaluates a predicate for a specific document only when an explicit, correctly scoped runtime snapshot and execution context are supplied. A current database row alone does not prove what values existed when a historical posting ran.

### Planned CLI and tests

Proposed CLI: `nav-intel --company datascrip conditions "Codeunit 80.PostItemJnlLine"`. Integrate the output into existing object and procedure details after the dedicated query is stable. Tests should cover nested IF/ELSE, ELSEIF, CASE, Option values, field comparisons, variable assignment/data-flow and unresolved expressions.

See ROADMAP_TRACKER.md, Phase 2.5, for implementation tasks and exit criteria.

## Initial implementation: control-flow structure extraction

The first implementation adds `nav_ai.control_flow` and a `conditions` command. It extracts nested IF/ELSE and CASE/OF branches from a supplied NAV TXT export and preserves raw predicates, branch statements, source spans and parser diagnostics.

Example:

```powershell
nav-intel --company datascrip conditions --source-file "data/input/datascrip/Codeunit 50081.txt" --object "Codeunit 50081" --procedure "CheckStocktake"
```

The source file must contain one resolvable object (or use `--object` to select one object from a multi-object export). Omit `--procedure` to analyze the object's CODE section. The command currently requires an explicit source file; automatic source-file resolution from the symbol index is a subsequent integration step.

**Current limits:** predicates are retained as source text and are not yet semantically resolved to Table/Field IDs or OptionString values. Assignment/data-flow, cross-procedure value propagation, full C/AL grammar coverage and runtime evaluation are not implemented. Unsupported statements are preserved as opaque statement nodes. Treat diagnostics and source spans as part of the evidence.


## Semantic resolution: Record fields and Option members

The next increment adds `nav_ai.semantic_conditions`. It resolves qualified C/AL references such as `tblStocktake."Start Date"` using the Record variable declaration and an explicit Table TXT export. Resolved references include Table ID/name, Field ID/name/type, metadata source and line. Option members are checked against the field's OptionString; a value not present in the metadata is marked `unverified`, not silently accepted.

Example against the actual Stocktake source exports:

```powershell
nav-intel --company datascrip --json conditions --source-file "reports/datascrip/ownership/Codeunit_50107.txt" --object "Codeunit 50107" --procedure "BlockStocktakeSalesHeader" --table-source "reports/datascrip/stocktake/Table_50063.txt"
```

Repeat `--table-source` for each additional Table export needed by the analyzed procedure. The resolver currently handles qualified `RecordVariable.Field` references. Unqualified field names inside C/AL `WITH` scopes, RecordRef/FieldRef, dynamic expressions and cross-procedure data flow remain unresolved by design. The output remains static and always sets `runtime_evaluated=false`.

The resolver is deliberately conservative: missing variable declarations, Table exports or fields produce explicit unresolved reasons. Option members absent from OptionString are marked unverified; no runtime branch is inferred.


## Static Record filter and lookup analysis

When Table TXT metadata is supplied, the `conditions` command also scans the selected source region for Record operations:

- `SETRANGE(Field, From[, To])` and `SETFILTER(Field, Filter[, Value...])` are retained with their raw arguments, source line, Record variable, Table ID and resolved Field metadata when available.
- `SETRANGE(Field)` removes the tracked filter for that field.
- `RESET` clears all tracked filters for that Record variable.
- `FINDFIRST`, `FINDLAST` and `FINDSET` produce lookup snapshots containing the filters seen earlier in source order.
- A direct `IF Record.FINDFIRST THEN` or `IF NOT Record.FINDFIRST THEN` is annotated with the possible matching-record / no-matching-record meaning.

Example against Codeunit 50107:

```powershell
nav-intel --company datascrip --json conditions --source-file "reports/datascrip/ownership/Codeunit_50107.txt" --object "Codeunit 50107" --procedure "BlockStocktakeSalesHeader" --table-source "reports/datascrip/stocktake/Table_50063.txt"
```

**Important limitations:** filter expressions and `%1` substitution arguments are preserved as source text, not evaluated. The current pass scans calls in source order. If the analyzed region contains IF/CASE/ELSE, lookup filter state is explicitly marked `branch_ambiguous`; it is not a path-sensitive merge and must not be interpreted as the exact filter set on every branch. It also does not model interprocedural flow, dynamic RecordRef/FieldRef or WITH-scope field references. A lookup result is always `unknown_static`: only NAV runtime evidence can establish whether a row was found.


## Path-sensitive filter state across IF / CASE

The condition analyzer now has a path-sensitive pass over the parsed IF/ELSE and CASE tree. Instead of scanning the whole procedure as one linear stream, it forks a filter state for each syntactic branch and keeps the states separate after branches rejoin.

For example:

```pascal
IF IsOutbound THEN
  R.SETFILTER("Jenis Transaksi", 'OUT|ALL')
ELSE
  R.SETFILTER("Jenis Transaksi", 'IN|ALL');

IF R.FINDFIRST THEN
  ...
```

The lookup after the first IF is represented by two possible source paths, one carrying `OUT|ALL` and the other carrying `IN|ALL`. CASE arms and ELSE are handled similarly. Each lookup includes `path_conditions`, `active_filters`, and `filter_state=path_specific`. The IF predicate annotation retains all matching lookup alternatives in `lookup_paths`.

This remains static path enumeration, not symbolic execution. Predicates such as `IsOutbound` are not evaluated, filter placeholders are not substituted, and the analyzer does not prove either path is reachable. Unknown or unsupported statement forms remain outside the interpreted subset. Database row existence is never inferred from FINDFIRST.
