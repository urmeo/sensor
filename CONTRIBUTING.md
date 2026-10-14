# Contributing

Contribute corrections to the code, data documentation, provenance or descriptive analysis. Preserve source observations and explain changes to their interpretation.

## Setup

Use Python 3.11 or later. CI checks Python 3.11 and 3.12. To install the pinned dependencies used by CI:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e . --no-deps
```

For an unpinned development install, use `python -m pip install -e ".[dev]"`. For runtime code only, use `python -m pip install -e .`.

Wheels do not include CSVs. Pass the directory containing the required files to `sensor_data.load(name, base=...)` or the data CLIs' `--data-dir` option. The relative-time export needs all six CSVs. The provenance validator needs the source checkout; use `--root` when running it elsewhere.

## Checks

Run these from the checkout:

```bash
python -m pytest tests/ -q
python -m pytest --nbmake --nbmake-timeout=600 notebooks/explore_data.ipynb
python -m scripts.derive --check
python -m scripts.validate_provenance
ruff check .
ruff format --check .
mypy sensor_data.py scripts
```

Use Python 3.11 for the configured mypy target. Run notebooks from top to bottom and remove stale or incorrect outputs.

## Data commands

`python -m scripts.derive` defaults to a read-only comparison with `sed_fix.csv`. Use `--output PATH` to write a separate historical derivative. The `detect_legacy_runs` API preserves the old calculation, including its quality and gap defects. `detect_fixations` remains a deprecated compatibility name.

The separate `scripts.fixations.detect_events` API requires four settings. The [detector contract](docs/FIXATION_DETECTOR.md) explains its parameters, event boundaries, export command and synthetic tests. Parameters need recording-specific evidence before candidate events can be interpreted as physiological fixations.

To remove calendar timestamp columns from copies of all six resources:

```bash
python -m scripts.shift_time --data-dir data --output-dir outputs/relative
```

The export validates every resource before writing and rejects source overwrites. Relative origins differ by resource; these copies remain sensitive and do not establish synchronized clocks. The shown `outputs/relative` directory is ignored by Git.

Generate all six notebook charts with `python -m scripts.export_figures --output-dir outputs/figures`. To update the versioned previews, use `--output-dir docs/figures`. The exporter leaves the notebook unchanged and records source and figure hashes. See the [pipeline and folder guide](docs/PIPELINE.md). Publishing runs after both Python test jobs and makes no commits.

## Changes

- Use synthetic fixtures for malformed input and command-line tests. Explain any proposed recording correction before changing source data.
- Keep claims descriptive and preserve measured results and limitations. Update the [dictionary](data/DATA_DICTIONARY.md) and [schema](datapackage.json) when contracts change.
- Update the [recording manifest](data/RECORDING_PROVENANCE.json) when adding recordings or acquisition evidence. Keep missing information explicit. Device, calibration and aggregation claims require recording-specific evidence; hardware reviews do not establish channel identity.
- Run the checks above before submitting a pull request. Use short lowercase commit messages beginning with `updated`, such as `updated docs` or `updated pupil validation`. License changes use `update license`.

Code uses MIT. Authored data and documentation use CC BY 4.0 where rights are held. Instrument wording and product media retain separate rights; see [NOTICE](NOTICE.md).
