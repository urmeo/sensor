# Contributing

**Facts · Tests · Data · Rights**

Corrections to code, provenance, references and descriptive analysis are welcome.

## Setup

Python 3.11+; CI checks 3.11 and 3.12. From the checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Runtime only: `python -m pip install -e .`. If installing requirements files separately, follow them with `python -m pip install -e . --no-deps`. The installed wheel contains code; use `sensor_data.load(name, base=...)` with an explicit directory containing the six CSVs.

## Verify

```bash
python -m pytest tests/ -q
python -m pytest --nbmake --nbmake-timeout=600 notebooks/explore_data.ipynb
ruff check .
ruff format --check .
mypy sensor_data.py scripts
```

Use Python 3.11 for the configured mypy target. Clear inaccurate notebook outputs, then run top to bottom without errors.

## Commands

```bash
python -m scripts.derive --check --data-dir data
python -m scripts.shift_time --data-dir data --output-dir outputs/relative
```

Derivation defaults to a read-only check; `--output PATH` explicitly creates a derived file. Relative export requires `--output-dir`, validates all six resources first and refuses source overwrite. `--data-dir` means the folder containing the CSVs. New exports stay untracked; the existing README figures are versioned. Relative copies remain sensitive.

## Changes

- Preserve source observations and schema contracts. Use synthetic fixtures for malformed input and CLI tests; explain any proposed data correction before changing recordings.
- Keep notebook claims descriptive. Update the [dictionary](data/DATA_DICTIONARY.md) and [schema](datapackage.json) with contract changes; run all gates before a PR.
- Use a short component title, such as `updated analysis`. Code is MIT; authored data/docs use CC BY 4.0 where rights are held. Instrument wording and product media retain separate rights: [NOTICE](NOTICE.md).
