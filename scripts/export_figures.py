"""Execute the source notebook in memory and export its six descriptive figures."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import sensor_data as sd

ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = "sensor.notebook-png-export/v1"
BACKEND = "module://matplotlib_inline.backend_inline"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FIGURE_NAMES = (
    "01_heart_rate.png",
    "02_pupil_readings.png",
    "03_legacy_run_durations.png",
    "04_interval_variation.png",
    "05_pupil_summaries.png",
    "06_response_times.png",
)


def extract_pngs(notebook: Mapping[str, Any]) -> list[bytes]:
    """Decode exactly six PNG display outputs in notebook cell/output order."""
    figures = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        for output in cell.get("outputs", []):
            encoded = output.get("data", {}).get("image/png")
            if encoded is None:
                continue
            if isinstance(encoded, list) and all(isinstance(part, str) for part in encoded):
                encoded = "".join(encoded)
            if not isinstance(encoded, str):
                raise ValueError("Notebook PNG output must contain base64 text")
            try:
                decoded = base64.b64decode("".join(encoded.split()), validate=True)
            except ValueError as error:
                raise ValueError("Notebook contains invalid base64 PNG output") from error
            if not decoded.startswith(PNG_SIGNATURE):
                raise ValueError("Notebook image/png output has no PNG signature")
            figures.append(decoded)
    if len(figures) != len(FIGURE_NAMES):
        raise ValueError(f"Expected six notebook PNG outputs, found {len(figures)}")
    return figures


def _execute_notebook(source: bytes, root: Path) -> Mapping[str, Any]:
    try:
        import nbformat
        from nbclient import NotebookClient
    except ImportError as error:
        raise ValueError(
            'Notebook dependencies missing; install with python -m pip install -e ".[dev]"'
        ) from error
    notebook = nbformat.reads(source.decode("utf-8"), as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root) + os.pathsep + environment.get("PYTHONPATH", "")
    environment["MPLBACKEND"] = BACKEND
    try:
        return NotebookClient(notebook, timeout=600, kernel_name="python3").execute(
            cwd=str(root), env=environment
        )
    except Exception as error:
        # Execution exceptions can contain cell text and sensitive printed data.
        raise ValueError(
            f"Notebook execution failed ({type(error).__name__}); inspect it in a notebook editor"
        ) from error


def _same_file(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve() or (
            first.exists() and second.exists() and first.samefile(second)
        )
    except (OSError, RuntimeError) as error:
        raise ValueError(f"Cannot resolve figure paths: {error}") from error


def _destinations(output_dir: Path, root: Path, inputs: Mapping[str, Path]) -> list[Path]:
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"Figure output directory is not a directory: {output_dir}")
    paths = [
        sd.validate_output_path(output_dir / name, root / "data")
        for name in (*FIGURE_NAMES, "figures.json")
    ]
    for index, path in enumerate(paths):
        if path.exists() and not path.is_file():
            raise ValueError(f"Figure destination is not a regular file: {path}")
        if any(_same_file(path, source) for source in inputs.values()):
            raise ValueError(f"Figure destination would overwrite a source input: {path}")
        if any(_same_file(path, previous) for previous in paths[:index]):
            raise ValueError("Figure outputs and figures.json must be separate files")
    return paths


def _hashes(inputs: Mapping[str, Path]) -> dict[str, str]:
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()}


def export_figures(output_dir: str | Path, root: str | Path = ROOT) -> dict[str, Any]:
    """Export PNG outputs and hashes; preserve source inputs and omit text outputs."""
    checkout = Path(root).resolve()
    notebook_path = checkout / "notebooks" / "explore_data.ipynb"
    if not notebook_path.is_file():
        raise ValueError(
            f"Source notebook not found at {notebook_path}; use a source checkout "
            "or --root /path/to/checkout"
        )
    inputs = {
        "notebook": notebook_path,
        "analysis": checkout / "sensor_data.py",
        "exporter": Path(__file__).resolve(),
        **{name: checkout / "data" / filename for name, filename in sd.CSV_FILES.items()},
    }
    for path in inputs.values():
        if not path.is_file():
            raise ValueError(f"Source input not found at {path}; use a complete source checkout")
    directory = Path(output_dir)
    destinations = _destinations(directory, checkout, inputs)
    source = notebook_path.read_bytes()
    before = _hashes(inputs)
    if hashlib.sha256(source).hexdigest() != before["notebook"]:
        raise ValueError("Source notebook changed while reading; no figures were written")
    executed = _execute_notebook(source, checkout)
    figures = extract_pngs(executed)
    if _hashes(inputs) != before:
        raise ValueError("Source inputs changed during notebook execution; no figures were written")
    _destinations(directory, checkout, inputs)
    provenance = {
        "schema": "sensor.figure-provenance/v1",
        "algorithm": ALGORITHM,
        "implementation": {"path": "scripts/export_figures.py", "sha256": before["exporter"]},
        "notebook": {"path": "notebooks/explore_data.ipynb", "sha256": before["notebook"]},
        "analysis": {"path": "sensor_data.py", "sha256": before["analysis"]},
        "source_csvs": {
            name: {"path": f"data/{filename}", "sha256": before[name]}
            for name, filename in sd.CSV_FILES.items()
        },
        "execution": {"kernel": "python3", "matplotlib_backend": BACKEND},
        "inputs_unchanged": True,
        "figures": [
            {"path": name, "sha256": hashlib.sha256(figure).hexdigest()}
            for name, figure in zip(FIGURE_NAMES, figures, strict=True)
        ],
        "scope": "Descriptive notebook figures from one participant; PNG outputs only.",
        "limits": [
            "Device mappings, calibration, coordinate units and clock alignment are unverified.",
            "Legacy low-movement runs retain quality/gap defects and are not validated fixations.",
            "Repeated interval samples are not a verified beat sequence or measured cardiac HRV.",
            "Supplied eye-summary aggregation, baseline intervals and blink rules are unavailable.",
            "Response times do not establish psychological states or diagnostic results.",
        ],
    }
    metadata = (json.dumps(provenance, indent=2, allow_nan=False) + "\n").encode("utf-8")
    directory.mkdir(parents=True, exist_ok=True)
    for destination, figure in zip(destinations[:-1], figures, strict=True):
        destination.write_bytes(figure)
    destinations[-1].write_bytes(metadata)
    return provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for six PNGs")
    parser.add_argument("--root", type=Path, default=ROOT, help="Source checkout directory")
    args = parser.parse_args(argv)
    try:
        export_figures(args.output_dir, args.root)
    except (OSError, ValueError, KeyError) as error:
        print(f"export_figures: {error}", file=sys.stderr)
        return 1
    print(f"wrote six descriptive figures and figures.json to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
