# NAV Record Snapshot Contract

## Purpose

The snapshot evaluator evaluates the supported subset of a normalized C/AL IF predicate against explicitly supplied Record-variable values. It is an offline evidence evaluator: it does not connect to NAV, query SQL Server, execute C/AL, or prove that a record was loaded by a particular NAV operation.

## JSON input contract

The `--snapshot-json` file is a JSON object keyed by the exact C/AL Record variable name (case-insensitive matching is used). Each value is an object keyed by NAV field name (also matched case-insensitively).

Example:

```json
{
  "SalesHeader": {
    "Document Type": "Order",
    "Status": "Released",
    "Amount": 1250.50,
    "Blocked": false
  }
}
```

Supply native JSON values: strings for Code/Text/Option labels and dates represented as strings; numbers for numeric fields; booleans for Boolean fields. For Option fields, a zero-based integer ordinal is also accepted and mapped through the Table export's OptionString. Do not supply SQL display strings such as "0"/"1" for Boolean or numeric values unless they are actually Text/Code values.

A missing Record, missing field, explicit null, unavailable Table/Field metadata, invalid Option ordinal, unsupported operand, or incompatible comparison types yields an indeterminate result (JSON `null`), not FALSE. Python's bool/int equivalence is explicitly rejected. Numeric int/float pairs are comparable; values from different primitive type families are not coerced implicitly.

## Supported condition subset

- Equality and ordering: `=`, `<>`, `<`, `>`, `<=`, `>=`.
- Boolean composition: `AND`, `OR`, `NOT`, with parsed parentheses/precedence.
- Option member references resolved against the supplied Table OptionString metadata.
- `IN [value, ...]` when all members resolve and have compatible primitive types.
- Boolean field operands when the supplied value is a native JSON boolean.

Unsupported C/AL expressions remain indeterminate. This is not a general C/AL expression interpreter.

## Output semantics

- `result=true/false`: the normalized predicate was deterministically evaluated from supplied values.
- `explanation`: ordered predicate-level trace with each comparison's resolved left/right values, individual result, and parent AND/OR/NOT result.
- For an IF node, `selected_branch` is `THEN`, `ELSE`, or `UNKNOWN`; UNKNOWN is used whenever the condition is indeterminate.
- `branch_effects` lists recognizable source statements in the selected branch (ERROR/MESSAGE/CONFIRM/EXIT/COMMIT, Record writes (including bulk operations), validation/filter/lookup/calculation operations, and CODEUNIT/REPORT/PAGE RUN calls), with source lines and certainty labels. Nested unresolved IF/CASE branches are explicitly marked uncertain.
- `result=null`, `status=indeterminate`: evidence was incomplete or unsupported; inspect `missing_or_unsupported`.
- `provenance=caller_supplied_snapshot` and `runtime_evaluated=false` are always retained. A successful evaluation does not mean NAV executed that branch in production; it means the supplied snapshot satisfies the parsed predicate. The selected branch is a deterministic implication of the supplied snapshot only. Branch effects are source-level statements beneath that branch, not proof of successful execution, committed writes, or completed downstream calls.

## CLI

Use `nav-intel conditions --source-file <object.txt> --procedure <ProcedureName> --table-source <Table.txt> --snapshot-json <snapshot.json> --json`. Repeat `--table-source` for every referenced Table. The CLI currently accepts one Record-variable snapshot per analysis input; it does not fetch data from the NAV database.

## Validation

Focused tests: `tests/test_snapshot_evaluator.py` and `tests/test_condition_expression.py`. Run the complete project test suite on the target branch before treating the evaluator as validated.


## Cross-procedure business-flow inventory

When `nav-intel trace --analyze-conditions` traverses the existing CALL dependency graph, its result also includes `business_flow`. Each reachable procedure entry combines its graph call path, direct table usage, source-resolution status, and recognizable source effects. The effect inventory traverses all IF/ELSE and CASE branches and preserves the branch predicate/arm as `branch_path`; it does not select a branch because no runtime snapshot was supplied to this trace mode.

Each effect includes source text, source lines, a certainty label, and `runtime_executed=false`. The summary's `branch_effect_counts` counts syntactic occurrences across the analyzed reachable procedures; it is not a count of runtime executions or committed database changes. Missing source objects remain visible with their source status and no fabricated effects. The graph still only traverses existing CALL edges, so unresolved dynamic object RUN targets and absent edges remain limitations.
