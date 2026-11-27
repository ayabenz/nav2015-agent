# NAV 2015 Agent — Roadmap & Validation Tracker

**Branch:** `datascrip`  
**Last updated:** 2026-11-27  
**Project:** NAV Enterprise AI — Phase 1 source-analysis foundation and Datascrip stocktake audit  
**Tracker rule:** Only mark a test PASS/FAIL when its execution output or NAV evidence is recorded. Static source findings are not runtime test results.

## 1. Executive status

| Workstream | Status | Evidence / next step |
|---|---|---|
| NAV export ingestion and deterministic parsing | COMPLETE — implementation exists | CLI supports TXT, ZIP and folder inputs; rerun full suite for current baseline |
| Symbol indexing and search | COMPLETE — implementation exists | SQLite symbol index and find CLI |
| Semantic diff and change audit | COMPLETE — implementation exists | Datascrip vs original baseline reports |
| Dependency graph and impact analysis | COMPLETE — implementation exists | Graph database and Excel report generated |
| Datascrip stocktake source audit | COMPLETE — documented | Entry-point audit and related process-flow reports |
| Business-rule confirmation | PARTIAL | Accepted behavior documented in Issue #3; other policy decisions remain open |
| NAV runtime validation | BLOCKED | Requires isolated non-production NAV 2015 test company and matching Datascrip build |
| Remediation implementation | NOT STARTED / gated | Do not change posting logic until policy is confirmed and runtime cases are reproducible |
| Deterministic Code Intelligence query layer | IMPLEMENTED — first vertical slice | `nav-intel` queries existing symbol/graph SQLite databases; object/procedure/callers/callees/impact/table usage; tests and CI validation passing (99 passed, 1 opt-in test skipped by default on 2026-11-27) |
| Conditional Logic Intelligence | IMPLEMENTED — static analysis foundation | IF/ELSE/CASE parsing, metadata-backed predicates, filter paths, explicit snapshots, local assignment provenance, Boolean-specialized multi-hop VAR propagation, semantic assignment resolution, and bounded nested Record-filter composition; broader grammar validation remains open |
| Automatic entry-point discovery and direct Table-footprint mapping | IMPLEMENTED — heuristic first pass | `nav-intel discover` ranks candidates; `nav-intel map-processes` groups overlapping direct Table usage. Validated process boundaries and non-CALL entry-point semantics remain open. |\n| AI-assisted NAV reasoning / agent workflows | PLANNED | Build on deterministic query layer, conditional logic, parser, symbol index, semantic diff and dependency graph; keep source evidence traceable |

## 2. Roadmap

### Phase 1 — Deterministic NAV source-analysis foundation

- [x] Parse NAV 2015 C/AL TXT exports.
- [x] Support ZIP and folder ingestion.
- [x] Extract object metadata, fields, keys, controls/actions, procedures, variables and triggers.
- [x] Build SQLite symbol index and symbol search.
- [x] Compare company export against original baseline using semantic diff.
- [x] Classify changes as REAL, WHITESPACE ONLY or BOUNDARY ARTIFACT.
- [x] Build object dependency graph and CUSTOM / MODIFIED_STANDARD / STANDARD_UNCHANGED classification.
- [x] Generate dependency and impact-analysis reports.
- [ ] Re-run the complete test suite on the current `datascrip` HEAD and publish one canonical result.
- [ ] Reconcile historical test snapshots in Section 3; do not combine their counts.

**Exit criteria:** reproducible CLI pipeline, clean test run, versioned reports and known parser limitations documented.

### Phase 2 — Datascrip semantic and process analysis

- [x] Establish original baseline and Datascrip export inventory.
- [x] Generate semantic object/procedure change inventory.
- [x] Build dependency graph and custom-to-standard impact view.
- [x] Audit stocktake entry points across Sales, Purchase, Transfer, Warehouse, P2B, Item Journal, Ownership, Production, Job and Service routes.
- [x] Document Sales Return Order / Credit Memo flow.
- [x] Document Transfer Order, Loan and Return Loan flow.
- [x] Record accepted company behavior and unresolved business-policy decisions in [Issue #3](https://github.com/ayabenz/nav2015-agent/issues/3).
- [x] Prepare stocktake runtime test plan.
- [x] Prepare runtime environment readiness checklist.
- [ ] Review remaining process audits for coverage gaps and conflicting conclusions.
- [ ] Obtain explicit business decisions for all POLICY REQUIRED scenarios.

**Known analysis metrics (from the recorded analysis run):**

| Metric | Recorded result |
|---|---:|
| Original baseline objects | 4,168 |
| Datascrip objects | 4,696 |
| Changed objects | 491 |
| Added procedures | 242 |
| Changed procedures | 217 |
| Dependency graph objects | 4,696 |
| Dependency graph procedures | 20,246 |
| Dependency edges | 77,364 |
| Table-usage records | 49,536 |
| Custom-to-standard edges | 5,031 |

These are recorded analysis outputs, not a claim that every NAV object or indirect/dynamic dependency has been resolved. See [NAV Dependency Report](../../reports/datascrip/NAV_Dependency_Report.xlsx) in the repository.

### Phase 2.5 — Conditional Logic Intelligence (new)

**Goal:** explain why a NAV procedure takes a particular branch by connecting C/AL conditions to the underlying table, field, variable and option values. This extends the existing symbol index and dependency graph; it does not replace or rebuild them.

- [x] Initial conservative parser for nested IF / THEN / ELSE and CASE / OF / ELSE; preserve branch structure and source spans. ELSEIF is represented as nested ELSE → IF where syntax permits.
- [ ] Expand grammar coverage and validate against representative Datascrip C/AL procedures; handle edge cases in statement boundaries and CASE labels.
- [x] Add initial expression-tree normalization for comparisons, IN lists, AND / OR / NOT and parentheses; raw operands are retained.
- [x] Add evidence-backed operand descriptions for resolved fields, Option members and basic literals; mark every explanation as unevaluated.
- [ ] Complete literal typing, constant classification, and normalized Option / Enum operand semantics.
- [x] Resolve qualified Record-variable field references to NAV Table / Field identities when matching Table TXT metadata is supplied, including procedure parameters and local VAR declarations.
- [x] Resolve Option members against field OptionString values; mark missing metadata or unknown values explicitly instead of guessing.
- [ ] Extend resolution to unqualified WITH-scope fields, RecordRef/FieldRef and dynamic expressions.
- [ ] Build branch paths with parent/child relationships and explicit TRUE / FALSE / CASE-match / CASE-default outcomes.
- [x] Extract SETRANGE / SETFILTER / RESET and FIND operations, preserving arguments, source locations and resolved field metadata where available.
- [x] Implement path-sensitive filter-state tracking across IF / ELSE / CASE branches; preserve distinct states at joins rather than merging incompatible filters. Compatible-state compaction remains an optimization.
- [x] Add conservative local assignment tracking for explicit `:=` statements; attach incoming assignments to IF predicates and preserve divergent IF/CASE path alternatives. Expressions remain symbolic, not evaluated.
- [x] Add first conservative direct-call argument binding: match receiver Codeunit type, map positional actual arguments to formal parameters, resolve Record variables/Rec via TableNo and identify Boolean literals; mark VAR formals by-reference. 
- [x] Summarize explicit assignments to VAR scalar parameters and qualified fields of VAR Record parameters; attach these symbolic effects to matching caller arguments. Nested-call effects, complete caller-state propagation and runtime values remain open.
- [x] Propagate supported direct-call VAR mutations into caller assignment flow when unconditional or fully selected by Boolean literal arguments; automatic caller procedure analysis now exposes the mutation to subsequent IF predicates. Function return values, multi-hop call chains and unresolved conditional effects remain open.
- [x] Add initial nav-intel conditions command with explicit source-file and optional object/procedure selection; return branch tree, raw predicates and source spans.
- [x] Add automatic source discovery for a CALL-graph trace: resolve exact object type/ID against TXT/ZIP/directory exports, use symbol-index source labels to disambiguate, and report missing/ambiguous exports and object-level CALL targets explicitly. Conditions integration into object/procedure queries remains open.
- [x] Add unit fixtures for nested IF/ELSE, CASE arms/default, comment/string masking and source line spans.
- [x] Add fixtures for Option values, qualified field comparisons and unresolved metadata.
- [x] Add fixtures for SETRANGE clearing, SETFILTER placeholders, RESET invalidation, FINDFIRST lookup annotation and path isolation across IF / ELSE / CASE.
- [x] Add initial fixtures for literal and Record-field assignments, reassignment, IF/ELSE divergence and unknown-call invalidation. ELSEIF and broader unresolved/dynamic expression coverage remain open.
- [x] Trace simple intra-procedural assignment provenance transitively (local variable → Record field → IF predicate), preserving source locations and unresolved/cycle markers. Regression tests included in the passing 98-test suite (2026-11-27).
- [x] Add `--call-source` to `nav-intel conditions` for direct call-site binding evidence; repeated caller exports are supported. Regression fixtures cover typed `Rec`, Boolean literals, comments and receiver type mismatch; included in the passing 98-test suite (2026-11-27).
- [x] Document static-analysis limits and avoid presenting inferred branch reachability as runtime fact.
- [x] Add a separate pure evaluator for explicitly supplied Record snapshots; preserve provenance and return indeterminate for missing/unsupported values.
- [ ] Add NAV runtime evidence integration only as a separate later capability; a supplied snapshot evaluation is not proof of historical execution.

**Design boundary:** static analysis explains the predicates and possible paths encoded in source. It cannot say which branch actually ran for a particular document unless the corresponding runtime values and execution context are supplied. SQL/current table values must never be silently treated as proof of historical execution.

**Initial data model (implementation may evolve):** conditions / conditional_branches store object, procedure, condition ID, parent condition, branch type, normalized expression, source file and line range; condition_operands store operand text, resolved table/field IDs, operator, expected value and value type. Keep raw expression and resolution diagnostics so conclusions remain auditable.

**Exit criteria:** for a selected procedure, nav-intel can explain each supported branch in readable form (for example, Sales Header.Status = Released → TRUE path / ELSE path), identify source lines and resolved field metadata, and explicitly label unknown or runtime-dependent values.

### Phase 3 — Stocktake runtime validation

**Current status: BLOCKED — environment access required.** See [Issue #4](https://github.com/ayabenz/nav2015-agent/issues/4) and [environment readiness checklist](./stocktake/STOCKTAKE_RUNTIME_ENVIRONMENT_READINESS.md).

- [x] Define evidence requirements and safe test conditions.
- [x] Define company-confirmed scenarios ST-001 through ST-008.
- [x] Separate policy-required scenarios from company-confirmed scenarios.
- [ ] Provision isolated non-production NAV test company with matching Datascrip objects/build.
- [ ] Capture Table 50063 configuration, test/control item, location, Owner and opening balances.
- [ ] Execute ST-001 — Sales Return Order Receive via Codeunit 50081.
- [ ] Execute ST-002 — Sales Return Order invoice-only via Codeunit 50082; preserve the approved no-duplicate-check exception.
- [ ] Execute ST-003 — Transfer Order shipment OUT via Codeunit 5704.
- [ ] Execute ST-004 — Transfer Order receipt IN via Codeunit 5705.
- [ ] Execute ST-005 — Loan shipment / Return Loan receipt through shared transfer posting codeunits.
- [ ] Execute ST-006 — Warehouse Shipment with Transfer Line source.
- [ ] Execute ST-007 — Warehouse Receipt with Transfer Line source.
- [ ] Execute ST-008 — Warehouse Activity with Transfer Line source; inspect pre-check COMMIT effects.
- [ ] Run negative/control cases (no active rule, non-matching item/location, direction, date window, multi-line rollback).
- [ ] Compare before/after Item Ledger Entry, Value Entry, Ownership Ledger Entry, posted documents and warehouse state.
- [ ] Publish runtime results with evidence references; no result is PASS until the actual NAV execution evidence is attached.

### Phase 4 — Policy decisions and targeted remediation

- [ ] Confirm whether non-WMS P2B Negative Adjustment posting is blocked during stocktake.
- [ ] Confirm whether same-location Ownership Transfer is blocked.
- [ ] Confirm Purchase Invoice receipt and Purchase Credit Memo shipment policy.
- [ ] Confirm Purchase batch posting and warehouse purchase posting policy.
- [ ] Confirm job-queue execution-time validation policy.
- [ ] Confirm manual Item Journal, Item Reclass, Assembly, Production, Job, Service and Warehouse Activity movement policy.
- [ ] Confirm Undo/reversal behavior and Warehouse Journal reclassification policy.
- [ ] Preserve Physical Inventory Journal operation for posting stocktake differences unless the company explicitly decides otherwise.
- [ ] Design the smallest targeted changes for confirmed gaps; do not add blanket checks to Codeunit 80, 90 or 22.
- [ ] Implement approved changes with source-level regression tests.
- [ ] Run runtime regression tests for each changed route.
- [ ] Review and merge the remediation PR.

### Phase 5 — NAV AI agent capabilities

- [ ] Define agent use cases and safety boundaries (read-only by default).
- [ ] Expose deterministic search, object details, procedure details and dependency/impact queries as tools.
- [ ] Require citations to source object, procedure and line/range for every code conclusion.
- [ ] Add multi-hop trace workflows for posting, table writes, callers and conditional branch paths.
- [ ] Add regression/evaluation dataset from known NAV questions and verified answers.
- [ ] Add optional SQL metadata/runtime evidence integration with least-privilege read-only access.
- [ ] Add change-impact and test-scenario generation grounded in the dependency graph and conditional logic.
- [ ] Keep code modification and posting execution outside autonomous agent permissions unless explicitly approved.

## 3. Test and validation history

The repository README currently records an earlier test snapshot of **44 passed, 4 failed**. The four failures were attributed there to missing, previously deleted `data/incoming/*.txt` fixtures in `test_real_exports.py`; they were described as pre-existing. A later conversation run recorded **27 collected tests, all passing** for the then-current test selection.

These are separate historical runs with different collection scopes. They must not be added together or represented as the current full-suite status. The current canonical full-suite result is **59 passed** on `datascrip` commit `11006682e4d5b9a049b5061ca9923c27351ffe2b` (GitHub Actions run [#57](https://github.com/ayabenz/nav2015-agent/actions/runs/45922644494)).

| Validation | Result | Classification | Notes |
|---|---|---|---|
| Earlier repository test snapshot | 44 passed, 4 failed | Historical automated test run | README attributes failures to absent `data/incoming/*.txt` fixtures |
| Later focused test run | 27 passed | Historical automated test run | Output in project conversation showed all 27 collected tests passing |
| Previous canonical full suite — 2026-11-27 | 59 passed in 0.53s | PASS — GitHub Actions | Commit `11006682e4d5b9a049b5061ca9923c27351ffe2b`; [run #57](https://github.com/ayabenz/nav2015-agent/actions/runs/45922644494) | 
| Previous full suite — 2026-11-27 | 73 passed in 0.74s | PASS — GitHub Actions | Commit `abdc19354b6b984e83e96fc60b11b09cc981adf4`; [run #117](https://github.com/ayabenz/nav2015-agent/actions/runs/45924798203) |
| Previous full suite — 2026-11-27 | 77 passed in 0.75s | PASS — GitHub Actions | Commit `023426daf4c2c89f458ca1b1854feced9975ba28`; [run #132](https://github.com/ayabenz/nav2015-agent/actions/runs/45926585814) |
| Current full suite — 2026-11-27 | 80 passed in 0.45s | PASS — GitHub Actions | `python -m pytest -q`; commit `1ddf702a61167dab607700ba6b131087ee6cf6e7`; [run #142](https://github.com/ayabenz/nav2015-agent/actions/runs/45926903904) |
| Parser / ingest / diff / audit / depgraph / search / ZIP support | Reported passing in README snapshot | Historical automated coverage | Confirm again in canonical full-suite run |
| Stocktake source audit | Completed | Static analysis | Does not prove NAV runtime behavior |
| Stocktake runtime ST-001…ST-008 | Not executed | Blocked | Requires non-production NAV environment |
| Policy-required scenarios ST-101…ST-311 | Not executed | Pending policy | Do not classify as defects until business owner confirms expected behavior |

## 4. Stocktake runtime test matrix

| Case | Scenario | Expected / policy | Status |
|---|---|---|---|
| ST-001 | Sales Return Order Receive, Codeunit 50081 | Company-confirmed: block before posting | BLOCKED — no NAV runtime |
| ST-002 | Sales Return Order invoice-only, Codeunit 50082 | Company-confirmed: proceed; no duplicate stocktake check | BLOCKED — no NAV runtime |
| ST-003 | Transfer Shipment OUT, Codeunit 5704 | Company-confirmed: block before posting | BLOCKED — no NAV runtime |
| ST-004 | Transfer Receipt IN, Codeunit 5705 | Company-confirmed: block before posting | BLOCKED — no NAV runtime |
| ST-005 | Loan / Return Loan | Company-confirmed: inherit Codeunit 5704/5705 checks | BLOCKED — no NAV runtime |
| ST-006 | Warehouse Shipment, Transfer Line source | Company-confirmed: transfer posting boundary blocks | BLOCKED — no NAV runtime |
| ST-007 | Warehouse Receipt, Transfer Line source | Company-confirmed: transfer posting boundary blocks | BLOCKED — no NAV runtime |
| ST-008 | Warehouse Activity, Transfer Line source | Company-confirmed: transfer posting boundary blocks; inspect COMMIT side effects | BLOCKED — no NAV runtime |
| ST-101…ST-109 | Purchase routes | Business policy required | PENDING POLICY |
| ST-201…ST-204 | P2B / Ownership routes | Business policy required | PENDING POLICY |
| ST-301…ST-311 | Item Journal / inventory / production / service / undo routes | Business policy required; preserve Physical Inventory Journal exception | PENDING POLICY |

**Important accepted rule:** Codeunit 50081 checks before Codeunit 80; Codeunit 50082 invoice-only route intentionally does not repeat that check. This is company-approved behavior and must not be changed solely for consistency.

## 5. Current blockers and required actions

1. **Runtime blocker:** an environment owner must provide an isolated non-production NAV 2015 company with the matching Datascrip application objects/build, Table 50063 setup, test data and authorized test user. Do not provide production credentials or production database access.
2. **Policy blocker:** business owner must record expected behavior for the policy-required routes before they are treated as defects or remediated.
3. **Test baseline blocker:** run the full automated test suite at current branch HEAD and record one canonical result.

## 6. Source documents and tracking

- [Stocktake entry-point audit](./stocktake/STOCKTAKE_ENTRYPOINT_AUDIT.md)
- [Stocktake runtime test plan](./stocktake/STOCKTAKE_RUNTIME_TEST_PLAN.md)
- [Runtime environment readiness](./stocktake/STOCKTAKE_RUNTIME_ENVIRONMENT_READINESS.md)
- [Issue #3 — accepted behavior and policy decisions](https://github.com/ayabenz/nav2015-agent/issues/3)
- [Issue #4 — non-production runtime environment blocker](https://github.com/ayabenz/nav2015-agent/issues/4)


**Implementation update (2026-11-27):** `nav_ai.semantic_conditions` now parses Table TXT field definitions and OptionString metadata, resolves declared Record variables to Table IDs, and annotates IF/CASE expressions with field and Option resolution evidence. The `conditions` CLI accepts repeatable `--table-source` arguments. Current resolver coverage is intentionally limited to qualified `RecordVariable.Field` references; WITH-scope and data-flow remain open. See `docs/CODE_INTELLIGENCE.md` for an actual Stocktake command.


**Implementation update (2026-11-27 — Record filter flow):** Added `nav_ai.record_filters` and integrated it into `nav-intel conditions`. The analyzer extracts SETRANGE / SETFILTER / RESET and FINDFIRST / FINDLAST / FINDSET operations, preserves raw filter arguments and resolves filter fields against supplied Table metadata. Procedure-local Record declarations are included in variable resolution. The path-sensitive pass now forks state at IF/ELSE and CASE arms, preserves each filter state through subsequent statements, and attaches all path alternatives to direct FINDFIRST predicates. It never evaluates predicate values or claims a lookup found a row. Tests cover filter accumulation, clearing, RESET, IF/CASE branch isolation, NOT FINDFIRST annotation, the actual Stocktake Sales Header OUT / IN / unfiltered document-type alternatives, initial expression normalization, metadata-backed operand explanations, explicit snapshot evaluation, CLI snapshot annotation, Record parameter resolution, and conservative indeterminate handling when metadata is missing. GitHub Actions run [#57](https://github.com/ayabenz/nav2015-agent/actions/runs/45922644494) passed on commit `11006682e4d5b9a049b5061ca9923c27351ffe2b`: `59 passed in 0.53s`.


**Implementation update (2026-11-27 — Static assignment flow):** Added `nav_ai.assignment_flow` and integrated it into `nav-intel conditions`. The first conservative pass tracks explicit local-variable and qualified Record-field assignments, links known assignments to later IF predicates, preserves separate incoming values across IF/ELSE and CASE paths, and invalidates tracked values when an unknown procedure call is encountered. Assignment expressions remain symbolic and are never evaluated. Interprocedural parameter flow, triggers, WITH scopes and implicit database mutations remain unsupported. Initial regression tests cover literal assignment, Record-field assignment, reassignment, divergent IF/ELSE values and unknown-call invalidation. GitHub Actions validation is running for the implementation commits; do not update the canonical test count until the run completes.


**Implementation update (2026-11-27 — Direct call bindings):** Added `nav_ai.interprocedural.analyze_direct_call_bindings` and the repeatable `--call-source` option to `nav-intel conditions`. The first slice binds direct `Receiver.Procedure(...)` actual arguments to parsed formal parameters, checks the receiver's declared Codeunit ID, recognizes Record variables and `Rec` via `TableNo`, identifies Boolean literals, and marks `VAR` formals by-reference. It deliberately does not infer runtime values. Explicit callee-side VAR mutations are summarized by `nav_ai.var_mutation` and attached to matching by-reference arguments. A limited caller-state effect map now maps unconditional assignments through simple actual arguments; conditional mutation paths and complete caller-state propagation remain open. Regression tests are included in the passing full-suite run [#117](https://github.com/ayabenz/nav2015-agent/actions/runs/45924798203).


**Implementation update (2026-11-27 — VAR parameter mutation summaries):** Added `nav_ai.var_mutation`. For a selected callee procedure, it extracts explicit assignments to `VAR` scalar parameters and qualified fields of `VAR Record` parameters, preserving source line and IF/ELSE/CASE path. The `--call-source` result now associates these effects with the corresponding by-reference actual argument at each recognized direct call site. Values remain symbolic; this is not a complete side-effect model and does not follow nested calls. Regression tests are included in the later full-suite validation [#132](https://github.com/ayabenz/nav2015-agent/actions/runs/45926585814): `77 passed in 0.75s`.


**Implementation update (2026-11-27 — Limited caller-side VAR propagation):** `analyze_assignment_flow` now accepts an optional `call_effects` map keyed by caller statement line. At a recognized call statement, it invalidates pre-call facts and restores only mapped explicit VAR assignments. `build_caller_var_effect_map` maps unconditional callee scalar assignments and qualified VAR Record field assignments through simple identifier arguments. Conditional callee mutations are intentionally excluded from definite caller state because callee branch predicates have not yet been translated into caller path alternatives. Complex actual arguments are not mapped. CLI output exposes this map as `caller_state_effect_map`; the CLI does not yet automatically reparse and analyze the caller's post-call procedure body. Full suite [#132](https://github.com/ayabenz/nav2015-agent/actions/runs/45926585814): **77 passed in 0.75s**.


**Implementation update (2026-11-27 — Call-site Boolean branch specialization):** Added `annotate_callsite_boolean_branches`. When a direct call passes a Boolean literal to a Boolean formal, simple callee IF predicates referencing that formal are annotated with the compatible and incompatible branch outcomes. This is particularly useful for the Datascrip Stocktake path: Codeunit 50081 calls `BlockStocktakeSalesHeader(Rec, FALSE)`, and Codeunit 50107 tests `IF CreateWhseShipment THEN`; for that call site, the ELSE branch is compatible and the THEN branch is incompatible. The tree is annotated, not rewritten; no branch is claimed to have executed. Compound predicates and nonliteral Boolean arguments remain unresolved. Full suite [#142](https://github.com/ayabenz/nav2015-agent/actions/runs/45926903904): **80 passed in 0.45s**.


**Implementation update (2026-11-27 — Conditional interprocedural VAR propagation and caller flow):** Callee VAR mutations are now specialized against Boolean literals supplied at each direct call site. Mutations on incompatible paths are discarded; only unconditional or fully resolved compatible paths enter `caller_state_effect_map`. The `conditions --call-source` workflow automatically reparses caller procedures containing those call sites and runs path-sensitive assignment analysis with the mapped effects. The result includes `caller_assignment_flow` and control-flow nodes, allowing later caller IF conditions to expose the symbolic value and its callee source provenance. Unknown/compound predicates, nonliteral Boolean arguments, complex actual arguments, nested calls, and implicit effects remain unresolved. No runtime execution is inferred. Regression coverage added for propagation into a caller IF; latest CI is tracked separately and the test count is not updated until it passes.


**Validation (2026-11-27):** The conditional interprocedural VAR propagation and automatic caller-flow implementation passed the full GitHub Actions test suite: [run #161](https://github.com/ayabenz/nav2015-agent/actions/runs/45928398309), **86 passed in 0.87s**. The regression test confirms a callee VAR Record-field mutation is visible in the caller's subsequent IF assignment context. A later test-only refinement is also running separately.


**Implementation update (2026-11-27 — bounded nested-call propagation):** `nav-intel conditions` now accepts repeatable `--nested-source` exports. It analyzes direct callees invoked by the selected procedure, specializes supported Boolean branches from literal arguments, and includes resulting mapped VAR effects in the selected procedure's mutation summary. Those effects can then be propagated to the selected procedure's own callers via `--call-source`, covering a bounded A → B → C chain. Traversal now supports configurable bounded recursion through `--max-call-depth`; unbounded whole-application call-graph discovery remains open. Regression fixtures cover B passing `FALSE` to C and a three-Codeunit chain where C delegates to D.


**Validation (2026-11-27):** Bounded nested-call VAR propagation passed the complete GitHub Actions suite: [run #172](https://github.com/ayabenz/nav2015-agent/actions/runs/45928951416), **88 passed in 0.77s**. This validates the new nested mutation-summary path and the existing direct caller propagation tests; arbitrary-depth call graph traversal remains future work.


**Validation (2026-11-27 — bounded multi-hop):** The configurable `--max-call-depth` implementation passed [GitHub Actions run #176](https://github.com/ayabenz/nav2015-agent/actions/runs/45929145882), **89 passed in 0.49s**. Regression coverage includes a three-Codeunit chain where the deepest callee's Boolean literal selects its ELSE-side Record field mutation, which is summarized through the intermediate Codeunit. This validates the bounded source-analysis fixture, not runtime NAV execution.


### Phase 2.6 — Automatic source discovery and call tracing

- [x] Add `nav-intel trace` to traverse existing `CALL` edges from an object or procedure with depth/node limits, including object-level and trigger-scope roots.
- [x] Resolve reachable objects against user-supplied TXT, ZIP, or directory roots; use symbol-index `source_file` labels when multiple exports share an object identity.
- [x] Report source procedure absolute line ranges, shortest discovered call paths, direct Table usage, aggregate process summary/origin counts, and explicit missing/ambiguous source states.
- [x] Report object-level/non-procedure CALL targets (such as possible `Var.RUN` edges) instead of expanding them into guessed procedures.
- [x] Feed discovered source files directly into IF/ELSE/CASE, assignment and Record-filter analysis; automatically load Table metadata from the same source roots with explicit missing/ambiguous statuses.
- [x] Validate tracing against the full Datascrip export with automatic conditions and Table metadata discovery; review uncovered dynamic/trigger call paths remains open.

**Design boundary:** trace follows only existing dependency-graph `CALL` edges. It is a source-discovery and call-graph traversal layer, not proof that a call or branch ran in NAV.


**Validation (2026-11-27 — automatic trace and conditions):** [GitHub Actions run #209](https://github.com/ayabenz/nav2015-agent/actions/runs/45930614213) passed: **97 tests in 0.81s**. Coverage includes TXT/ZIP source discovery, exact graph traversal, missing/ambiguous source handling, object/trigger roots, absolute source line offsets, and automatic condition analysis with Table Option metadata. This is parser/source-fixture validation; no live NAV runtime execution was performed.


**Validation update (2026-11-27 — explicit source/metadata statuses):** [GitHub Actions run #214](https://github.com/ayabenz/nav2015-agent/actions/runs/45930876706) passed: **98 tests in 0.74s**. Automatic condition analysis now reports `source_unavailable`, `procedure_not_found`, or `analyzed` per procedure and lists required Table IDs missing from the supplied source roots. No runtime NAV execution is implied.


**Full-export validation (2026-11-27):** [GitHub Actions run #216](https://github.com/ayabenz/nav2015-agent/actions/runs/45931034390) completed the full `data/input/datascrip/datascrip.zip` Stocktake trace with `analyze_conditions=True`: **99 passed in 272.76s**. The integration test was subsequently split into a fast default Stocktake-source check and an opt-in full ZIP check (`NAV_RUN_FULL_DATASCRIP_TRACE=1`) to avoid imposing a multi-minute full-export scan on every ordinary CI run. Static source analysis only; no NAV runtime was executed.


**Fast CI validation (2026-11-27):** [GitHub Actions run #223](https://github.com/ayabenz/nav2015-agent/actions/runs/45931717791) passed: **99 passed, 1 skipped in 0.96s**. The skipped test is the opt-in full ZIP scan; that full Datascrip scan was separately executed and passed in run #216.


**Process-trace output validation (2026-11-27):** [GitHub Actions run #233](https://github.com/ayabenz/nav2015-agent/actions/runs/45932114995) passed: **99 passed, 1 opt-in full-export test skipped in 1.29s**. The trace now returns a representative shortest call path per procedure, preserves all discovered edges (including alternate/cycle edges), and aggregates table usage and IF/CASE counts into `process_summary`.


### Phase 2.7 — Automatic interprocedural analysis on traced edges

- [x] For every discovered CALL edge, resolve caller/callee source and attempt direct receiver/procedure argument binding.
- [x] Summarize explicit callee VAR parameter and Record-field mutations and map supported effects back to simple caller arguments.
- [x] Apply existing Boolean-literal path specialization so incompatible mutations are discarded and unresolved paths are not treated as definite.
- [x] Preserve unavailable, ambiguous, nonmatching and unsupported edge states explicitly; retain `runtime_evaluated: false`.
- [x] Compose mutation summaries across multiple graph hops with bounded propagation rounds; cycles cannot expand beyond the configured depth.
- [ ] Feed the composed graph effects into every reached procedure's condition/assignment-flow output so downstream IF/ELSE nodes expose multi-hop symbolic context.
- [x] Resolve propagated Record-field assignment targets against Table/Field metadata and validate Option RHS members against OptionString; Direct and bounded multi-hop interprocedural Record-filter effects are propagated into caller path states.

**Current boundary:** this phase provides direct per-edge bindings and symbolic VAR effects. It does not yet perform recursive graph-wide effect composition or assert that any branch/call executed in NAV.


**Validation (2026-11-27 — automatic interprocedural edge summaries):** [GitHub Actions run #239](https://github.com/ayabenz/nav2015-agent/actions/runs/45933401095) passed: **101 passed, 1 opt-in full-export test skipped in 1.66s**. Coverage includes direct traced-edge call binding, Boolean-specialized explicit VAR Record-field effects, and explicit missing-source status. The run validates static fixtures and the fast suite; recursive graph-wide effect composition remains open.


**Implementation update (2026-11-27 — bounded multi-hop VAR composition):** `trace` now accepts `--max-interprocedural-depth` (default 2). Explicit VAR mutation summaries are iteratively composed from callee to caller across the discovered CALL edges, with a fixed propagation-round bound to prevent unbounded cycle traversal. Procedure-level summaries and composed per-edge caller effect maps are included in the JSON. Regression tests cover a three-Codeunit A → B → C chain and depth-zero behavior. The next remaining integration is to inject these composed effects into all reached procedures' condition-analysis assignment contexts, rather than only exposing them in interprocedural summaries.


**Implementation update (2026-11-27 — condition-context integration):** The bounded interprocedural effect maps are now injected into assignment-flow analysis for each reached caller procedure. Call-site line numbers are translated from object-local coordinates to absolute source-file lines before injection. This makes multi-hop Record-field mutations visible in downstream IF nodes' `assignment_context`, with an `interprocedural_call_effect_count` per procedure. A three-Codeunit trace fixture validates A → B → C propagation into both A and B's later IF contexts. CI validation for this integration is running.


**Implementation update (2026-11-27 — semantic assignment enrichment):** Assignment events and IF-node incoming assignment alternatives now carry `semantic_assignment` metadata. Record variable declarations resolve target Table IDs; target fields resolve to field IDs/types; Option RHS members are checked against the field's exported OptionString and classified as resolved, unverified, or unresolved. This enriches the A → B → C multi-hop fixture so the downstream caller context identifies the Sales Header Status field and verifies the Released Option member without evaluating it. Record-filter-state correlation remains the next enhancement.


**Validation (2026-11-27 — multi-hop condition and assignment semantics):** [GitHub Actions run #261](https://github.com/ayabenz/nav2015-agent/actions/runs/45935404655) passed: **108 passed, 1 opt-in full-export test skipped in 1.38s**. Regression coverage verifies A → B → C VAR-field propagation into both caller IF assignment contexts, semantic Table/Field resolution, OptionString membership, unresolved/unknown Option handling, and Table metadata stored in a separate field-property block. The earlier failed run exposed that the Table parser did not read OptionString when its property block followed a closed field declaration; that parser case is now covered and fixed.


**Implementation update (2026-11-27 — direct interprocedural Record filters):** Added a separate filter-effect summary for direct CALL edges. Explicit callee `SETRANGE`, `SETFILTER`, `SETRANGE(Field)` clear, and `RESET` operations on typed VAR Record parameters are mapped to simple caller Record arguments. Supported Boolean call literals specialize conditional filter operations. With condition analysis enabled, these effects are applied at the caller's call statement and appear in later lookup snapshots. A regression fixture verifies a callee-set Sales Header Status filter is visible at the caller's subsequent FINDFIRST. Nested filter-effect composition remains open.


**Validation (2026-11-27 — direct interprocedural Record filters):** [GitHub Actions run #277](https://github.com/ayabenz/nav2015-agent/actions/runs/45936281636) passed: **109 passed, 1 opt-in full-export test skipped in 1.28s**. The fixture confirms a Boolean-specialized `SETRANGE` on a callee's `VAR Record 36` parameter is mapped to the caller's Record variable and appears in the caller's subsequent `FINDFIRST` active-filter snapshot. During validation, direct call binding was corrected to normalize `VAR Record N` declarations as `Table N`, and filter argument text is now retained in the effect summary. No NAV runtime was executed.


**Implementation update (2026-11-27 — bounded nested Record-filter composition):** The traced-edge filter analyzer now builds procedure-level filter summaries and iteratively maps explicit `RESET`, `SETRANGE`, `SETFILTER`, and field-clear effects through typed `VAR Record` arguments across discovered CALL edges. It uses the same `--max-interprocedural-depth` bound as VAR-assignment propagation, specializes supported Boolean literal paths at each boundary, and injects composed effects into caller path-sensitive lookup analysis. Added an A → B → C regression fixture in which C filters a Record passed through B and A's subsequent FINDFIRST receives the filter. The first CI attempt exposed an over-escaped Record-type matcher; this was corrected in commit `40c4d569ba3527f79f9ca6f056b32dba09e369ab`. Validation: GitHub Actions [run #45937720261](https://github.com/ayabenz/nav2015-agent/actions/runs/45937720261) on commit `fc81717ece7c3671e8f6f0bf59c8af5429377980` passed: **110 passed, 1 opt-in full-export test skipped in 1.72s**. The nested regression confirms that C's explicit filter and its raw argument survive propagation through B into A's later FINDFIRST snapshot. Earlier failed attempts exposed and corrected a Record-type regex escaping issue and loss of filter arguments in intermediate summaries. No NAV runtime or SQL query was executed. No NAV runtime or SQL query was executed.


**Implementation update (2026-11-27 — snapshot evaluator contract and type safety):** Added `docs/RECORD_SNAPSHOT_CONTRACT.md` to define the JSON input schema, native value expectations, supported predicate subset, provenance and indeterminate semantics. Tightened `snapshot_evaluator.py` so Python's bool/int equality and comparisons across incompatible primitive types cannot silently produce TRUE/FALSE; these now return an indeterminate result with a diagnostic. Added focused regression fixtures for Boolean fields and cross-type comparisons. The focused and full test suites have **not yet been executed for these latest commits**; do not treat this increment as validated until CI/full-suite evidence is available. Snapshot evaluation remains caller-supplied evidence, not NAV runtime execution.


**Implementation update (2026-11-27 — predicate-level snapshot explanation):** Snapshot evaluation now emits an ordered `explanation` trace for individual comparisons and parent Boolean operators, including resolved values and TRUE/FALSE/indeterminate results. IF nodes expose `selected_branch` as THEN, ELSE or UNKNOWN; UNKNOWN is preserved when snapshot evidence is incomplete. Added a regression test for comparison-level and combined AND results. Focused/full CI validation for the latest commits is still pending; do not report these tests as passing until a run completes. This remains evaluation against caller-supplied data, not evidence that NAV executed the branch.


**Validation (2026-11-27 — snapshot predicate explanation and fixture correction):** GitHub Actions [run #46014884764](https://github.com/ayabenz/nav2015-agent/actions/runs/46014884764) passed on commit `583cf83ae9a870b9f05c55d13e48ce4bb642a6e0`: **123 passed, 1 skipped in 1.35s**. The run includes the type-safety, per-comparison explanation, IF selected-branch, and regression coverage. The skipped test is the opt-in full Datascrip export test. A previously failing assignment-flow fixture contained escaped backslash-n text rather than actual newlines; the fixture was corrected. This validates the automated source fixtures only, not NAV runtime execution.


**Implementation update (2026-11-27 — selected-branch effect summaries):** Added `nav_ai.branch_effects` to classify recognizable effects beneath an IF branch: ERROR, MESSAGE, CONFIRM, EXIT, COMMIT, Record writes (INSERT/MODIFY/DELETE/RENAME), Record validation (VALIDATE/TESTFIELD/FIELDERROR), Record filters, and CODEUNIT/REPORT/PAGE RUN calls. Snapshot output now includes `branch_effects` for the selected branch, or separately labeled possible TRUE/FALSE branch effects when the predicate is indeterminate. Nested IF effects are narrowed only when that nested IF also has a determinate snapshot result; nested CASE arms remain marked unevaluated. Source lines are preserved and every effect carries `runtime_executed=false`. Tests cover classification, nested uncertainty, and selected nested paths. CI validation is pending for these latest commits.


**Validation (2026-11-27 — branch effect summaries):** GitHub Actions [run #46015531881](https://github.com/ayabenz/nav2015-agent/actions/runs/46015531881) passed on commit `00efecc15fb74cd2960d39789b4eb39298518b7f`: **127 passed, 1 skipped in 1.26s**. Coverage includes classification of ERROR/MESSAGE/CONFIRM/EXIT/COMMIT, Record writes/validation/filter calls, object RUN calls, selected and indeterminate branches, and nested branch certainty. The opt-in full Datascrip ZIP test remains skipped in the default suite. The tests validate source parsing and classification, not NAV runtime execution.


**Implementation update (2026-11-27 — broader NAV Record effects):** Expanded branch-effect classification to include Record bulk writes (`DELETEALL`, `MODIFYALL`), lookups (`GET`, `FIND`, `FINDFIRST`, `FINDLAST`, `FINDSET`, `ISEMPTY`, `COUNT`), and calculations (`CALCFIELDS`, `CALCSUMS`). EXIT with a return expression is also recognized. These remain source-level classifications, not proof of database persistence. Regression tests added; CI pending.


**Validation (2026-11-27 — expanded branch effect analysis):** GitHub Actions [run #46015849420](https://github.com/ayabenz/nav2015-agent/actions/runs/46015849420) passed on commit `6429312dda59015f36724b365a2f52b5bc7483d4`: **128 passed, 1 skipped in 1.51s**. This includes source-level branch effect classification for record lookups, calculations, bulk writes and EXIT(value), plus selected/nested branch certainty. The skipped test is the opt-in full Datascrip ZIP test. No NAV runtime was executed.


**Implementation update (2026-11-27 — cross-procedure business-flow inventory):** `nav-intel trace --analyze-conditions` now returns `business_flow`, one evidence bundle per reachable procedure: graph call path, direct table usage, source resolution, and a source-level effect inventory. The inventory preserves all IF/ELSE and CASE branch predicates instead of assuming a branch executed. Process summary adds effect counts. New tests cover IF branches, CASE arms/default, and unconditional procedure effects. CI validation passed: GitHub Actions run #46016359498 reported 132 passed, 1 skipped. The skipped test is the opt-in full Datascrip ZIP integration test.


**Validation (2026-11-27 — cross-procedure business-flow trace):** GitHub Actions [run #46016359498](https://github.com/ayabenz/nav2015-agent/actions/runs/46016359498) passed on commit `c355ac31ded5f609841cf16ed431209f4256c47a`: **132 passed, 1 skipped in 0.98s**. This includes an integration fixture proving that a reachable callee's call path, table usage, both IF branches, and unconditional procedure effects are assembled in `business_flow`. The skipped test is the opt-in full Datascrip ZIP trace. This validates the synthetic integration fixture, not the live Datascrip NAV environment.

**Implementation update (2026-11-27 — business-process report generator):** Added `nav-intel document` to run the dependency-graph trace and write paired Markdown and JSON artifacts. Markdown documents call paths, source resolution, direct/aggregate table usage, branch effects with source references, unresolved call targets, and evidence limitations. JSON preserves the complete trace for agent ingestion. Added tests for report content, paired output files, and safe filenames. GitHub Actions [run #46016877573](https://github.com/ayabenz/nav2015-agent/actions/runs/46016877573) passed on commit `f82d28d98e1726be1c8edc14ea70b2f590d6c453`: **135 passed, 1 skipped in 1.00s**. The skipped test is the opt-in full Datascrip ZIP integration test; no NAV runtime was executed.


**Implementation update (2026-11-27 — custom/standard process boundary mapping):** Each `business_flow` entry now retains its object-origin classification. Trace also emits `origin_transitions` for discovered procedure CALL edges crossing origin classes (for example CUSTOM → STANDARD_UNCHANGED). The Markdown generator includes a dedicated boundary section to highlight where company customizations enter standard NAV and vice versa. These are graph relationships, not runtime execution claims.

**Validation (2026-11-27 — custom/standard process boundaries):** GitHub Actions [run #46017163658](https://github.com/ayabenz/nav2015-agent/actions/runs/46017163658) passed on commit `d5bf0b352361776641cff254bcab694dc4b4f5a0`: **136 passed, 1 skipped in 1.62s**. The skipped test remains the opt-in full Datascrip ZIP integration test. The tests validate synthetic graph fixtures and report rendering, not live NAV runtime behavior.


**Implementation update (2026-11-27 — automatic process entry-point discovery):** Added `nav-intel discover` and a deterministic candidate-ranking module. It inventories Page, Report, XMLport, and Codeunit objects, prioritizes CUSTOM/MODIFIED_STANDARD objects, and ranks by indexed graph connectivity and procedure count. Unchanged standard objects are excluded by default and can be included explicitly. Results are labeled `heuristic_candidate`; no candidate is asserted to be a confirmed business process or runtime entry point. Unit tests cover ranking, standard-object filtering, inclusion override, and limit validation. CI validation pending.


### Phase 2.6 — Automatic business-process discovery and mapping

- [x] Rank candidate entry objects from Page, Report, XMLport and Codeunit metadata plus graph connectivity.
- [x] Group candidate entry objects using pairwise Jaccard similarity of Table-usage sets aggregated across bounded CALL-reachable procedures; retain call paths, contributing procedure evidence, unresolved targets and explicit heuristic semantics.
- [ ] [x] Extend each candidate's Table footprint through bounded, CALL-only reachable procedure/object traversal, retaining call paths and unresolved edge targets.
- [ ] Distinguish UI entry points, scheduled/integration entry points and internal helpers using trigger/action/job-queue evidence.
- [ ] Generate process maps with candidate roots, reachable procedures, Tables, source references, branch effects and unresolved edges.
- [ ] Evaluate clustering against manually audited Datascrip process examples; tune thresholds only from evidence.

**Current boundary:** direct Table overlap is a prioritization heuristic. It is not yet transitive process mapping and must not be presented as a complete business-process inventory.


### Phase 2.7 — Automated full business-process inventory

- [x] Orchestrate ranked entry-point discovery and transitive CALL/Table mapping.
- [x] Generate an inventory summary in Markdown and JSON.
- [x] Generate individual Markdown/JSON source-trace reports for each resolvable candidate.
- [x] Generate heuristic cluster summaries with pairwise shared-Table evidence.
- [x] Continue when individual source traces are missing or ambiguous; record per-candidate status.
- [ ] Run against the complete Datascrip TXT export and review coverage, duration, source-resolution rate and duplicate/ambiguous exports.
- [ ] Audit candidate clusters with business owners and label validated business-process boundaries.
- [ ] Add explicit UI action, job queue, XMLport and integration entry-point evidence beyond CALL-only traversal.

**Evidence boundary:** inventory generation is implemented as a static analysis pipeline. It is not a runtime execution monitor and does not certify business-process completeness.
