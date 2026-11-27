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
| Deterministic Code Intelligence query layer | IMPLEMENTED — first vertical slice | `nav-intel` queries existing symbol/graph SQLite databases; object/procedure/callers/callees/impact/table usage; tests added, execution pending |
| Conditional Logic Intelligence | IMPLEMENTED — static analysis foundation | IF/ELSE/CASE parsing, metadata-backed predicates, filter paths, explicit snapshots, local assignment provenance and first direct-call argument binding; CI and broader grammar validation remain pending |
| AI-assisted NAV reasoning / agent workflows | PLANNED | Build on deterministic query layer, conditional logic, parser, symbol index, semantic diff and dependency graph; keep source evidence traceable |

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
- [ ] Propagate values through direct calls, including VAR mutation and return values, only when source evidence and call context are sufficient.
- [x] Add initial nav-intel conditions command with explicit source-file and optional object/procedure selection; return branch tree, raw predicates and source spans.
- [ ] Resolve source files automatically from the symbol index and integrate conditions into object/procedure queries.
- [x] Add unit fixtures for nested IF/ELSE, CASE arms/default, comment/string masking and source line spans.
- [x] Add fixtures for Option values, qualified field comparisons and unresolved metadata.
- [x] Add fixtures for SETRANGE clearing, SETFILTER placeholders, RESET invalidation, FINDFIRST lookup annotation and path isolation across IF / ELSE / CASE.
- [x] Add initial fixtures for literal and Record-field assignments, reassignment, IF/ELSE divergence and unknown-call invalidation. ELSEIF and broader unresolved/dynamic expression coverage remain open.
- [x] Trace simple intra-procedural assignment provenance transitively (local variable → Record field → IF predicate), preserving source locations and unresolved/cycle markers. Regression tests added; CI validation pending.
- [x] Add `--call-source` to `nav-intel conditions` for direct call-site binding evidence; repeated caller exports are supported. Regression fixtures cover typed `Rec`, Boolean literals, comments and receiver type mismatch; CI validation pending.
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
| Previous full suite — 2026-11-27 | 73 passed in 0.74s | PASS — GitHub Actions | Commit `abdc19354b6b984e83e96fc60b11b09cc981adf4`; [run #117](https://github.com/ayabenz/nav2015-agent/actions/runs/45924798203) |\n| Previous full suite — 2026-11-27 | 77 passed in 0.75s | PASS — GitHub Actions | Commit `023426daf4c2c89f458ca1b1854feced9975ba28`; [run #132](https://github.com/ayabenz/nav2015-agent/actions/runs/45926585814) |\n| Current full suite — 2026-11-27 | 80 passed in 0.45s | PASS — GitHub Actions | `python -m pytest -q`; commit `1ddf702a61167dab607700ba6b131087ee6cf6e7`; [run #142](https://github.com/ayabenz/nav2015-agent/actions/runs/45926903904) |
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
