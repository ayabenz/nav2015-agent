# Handoff: NAV 2015 Stocktake Runtime Testing — PT DATASCRIP Demo

## Goal
Validate the Datascrip stocktake behavior in a running NAV 2015 non-production environment. Execute runtime scenarios ST-001 through ST-008, capture before/after evidence, and distinguish confirmed behavior from unresolved business-policy decisions.

## Current state
- Repository: `ayabenz/nav2015-agent`
- Branch: `datascrip`
- User has prepared the local Python environment, installed dependencies, and reported that the initial local setup and tests are OK.
- User confirms a NAV 2015 demo/non-production server and database are available.
- Test company: `PT DATASCRIP`.
- User confirms the required NAV objects are present and compiled:
  - Table 50063 — Stocktake rules.
  - Codeunit 50081 — Sales Return Order Receive.
  - Codeunit 50082 — Credit Memo / invoice-only route.
  - Codeunit 80 — Sales-Post.
  - Codeunit 5704 — Transfer Shipment.
  - Codeunit 5705 — Transfer Receipt.
- Runtime test plan ST-001–ST-008 and environment readiness checklist are committed in the repository.
- GitHub Issue #4 tracks the runtime environment readiness work.
- No NAV runtime transaction has been executed yet; there are no ST-001–ST-008 pass/fail results.
- No actual Table 50063 records, matching test item/location, control item, or NAV build details have been supplied yet.

## Decisions made (do not re-litigate)
- Use the NAV demo/non-production database and company `PT DATASCRIP`; do not use production.
- Preserve the company-approved Codeunit 50082 invoice-only behavior: it intentionally calls Codeunit 80 without repeating the Codeunit 50081 stocktake check. Do not classify this as a defect or add a check solely for consistency.
- ST-001 expected behavior: Sales Return Order Receive through Codeunit 50081 is blocked by a matching active IN stocktake rule before Return Receipt / Item Ledger posting.
- ST-003 / ST-004 expected behavior: Codeunit 5704 checks OUT and Codeunit 5705 checks IN before transfer posting.
- Loan and Return Loan use the shared transfer posting routes and should inherit the corresponding OUT/IN checks.
- Do not modify NAV objects or remediate source code before runtime validation and relevant policy confirmation.
- The assistant has no direct connection to the user's NAV Server. The user performs NAV UI/runtime actions and provides outputs or screenshots for analysis.

## Open questions
- What records currently exist in Table 50063 in company `PT DATASCRIP`?
- Which active rule has a suitable date window, transaction direction, item scope, and location scope for ST-001?
- Which test Item No. and Location Code match exactly one active rule?
- Which control item is outside the rule scope?
- What exact NAV application/platform build is running?
- Is a restorable backup/restore point available, and are EDI, email, external integrations, and production-facing job queues disabled or redirected to demo?

## Constraints
- Never run tests against production.
- Do not post transactions until the applicable stocktake rule, test item/location, opening balances, and safety controls are recorded.
- Do not send EDI, email, or other external integration traffic to production systems.
- Do not delete or reverse posted entries without an approved test-environment procedure.
- For every test, capture the company, NAV build, user, posting date, rule details, source document, item/quantity/location/Owner, exact NAV error, and relevant before/after ledger and posted-document evidence.
- A Python test or static source analysis is not proof of NAV runtime behavior.
- Keep policy-required scenarios pending until the company confirms expected behavior.
- Communicate in Indonesian.
- Provide PowerShell commands as single-line, paste-ready commands.
- Continue autonomously where the next action is clear; avoid asking the user to repeat information already recorded here.

## Next step
Ask the user to open Table 50063 in NAV Development Environment for company `PT DATASCRIP` and provide the complete current stocktake-rule records (screenshots or exported values). Use those records to select the ST-001 rule, then identify a matching test item/location and an out-of-scope control item before preparing the Sales Return Order test. Do not post yet.

## Context files
1. `reports/datascrip/stocktake/STOCKTAKE_RUNTIME_TEST_PLAN.md` — runtime scenarios ST-001–ST-008, expected behavior, evidence requirements, and policy-required cases.
2. `reports/datascrip/stocktake/STOCKTAKE_RUNTIME_ENVIRONMENT_READINESS.md` — environment prerequisites, safety controls, configuration snapshot, and posting evidence requirements.
3. `reports/datascrip/stocktake/STOCKTAKE_ENTRYPOINT_AUDIT.md` — static audit of stocktake enforcement across posting entry points and accepted exceptions.
4. `ROADMAP_TRACKER.md` — project phases, progress, runtime blockers, and validation status.
