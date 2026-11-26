# NAV 2015 Agent — Roadmap & Validation Tracker

**Branch:** `datascrip`  
**Last updated:** 2026-11-26  
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
| Conditional Logic Intelligence | PLANNED | Explain IF/ELSE/ELSEIF/CASE branches, field/value predicates, nested paths and data-flow; static analysis first, runtime evaluation later |
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

- [ ] Inventory and parse C/AL control-flow constructs: IF / THEN / ELSE / ELSEIF and CASE / OF / ELSE; preserve nested block structure and source line ranges.
- [ ] Normalize condition expressions: operands, comparison operators, boolean operators, parentheses, constants and enum/option members.
- [ ] Resolve Record variables and field references to NAV Table / Field identities, including qualified Option values such as Record.Status::Released.
- [ ] Resolve field metadata and OptionString values from parsed table definitions; distinguish Option fields, ordinary text/code/numeric/date fields and unresolved expressions.
- [ ] Build branch paths with parent/child relationships and explicit TRUE / FALSE / CASE-match / CASE-default outcomes.
- [ ] Track local variable assignments and record-field values sufficiently to explain predicates whose operands are assigned earlier in the procedure.
- [ ] Trace relevant values across direct procedure calls where parameter and Record-variable flow can be resolved safely.
- [ ] Add nav-intel conditions and object/procedure integration; return source file, line range, resolution confidence and unresolved operands.
- [ ] Add unit fixtures for nested IF/ELSE, ELSEIF, CASE, Option values, field comparisons, variable assignments and unresolved/dynamic expressions.
- [ ] Document static-analysis limits and avoid presenting inferred branch reachability as runtime fact.
- [ ] Add optional runtime evaluation only as a separate later capability, requiring an explicitly supplied read-only record snapshot / runtime evidence.

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

These are separate historical runs with different collection scopes. They must not be added together or represented as the current full-suite status. The current canonical full-suite result is **NOT YET RE-RUN / NOT VERIFIED**.

| Validation | Result | Classification | Notes |
|---|---|---|---|
| Earlier repository test snapshot | 44 passed, 4 failed | Historical automated test run | README attributes failures to absent `data/incoming/*.txt` fixtures |
| Later focused test run | 27 passed | Historical automated test run | Output in project conversation showed all 27 collected tests passing |
| Current full suite at tracker update | Not run / not verified | Pending | Run against current branch HEAD and record exact command, commit SHA and output |
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
