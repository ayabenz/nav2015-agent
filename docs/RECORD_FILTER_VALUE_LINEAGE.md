# NAV Record Filter Value Lineage

## Purpose

The experimental `nav_ai.filter_value_resolution` module links a C/AL Record filter argument to the most recent statically visible assignment on a compatible source path. For example:

```pascal
TransactionType := 'IN';
StocktakeRule.SETRANGE("Jenis Transaksi", TransactionType);
IF StocktakeRule.FINDFIRST THEN
  ERROR('Blocked');
```

The analysis can explain that `TransactionType` was assigned the symbolic literal `'IN'` before the filter was applied. It retains filter field metadata and the lookup's path-specific filter set.

## Python API

```python
from nav_ai.control_flow import analyze_control_flow
from nav_ai.filter_value_resolution import analyze_record_filter_value_flow
from nav_ai.semantic_conditions import load_table_sources, parse_record_variables

variables = parse_record_variables("StocktakeRule : Record 50063;")
tables = load_table_sources(["Table50063.txt"])
parsed = analyze_control_flow(source_code, "Codeunit", 50107, "Stocktake Test", "CheckStocktake", "Codeunit50107.txt")
analysis = analyze_record_filter_value_flow(parsed["nodes"], variables, tables, "Codeunit50107.txt")
```

In `nav-intel conditions` JSON output, inspect `assignment_flow_analysis`, `record_filter_analysis.events`, and `record_filter_analysis.lookups`. The traced-procedure output from `nav-intel trace --analyze-conditions` now attaches the same value lineage to each procedure's `condition_analysis`. Filter arguments include `argument_value_resolution` with the symbolic assignment chain.

## Semantics and limitations

- Static source analysis only; this is not NAV execution.
- A resolved literal proves source assignment lineage, not that a database row exists.
- Assignments must precede the filter operation and have a compatible path. Built-in Record API calls such as `SETRANGE`, `SETFILTER`, `RESET`, and `FINDFIRST` do not invalidate unrelated scalar-local assignments; unknown/custom calls remain conservative invalidators.
- Simple identifier aliases and literals are supported; other expressions remain symbolic or partially resolved.
- Procedure side effects, implicit database changes, triggers, WITH scope, dynamic RecordRef/FieldRef, type coercion and SETFILTER placeholder formatting are not evaluated.
- Runtime row existence requires a supplied data snapshot or NAV runtime evidence.

## Focused tests

- `tests/test_record_filter_paths.py`
- `tests/test_filter_value_resolution.py`
- `tests/test_filter_value_flow_integration.py`

Run the test suite in the project virtual environment before treating this feature as validated. This feature has not been runtime-tested against NAV.

## Option members and SETFILTER placeholders

Filter argument enrichment also checks a direct Option member expression against the
OptionString values of the filtered Table field. A known member is marked
`resolved_option`; a member absent from the metadata is marked `unverified_option`.
Neither status means that a record contains that value.

For `SETFILTER`, format placeholders such as `%1` are linked to the corresponding
argument (for example, `SETFILTER(Status, '=%1', TargetStatus)` links `%1` to
`TargetStatus`). The argument's assignment lineage is attached when statically
available. This does not execute NAV filter syntax, expand date formulas, interpret
wildcards/ranges, or perform database matching.