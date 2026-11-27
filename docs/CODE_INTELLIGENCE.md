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
nav-intel --company datascrip --json trace "Codeunit 50107" --source-root "data\input\datascrip\datascrip.zip" --max-depth 2 --max-nodes 300 --analyze-conditions
nav-intel --company datascrip --json trace "Codeunit 50107.BlockStocktakeSalesHeader" --source-root "data\input\datascrip\datascrip.zip" --max-depth 1 --max-nodes 100
```

The output contains reachable procedure nodes, call edges, source paths, procedure line ranges, origin classification, and explicit missing/ambiguous source statuses. Each procedure also carries one shortest discovered `call_path` and its direct Table usage; `process_summary` aggregates procedure origins, source-resolution states, Table usage and IF/CASE node counts. Alternate call edges remain in `call_edges`, so the displayed path is not asserted to be the only possible route. Object starts include all indexed procedures plus the object-level and trigger-scope graph sources at depth zero. `--max-depth` counts procedure-call edges; `--max-nodes` bounds output size.

With `--analyze-conditions`, the command also runs the existing IF/ELSE/CASE, assignment and Record-filter analyzers for every resolved procedure, automatically loading Table metadata found in the same source roots. Missing or ambiguous Table exports remain explicit in `semantic_resolution`; each procedure also reports required-but-unavailable Table IDs, and source/procedure resolution failures are represented as per-procedure statuses. It follows only dependency-graph `CALL` edges, so dynamic calls, indirect dispatch, implicit side effects, and edges missing from the graph are not discovered. It is static analysis and never proves runtime execution.

The default Datascrip integration test checks the committed Stocktake source export quickly. The full 4,696-object ZIP integration can be run explicitly from PowerShell with:

```powershell
$env:NAV_RUN_FULL_DATASCRIP_TRACE='1'; python -m pytest tests/test_datascrip_trace_integration.py -q; Remove-Item Env:NAV_RUN_FULL_DATASCRIP_TRACE
```



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


### Automatic interprocedural summaries in process traces

The `trace` command now adds `interprocedural_analysis` for every discovered CALL edge. For edges whose caller and callee source exports are resolved, it attempts to bind direct `Receiver.Procedure(...)` call sites, summarizes explicit callee `VAR` parameter assignments, and maps safe effects back to simple caller arguments. Supported Boolean literal arguments specialize simple callee IF paths; incompatible mutations are excluded and unresolved paths are not promoted.

The result reports each edge as `analyzed`, `no_matching_direct_call`, `source_unavailable`, or `analysis_unavailable`, with the binding, mutation summary, and symbolic caller effect map. Object-scope/trigger edges and graph edges that cannot be resolved to direct source-level calls remain explicit rather than guessed.

This is currently a **one-edge summary**: it does not yet recursively compose VAR effects across multiple discovered graph hops or feed those effects into every caller's later IF/ELSE assignment context. It does not evaluate expressions, access SQL data, or prove runtime execution. All results carry `runtime_evaluated: false`.


#### Bounded multi-hop VAR-effect composition in `trace`

The `trace` command composes explicit VAR mutations across discovered call edges. Set `--max-interprocedural-depth N` to control the number of additional propagation rounds (default: `2`). Each round takes effects summarized for a callee, maps them through its caller's direct call-site arguments, and feeds those mapped assignments into the caller's own VAR mutation summary. This supports chains such as A calls B, B calls C, and C assigns a field on a Record VAR parameter; the resulting symbolic field mutation can be mapped through B to A.

The JSON output adds `interprocedural_analysis.procedure_summaries`, `propagated_hops`, and the composed `caller_state_effect_map` on each analyzed edge. Cycles are bounded by the configured round count rather than traversed indefinitely. A depth of zero disables cross-edge composition; direct source bindings are still reported.

Example:

```powershell
nav-intel --company datascrip --json trace "Codeunit 50107" --source-root "data\\input\\datascrip\\datascrip.zip" --max-depth 3 --max-nodes 500 --max-interprocedural-depth 2 --analyze-conditions
```

Composition is conservative and only carries explicit VAR assignments whose simple Boolean path predicates are selected by literal call arguments. It does not propagate arbitrary expressions, infer SQL Record values, prove calls executed, or fully model triggers, implicit writes, WITH scopes, dynamic dispatch or indirect calls. `runtime_evaluated` remains false for all summaries.


When `--analyze-conditions` is enabled, the composed per-edge effects are also injected into the assignment-flow analysis of each reached caller procedure. The source line offset is applied when converting call-site lines from an object export into absolute file lines. Consequently, a later caller IF node can expose a multi-hop symbolic Record-field assignment in its `assignment_context`, not merely in the top-level interprocedural report. The output includes `interprocedural_call_effect_count` per analyzed procedure. This remains a symbolic assignment context; it does not establish the Record's database value or runtime branch outcome.


#### Semantic resolution of propagated assignments

For procedures with Table metadata available, `trace --analyze-conditions` now enriches explicit and interprocedural assignment events. A target such as `Header.Status` is resolved against the declared Record variable's Table ID and field metadata. An Option RHS such as `Header.Status::Released` is checked against that field's `OptionString`; results distinguish `resolved`, `unverified`, and `unresolved`. The same metadata is attached to assignment alternatives shown in later IF nodes' `assignment_context`.

This explains *which Table field is being assigned and whether the named Option member exists in the exported Table definition*. It does not prove the assignment executed or that the field currently contains that value in SQL/NAV. Non-Option expressions remain symbolic.


#### Interprocedural Record filter propagation

Trace now reports `interprocedural_filter_analysis` for direct CALL edges. When a callee receives a typed Record parameter by reference, explicit `SETRANGE`, `SETFILTER`, field-clearing `SETRANGE(Field)`, and `RESET` operations can be mapped to a simple caller Record argument. Conditional operations are propagated only when supported Boolean literals at the call site select the corresponding IF path.

With `--analyze-conditions`, mapped filter effects are applied to the caller's path-sensitive Record-filter state at the call statement. A later `FINDFIRST`/FIND lookup can therefore show filters established inside the called Codeunit. Filter arguments remain source expressions; no filter is executed and no matching row is inferred. This first version handles direct callee filter operations; nested interprocedural filter composition remains unsupported.


#### Business-process documentation generator

Use the `document` command to generate a human-readable Markdown report and a machine-readable JSON trace from the same dependency-graph traversal:

```powershell
nav-intel --company datascrip document "Codeunit 50107" --source-root "data\\input\\datascrip\\datascrip.zip" --max-depth 5 --max-nodes 5000 --max-interprocedural-depth 2 --analyze-conditions
```

By default, files are written under `reports/datascrip/business_process/` using the start object as the filename. Supply `--output "reports\\datascrip\\business_process\\stocktake.md"` to choose a Markdown path; the companion JSON uses the same basename. The report includes process scope, procedure call paths, source resolution, direct table usage, IF/ELSE/CASE effect inventory with branch paths and source line references, aggregate table usage, unresolved call targets, and evidence limitations.

The JSON companion retains the complete trace payload for downstream agent retrieval, including condition trees, assignment/filter analysis, interprocedural summaries, graph edges, and source evidence. Reports explicitly state that static effects are not runtime execution counts or proof of committed changes. Missing/ambiguous source remains visible. The command does not require a NAV database connection or runtime test.


#### Custom/standard NAV boundary mapping

The `business_flow` payload retains each procedure's object-origin classification (for example `CUSTOM`, `MODIFIED_STANDARD`, or `STANDARD_UNCHANGED`). It also reports `origin_transitions`: discovered procedure CALL edges where caller and callee origins differ. The Markdown report presents these transitions separately so a reader can see where a Datascrip customization crosses into standard NAV code, or where a standard object calls back into custom code.

These transitions are dependency-graph evidence only. They do not prove the call occurred in a particular transaction. Edges with object-level or unresolved targets are still reported separately; no procedure target is invented.


#### Automatic business-process entry-point discovery

Use `discover` to produce a ranked inventory of candidate entry objects before generating individual process traces:

```powershell
nav-intel --company datascrip discover --limit 300
```

The command reads the existing dependency graph only; it does not need source exports or rebuild the graph. It prioritizes Page, Report, XMLport, and Codeunit objects using object origin, incoming/outgoing graph-edge counts, and indexed procedure counts. Use `--include-standard` to include unchanged standard NAV objects.

The output is a review queue, not a list of confirmed business processes. A Page may be a lookup/subpage, a Report may be an auxiliary report, and low incoming-edge count does not prove external initiation. Static graph edges may omit UI actions, job queues, integrations, events, and dynamic calls. After reviewing candidates, pass a selected object to `document` with the Datascrip source ZIP to build its evidence-backed Markdown and JSON process trace. Automatic grouping of related candidates into end-to-end processes is a subsequent capability.


## Automatic candidate mapping by Table footprint

Use `discover` to rank likely entry objects, then `map-processes` to group candidates whose CALL-reachable procedures use overlapping Tables:

```powershell
nav-intel --company datascrip --json discover --limit 300
nav-intel --company datascrip --json map-processes --limit 300 --min-similarity 0.25 --max-depth 5 --max-nodes 5000
```

The mapper follows bounded indexed `CALL` edges from each candidate's procedures and object/trigger scopes, aggregates Table usage from reachable procedures, and calculates Jaccard similarity over those transitive Table sets. Each candidate reports reachable procedures and call paths, contributing procedures per Table, unresolved CALL targets, and truncation state. This remains static dependency evidence: dynamic RUN targets, UI navigation, job queues, integration entry points and actual runtime execution are not inferred. Shared master Tables may connect unrelated workflows, and transitive clustering can connect members that do not all share Tables pairwise. Use the results to prioritize source-backed `trace` and `document` investigations.


## Full automatic business-process inventory

The `inventory` command orchestrates candidate ranking, bounded transitive CALL/Table mapping, and per-candidate source traces. It writes an inventory summary plus individual Markdown/JSON trace reports and heuristic cluster summaries:

```powershell
nav-intel --company datascrip inventory --source-root "data\\input\\datascrip\\datascrip.zip" --limit 100 --max-depth 5 --max-nodes 5000
```

Default output: `reports/<company>/business_process/`. Source-unavailable candidates are recorded as unavailable and do not stop the remaining candidates. Condition analysis is enabled by default; `--skip-conditions` skips IF/ELSE/CASE, assignment and filter analysis for a faster inventory pass. This command may take significant time for large exports because it traces each candidate independently. The inventory records its limits and source roots for reproducibility.

Generated reports are static evidence. They do not prove that a process was executed, that a branch was selected at runtime, or that a database transaction committed. Candidate clusters are heuristic and require business-owner review before being treated as process boundaries.


### Evidence-backed domain hints

The inventory attaches a heuristic domain hint (for example sales, purchase, inventory, warehouse, transfer, finance, production, service, integration or ownership) from the candidate object name, reachable procedure names and transitive Table names. The JSON preserves matched terms and their evidence category. Ties are reported as `ambiguous`; candidates without lexical evidence remain `unclassified`. A `moderate_heuristic` label is only a vocabulary-based hint, not confirmation of an actual business process. Validate vocabulary and classifications against Datascrip-specific objects before using them as authoritative process labels.

The inventory also emits a separate **operational role hint** using CamelCase-aware reachable procedure names and indexed Table usage kinds. Possible hints include posting/transaction, data exchange, setup/configuration, inquiry, data maintenance and undetermined. This is a static profile: it does not prove that INSERT/MODIFY/DELETE executed or that a posting transaction completed. Both domain and role evidence are retained in the candidate's `domain_classification` JSON object.


## Source-declared entry-point evidence

The `nav_ai.entrypoint_intelligence.discover_source_entrypoints(source_roots)`
API scans NAV TXT files and ZIP exports for source-declared trigger signatures,
Page `OnAction` properties, and `RunObject` properties. Each finding retains
object identity, source label, line number, section, and evidence kind.

This is an evidence inventory, not a runtime invocation log. It does not prove
that a Page Action is visible/enabled, that a trigger ran, or that a RunObject
target was opened. Job Queue targets commonly depend on configured
`Job Queue Entry` records and therefore require a separate configuration
snapshot. Event subscribers and external schedules also need separate evidence.


### Entry-point to CALL-graph tracing

The business-process inventory also writes `entrypoint_traces.json`. For each
source-declared entry object, it traverses indexed static `CALL` edges from the
object's procedures and trigger scope, retaining reachable procedure paths,
unresolved call targets, traversal limits, and explicit `RunObject` targets.
The inventory JSON includes the same result under `entrypoint_traces`.

This is deliberately object-scoped: the current dependency graph does not
represent each Page Action body as its own graph node. Therefore a Page Action
declaration is not yet a precise root for its individual action body, and
reachable procedures may include other procedures belonging to the same object.
The report must not be interpreted as an execution sequence or runtime call log.

## Individual entry-point body extraction

The business-process inventory now emits `entrypoint_bodies.json` alongside the source-declaration inventory. It extracts separate source bodies for Page Action `OnAction` handlers and supported C/AL object triggers, with stable entry identifiers, action IDs where available, and absolute source line ranges.

This is a source extraction stage only. It does not yet resolve each body's calls into independent CALL-graph roots. In particular, an Action body may contain a textual `CODEUNIT.RUN`, a local procedure call, or a typed Record method; each requires syntax-aware target resolution before it can be connected safely to the dependency graph. Until that stage is implemented, do not interpret the object-level trace as the exact call tree of an individual Action.

The extractor is intentionally conservative:
- Raw body text and source line ranges are preserved for audit.
- Action IDs are associated with the nearest parsed Action control declaration.
- Trigger bodies are isolated from the object CODE section before procedures.
- `runtime_invoked=false` remains attached to every extracted entry.
- Unusual formatting, unsupported trigger forms, dynamic dispatch and runtime UI state may remain unresolved.

The generated file is created automatically when running `nav-intel inventory`; no separate command is required.

## Per-entry-point CALL mapping

The inventory now also emits `entrypoint_call_mapping.json`. This stage attempts a separate source-to-graph mapping for each extracted Page Action or object trigger:

- Unique procedure identifiers belonging to the same NAV object are matched against the extracted entry body and become procedure roots.
- Explicit `CODEUNIT.RUN`, `REPORT.RUN`, `PAGE.RUN` and `XMLPORT.RUN` references with numeric IDs or uniquely named object references are recorded as object targets.
- Resolved procedure roots are traversed through existing static `CALL` edges, with bounded depth/node limits and call paths.
- Object-level RUN targets are deliberately not expanded into all procedures of that object: doing so would falsely imply that every procedure belongs to that Action.
- String literals are masked before identifier matching.

This is deliberately a conservative first mapping stage, not a C/AL compiler. It does not yet resolve typed variable method calls such as `MyCodeunit.RunSomething(...)`, all parameter-driven dispatch, ambiguous identifiers, event subscribers, Job Queue configuration, or dynamic RUN expressions. A local procedure identifier match is source evidence, not proof of invocation. The report sets `runtime_executed=false` and `call_order_proven=false`.

Generated inventory artifacts:
- `entrypoint_bodies.json`: isolated Action/trigger bodies.
- `entrypoint_call_mapping.json`: per-entry direct targets and CALL-reachable procedures.
- `entrypoint_traces.json`: earlier object-level entry-point trace; it must not be confused with the more precise per-entry mapping.
\n

## Extended entry-point mapping

The business-process inventory now emits `extended_entrypoints.json` alongside the existing entry-point declarations, extracted bodies and CALL mapping.

It contains five evidence families:

- **Typed variable calls:** resolves a receiver declared as `Codeunit N`, `Page N`, `Report N`, `XMLport N` or `Query N` to the target object's procedure when the graph contains one unique procedure with that name. Record variables are deliberately excluded from object-procedure resolution because their members are NAV Record APIs.
- **Dynamic RUN targets:** records `CODEUNIT.RUN`, `PAGE.RUN`, `REPORT.RUN` and `XMLPORT.RUN` argument expressions, any statically resolved object target, graph-index presence and unresolved reason. Variable expressions without a proven constant or typed declaration remain unresolved.
- **Event subscribers and publishers:** extracts `EventSubscriber` attributes and `IntegrationEvent` / `BusinessEvent` / `InternalEvent` publisher procedure declarations. It links a subscriber to a publisher when object identity and event name match uniquely. A declaration is not proof that the publisher raises the event or that the subscriber executes.
- **Job Queue evidence:** identifies Table 472 source and source objects referencing Job Queue Entry / Codeunit 448. It does not read configured Job Queue Entry rows, enabled state, schedule, parameter strings or runtime outcomes.
- **Individual Table field triggers:** extracts Table field `OnValidate`, `OnLookup`, `OnDrillDown` and `OnAssistEdit` bodies with field ID/name and source line ranges. This is distinct from Table-level triggers and does not imply that a field validation occurred.

All records retain static-evidence semantics. In particular, a resolved target is not a runtime call, an EventSubscriber declaration is not event dispatch evidence, and source references to Job Queue are not a live schedule inventory. The current analyzer is a conservative first pass; unusual variable scopes, aliases, computed RUN arguments, event publisher discovery and actual Job Queue configuration require further resolution/evidence.


### Optional Job Queue configuration snapshot

The inventory command accepts `--job-queue-snapshot <json>`. The JSON file must contain an `entries` array; each row may include `entry_no`, `object_type`, `object_id`, `status`, `earliest_start_datetime`, `next_run_datetime`, `recurring` and `parameter_string`. Example:

```json
{
  "snapshot_at": "2026-11-27T10:00:00+07:00",
  "company": "PT DATASCRIP",
  "entries": [
    {
      "entry_no": "JOB-001",
      "object_type": "Codeunit",
      "object_id": 50001,
      "status": "Ready",
      "next_run_datetime": "2026-11-27T10:15:00+07:00",
      "recurring": true,
      "parameter_string": "..."
    }
  ]
}
```

The mapper resolves the configured Object Type / Object ID against the indexed NAV object graph and records the procedure count. It deliberately redacts Parameter String content and retains only presence/length. The snapshot describes configuration at its stated time; it does not prove that the dispatcher started the job or that the job completed. Historical execution requires Job Queue Log or equivalent telemetry.

