# Abaqus solver diagnostics

Turn instance-qualified excessive-element-distortion messages into an auditable CSV/JSON report. An optional Abaqus/CAE adapter can create a diagnostic assembly set after validating all instance and element identities.

Adapted and refactored from a research troubleshooting script. The public version removes project-specific model names, paths and element identifiers. All examples are synthetic. It is a focused distortion-message reporter, not a general solver-failure diagnosis or model-validity checker.

## Quick start (no Abaqus required)

Requires Python 3.9 or newer; standard library only. From this directory:

```sh
python diagnostics.py examples/distortion.msg --output reports/demo
python -m unittest discover -s tests -v
```

The synthetic example produces:

```text
Unique elements: 3; occurrences: 4; unparsed distortion lines: 1
```

Output files:

| File | Contents |
| --- | --- |
| `report.json` | Instance-qualified findings, occurrence counts, original source lines, unparsed distortion lines, source filename and SHA-256 |
| `elements.csv` | One row per unique instance/element identity |
| `unparsed.csv` | Distortion-related lines that did not match the supported element format |

The output directory must be new. Reusing an existing directory is rejected rather than overwriting a report. Source files are read only. If writing fails, a partial output directory may remain; inspect it and choose a fresh directory for the next run.

## Supported messages

```text
ELEMENT BRACKET-1.42 IS DISTORTING EXCESSIVELY
```

- Case-insensitive keywords and instance matching; instance names are normalised to uppercase in the report.
- Whitespace or line breaks between tokens.
- Instance names beginning with a letter/underscore and containing letters, digits, underscores, dots, colons or hyphens.
- Positive element labels without leading zeroes.
- Repeated occurrences retained with 1-based starting line numbers.
- Identical element labels in different instances remain separate.

Bare element labels, quoted instance names, other diagnostic formats and message summaries are not converted into element findings. Same-line text containing both distortion and excess keywords is retained for review when unmatched. This heuristic is not a complete catalogue of unrecognised warnings; unsupported formats and differently wrapped text may be missed. Step, increment and solver-completion state are not inferred.

**No findings does not mean the analysis succeeded.** The second synthetic example contains an unrelated error and deliberately produces no supported distortion findings.

## Automation and text encoding

```sh
python diagnostics.py example.msg --output reports/run-01 --fail-on-findings
python diagnostics.py example.msg --output reports/run-02 --encoding cp1252
```

Exit codes: `0` report written; `1` I/O, decoding or output-path error; `2` report written with findings when `--fail-on-findings` is selected. Without that flag, findings do not change exit code 0. UTF-8 with an optional BOM is the default; decoding errors are not silently replaced. The parser reads the full file into memory.

Reports retain diagnostic text and the source basename. Review reports before sharing them outside your project.

## Optional Abaqus/CAE integration

Run the following in an installed Abaqus/CAE release with Python 3 support, with this repository on its Python path:

```python
import json
from abaqus import mdb
from cae_adapter import create_diagnostic_set

with open('reports/demo/report.json', encoding='utf-8') as stream:
    report = json.load(stream)

# Use the actual model corresponding to the report, not an arbitrary open model.
assembly = mdb.models['YourModel'].rootAssembly
selection = create_diagnostic_set(assembly, report)  # preview only
print(selection)

# After inspecting the preview, explicitly create one assembly set:
# create_diagnostic_set(assembly, report, name='CHECK_DISTORTION_01', apply=True)
```

The adapter validates report schema, unique identities, instance lookup and element existence before requesting a single assembly-set creation. It rejects existing set names. It never deletes elements, submits a solver job or saves a CAE database. Work on the matching model and inspect the result before saving: matching labels alone cannot prove that a report belongs to the open model. Unparsed lines are not converted to a set.

The `SetFromElementLabels` assembly API is documented by [Dassault Systèmes](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-setpyc.htm). Abaqus API errors may still occur; the adapter has not been executed in Abaqus during this project build.

## Validation

Standalone tests cover multi-instance identity, repeated and wrapped messages, unsupported formats, report round-tripping, overwrite rejection, CLI exits, decoding errors, preview behaviour and adapter validation using mock assembly objects. These tests do not run or validate Abaqus. The synthetic messages are intentionally authored fixtures, not captured solver output.

Locally checked with Python 3.14. A GitHub Actions workflow is included for Python 3.9, 3.12 and 3.14; its status should be checked in the repository's Actions tab.
