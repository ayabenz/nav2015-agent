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

### Automatic call-graph tracing and source discovery

The `trace` command starts from an object or procedure node, follows existing `CALL` edges to a configurable depth, and resolves each reached object against source exports supplied as TXT files, ZIP files, or directories. It uses the symbol index's `source_file` labels to disambiguate duplicate object exports where possible.

```powershell
nav-intel --company datascrip --json trace "Codeunit 50107" --source-root "reports\datascrip" --max-depth 5
nav-intel --company datascrip --json trace "Codeunit 50107.BlockStocktakeSalesHeader" --source-root "data\input\datascrip.zip" --max-depth 3
```

The output contains reachable procedure nodes, call edges, source paths, procedure line ranges, origin classification, and explicit missing/ambiguous source statuses. Object starts include all indexed procedures plus the object-level and trigger-scope graph sources at depth zero. `--max-depth` counts procedure-call edges; `--max-nodes` bounds output size.

With `--analyze-conditions`, the command also runs the existing IF/ELSE/CASE, assignment and Record-filter analyzers for every resolved procedure, automatically loading Table metadata found in the same source roots. Missing or ambiguous Table exports remain explicit in `semantic_resolution`; each procedure also reports required-but-unavailable Table IDs, and source/procedure resolution failures are represented as per-procedure statuses. It follows only dependency-graph `CALL` edges, so dynamic calls, indirect dispatch, implicit side effects, and edges missing from the graph are not discovered. It is static analysis and never proves runtime execution.


The installed console command is also available:

```powershell
nav-intel --company datascrip --json conditions --source-file "path\Codeunit_B.txt" --object "Codeunit 60001" --procedure "Process" --nested-source "path\Codeunit_C.txt" --nested-source "path\Codeunit_D.txt" --max-call-depth 2 --call-source "path\Codeunit_A.txt"
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

Current CLI: `nav-intel --company datascrip --json conditions --source-file <NAV-TXT> --object "Codeunit 80" --procedure "PostItemJnlLine" --table-source <TABLE-TXT>`. Automatic source-file resolution from the symbol index and integration into existing object/procedure details remain future work. Tests should cover nested IF/ELSE, ELSEIF, CASE, Option values, field comparisons, variable assignment/data-flow and unresolved expressions.

See ROADMAP_TRACKER.md, Phase 2.5, for implementation tasks and exit criteria.

## Initial implementation: control-flow structure extraction

The first implementation adds `nav_ai.control_flow` and a `conditions` command. It extracts nested IF/ELSE and CASE/OF branches from a supplied NAV TXT export and preserves raw predicates, branch statements, source spans and parser diagnostics.

The analyzer also annotates simple Boolean callee conditions when a direct caller passes a literal `TRUE` or `FALSE`. For example, Codeunit 50081 calls `BlockStocktakeSalesHeader(Rec, FALSE)`, while Codeunit 50107 branches on `IF CreateWhseShipment THEN`. The call-site annotation identifies the ELSE outcome as compatible with that call and the THEN outcome as incompatible. This is call-site-specific static specialization, not proof that either procedure executed. Only simple predicates directly referencing the Boolean formal (or supported `NOT`/Boolean comparison forms) are recognized; compound expressions remain unresolved.

Example:

```powershell
nav-intel --company datascrip conditions --source-file "data/input/datascrip/Codeunit 50081.txt" --object "Codeunit 50081" --procedure "CheckStocktake"
```

The source file must contain one resolvable object (or use `--object` to select one object from a multi-object export). Omit `--procedure` to analyze the object's CODE section. The command currently requires an explicit source file; automatic source-file resolution from the symbol index is a subsequent integration step.

**Current limits:** raw predicates and source spans are retained, with initial normalization, Table/Field/Option resolution and path-sensitive filter tracking described in the sections below. Local assignment/data-flow, cross-procedure value propagation, full C/AL grammar coverage and runtime evaluation are not implemented. Unsupported statements are preserved as opaque statement nodes. Treat diagnostics and unresolved operands as part of the evidence.


## Semantic resolution: Record fields and Option members

The semantic-resolution increment adds `nav_ai.semantic_conditions`. It resolves qualified C/AL references such as `tblStocktake."Start Date"` using the Record variable declaration and an explicit Table TXT export. Resolved references include Table ID/name, Field ID/name/type, metadata source and line. Option members are checked against the field's OptionString; a value not present in the metadata is marked `unverified`, not silently accepted.

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

**Important limitations:** filter expressions and `%1` substitution arguments are preserved as source text, not evaluated. The current CLI uses the path-sensitive IF/CASE pass described below. It does not model interprocedural flow, dynamic RecordRef/FieldRef or WITH-scope field references. A lookup result is always `unknown_static`: only NAV runtime evidence can establish whether a row was found.


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


### Stocktake Sales Header example

The current `BlockStocktakeSalesHeader` source has a document-type IF / ELSE IF before the `tblStocktake.FINDFIRST` lookup:

- Sales Order / Sales Invoice path: `Jenis Transaksi = OUT|ALL`
- Sales Credit Memo / Sales Return Order path: `Jenis Transaksi = IN|ALL`
- Other document-type path: no `Jenis Transaksi` filter is assigned by that IF chain

The third path is important: the analyzer must not silently treat it as either IN or OUT. Whether it is reachable for the caller's document type is a separate question that requires value and caller-context analysis. A dedicated regression fixture covers these three syntactic paths.


## Normalized condition expressions

The analyzer now attaches `normalized_condition` to IF nodes and `normalized_expression` to CASE selectors when Table metadata resolution is enabled. The initial expression normalizer recognizes:

- Comparison operators: `=`, `<>`, `<`, `>`, `<=`, `>=`, and `IN`
- Boolean composition: `AND`, `OR`, and unary `NOT`, with parentheses and precedence preserved
- `IN [value, ...]` lists, retained as individual raw operands
- Field references and Option members, which are resolved separately by `semantic_conditions`

For example, the Stocktake predicate comparing `tblStocktake."Block Type"` to the `"Item Category"` Option member becomes a comparison node with left and right operands. The resolver separately confirms whether the field and Option member exist in the supplied Table 50063 metadata.

Normalization is structural, not evaluative. It does not determine the current value of a Record field, evaluate Boolean expressions, classify every literal type, or prove a branch reachable. Unrecognized fragments remain raw operand nodes so the original source expression is not discarded.


## Evidence-backed condition explanations

When Table metadata is supplied, IF nodes now include `condition_explanation` alongside the raw predicate, normalized expression and resolution details. Comparison operands are classified as resolved field references, Option members, string/numeric/boolean literals, or raw expressions. Boolean AND / OR / NOT nodes retain their nested structure.

For a predicate such as:

```pascal
tblStocktake."Block Type" = tblStocktake."Block Type"::"Block Type"::"Item Category"
```

the explanation identifies the left operand as Table 50063 Field 11 (`Block Type`) and the right operand as the `Item Category` Option member, then reports whether that member exists in the supplied OptionString.

This describes what the source compares; it does not read a live or historical record value. The explanation marks comparisons as `evaluated=false`. An actual TRUE/FALSE answer for a document still requires a matching runtime snapshot and execution context.


## Optional evaluation against an explicit record snapshot

A separate helper, `nav_ai.snapshot_evaluator.evaluate_condition_snapshot`, evaluates the supported normalized expression tree against a caller-supplied dictionary of Record values. It performs no SQL access and does not invoke NAV. Missing fields, unsupported expressions and incompatible values produce `indeterminate`, never an assumed FALSE.

For NAV Option fields, a SQL-style integer ordinal is translated through the supplied Table TXT `OptionString` (zero-based option position) before comparison with an Option member. For example, Table 50063 `Jenis Transaksi` ordinal `2` resolves to `ALL` when its OptionString is `IN,OUT,ALL`.

The result provenance is `caller_supplied_snapshot` and `runtime_evaluated=false`. This is a deterministic evaluation of the supplied values, not proof that those values existed at posting time or that NAV executed the procedure. A future CLI integration must require an explicit snapshot file and preserve its provenance.


### CLI usage with a supplied snapshot

The optional `--snapshot-json` argument attaches a snapshot evaluation to IF nodes. It requires at least one `--table-source` so Option ordinals can be interpreted against metadata.

Example snapshot file:

```json
{
  "tblStocktake": {
    "Block Type": 2,
    "Item Category Code": "ELEC",
    "Product Group Code": "",
    "Item No.": ""
  }
}
```

Example command:

```powershell
nav-intel --company datascrip --json conditions --source-file "reports/datascrip/ownership/Codeunit_50107.txt" --object "Codeunit 50107" --procedure "BlockStocktakeSalesHeader" --table-source "reports/datascrip/stocktake/Table_50063.txt" --snapshot-json "stocktake_snapshot.json"
```

The snapshot keys are Record variable names; nested keys are NAV field names. Record variable declarations in both local VAR sections and procedure parameters are resolved. The example is illustrative only: values must come from an explicitly selected and properly scoped record snapshot. If a predicate references a field whose Table metadata or snapshot value is missing, its result remains indeterminate.


## Static assignment and data-flow analysis

The `conditions` command also runs `nav_ai.assignment_flow` and attaches `assignment_context` to each IF node. It tracks explicit assignments such as `Status := 'Released'` and `SalesHeader.Status := SalesHeader.Status::Released`, then links the latest visible assignment to a later condition. IF/ELSE and CASE branches retain separate incoming assignment alternatives; values from divergent paths are not collapsed into one assertion.

Assignment expressions remain symbolic source text. The analyzer does not calculate expressions, query SQL, infer values from database state, or prove a path was executed. When an unrecognized procedure call is encountered, all currently tracked values on that path are invalidated because C/AL VAR parameters may be modified. The first implementation intentionally does not trace values across procedure boundaries, triggers, WITH scopes, or implicit database mutations.

Example output shape (abbreviated):

```json
{
  "assignment_context": {
    "alternatives": [
      {
        "known_assignments": [
          {
            "target": "Status",
            "expression": "'Released'",
            "line": 12,
            "evaluated": false
          }
        ]
      }
    ],
    "runtime_evaluated": false
  }
}
```

The `assignment_flow_analysis` top-level section records assignment events, unknown-call invalidations, and the static-path limitation. This is provenance for source-level reasoning, not a substitute for a caller-supplied snapshot or NAV runtime trace.


### Assignment provenance chains

The local assignment analyzer now records conservative symbolic references used by an assignment and follows those references through the latest visible assignments on the same static path. For example, if Status := 'Released' is followed by SalesHeader.Status := Status, an IF predicate on SalesHeader.Status includes a provenance chain back to the assignment of Status.

Each chain element retains its source assignment and line. String literals and quoted field names are masked before reference extraction; Option members after :: are not treated as variables. Missing upstream assignments are reported as unresolved. Cycles are marked explicitly. No expression is evaluated, and no database value is inferred.

This remains intra-procedural analysis. Procedure parameters, return values, VAR parameter mutation across calls, WITH scopes, implicit trigger effects and RecordRef/FieldRef remain outside the supported scope. Unknown calls continue to invalidate tracked state.


### Direct interprocedural argument binding

The `conditions` command accepts repeatable `--call-source <caller.txt>` arguments when a specific `--procedure` is selected. It scans supplied caller exports for direct `Receiver.Procedure(...)` syntax, checks the receiver's declared Codeunit type against the callee object, and maps positional actual arguments to the callee's parsed formal parameters. It recognizes typed Record variables (including `Rec` when `TableNo` is declared) and Boolean literals. `VAR` formals are explicitly marked by-reference.

The same command also includes a conservative callee-side summary of explicit assignments to those `VAR` parameters. Assignments to a scalar parameter and assignments to a qualified field of a `VAR Record` parameter are reported with source line and branch path, then associated with the corresponding actual argument in each call-site result under `var_parameter_effects`. For example, a formal `SalesHeader: Record 36` passed by reference can report an assignment to `SalesHeader.Status` as a mutation of the caller's Record argument.  This remains symbolic: expressions are not evaluated, nested calls, triggers, implicit writes and other side effects are not fully modeled.

For simple caller arguments, the output includes `caller_state_effect_map`. It maps explicit callee assignments back to a simple caller variable (for example, a `VAR SalesHeader` field assignment maps to `Rec.Status`). Unconditional mutations are eligible directly. A conditional mutation is eligible only when every predicate in its path is a supported simple Boolean formal and the call site supplies a Boolean literal that selects that exact path. Incompatible paths are discarded; unresolved or mixed paths are not promoted to definite effects.

The `conditions` command also accepts repeatable `--nested-source` exports for procedures directly called by the selected procedure. It summarizes those nested callees' explicit `VAR` mutations, specializes their simple Boolean branches using literal arguments at the nested call site, and feeds the mapped effects into the selected procedure's own `VAR` mutation summary. This lets an outer `--call-source` see effects originating one Codeunit deeper (A calls B, B calls C). The traversal is recursive but explicitly depth-bounded with `--max-call-depth` (default `1` additional hop). Repeated object identities on the current path are skipped to prevent cycles; it is not an unbounded whole-application call-graph traversal. Example invocation for a selected callee B, with C as its nested callee and A as B's caller:

```powershell
nav-intel --company datascrip --json conditions --source-file "path\Codeunit_B.txt" --object "Codeunit 60001" --procedure "Process" --nested-source "path\Codeunit_C.txt" --call-source "path\Codeunit_A.txt"
```



The CLI now automatically reparses supplied caller object exports, identifies caller procedures containing mapped call sites, and runs `analyze_assignment_flow(..., call_effects=...)` over those procedures. The resulting `caller_assignment_flow` includes caller procedure identity, path-sensitive assignment events, and control-flow nodes. Subsequent caller `IF` nodes can therefore show the symbolic callee assignment in their `assignment_context`. At a recognized call, pre-call tracked facts are invalidated before only supported mapped effects are restored.

Complex actual arguments, compound Boolean predicates, nonliteral Boolean arguments, conditional paths with unknown predicates, and implicit or nested side effects are not propagated. A missing caller assignment means the value remains unknown, not unchanged. A missing explicit assignment is not proof that a parameter is immutable. This is static source analysis; it does not prove that the call or branch executed at runtime.

Example:

```powershell
nav-intel --company datascrip --json conditions --source-file "reports/datascrip/ownership/Codeunit_50107.txt" --object "Codeunit 50107" --procedure "BlockStocktakeSalesHeader" --call-source "reports/datascrip/stocktake_callers/Codeunit_50081.txt"
```

The output is static call-site evidence only. It does not prove execution or fully propagate caller state. Only unconditional explicit VAR mutations through simple arguments are mapped; conditional effects remain possible rather than definite. WITH-scoped/unqualified calls, dynamic dispatch, indirect callbacks, and arbitrary expression types are not resolved. Caller source line numbers are relative to the supplied object export.
