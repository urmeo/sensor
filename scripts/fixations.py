"""Find candidate gaze events using quality, gap, displacement and duration rules.

Synthetic tests validate the boundary contract, not physiological fixation detection.
Distances are Euclidean displacements in the recorded vector units, not angles.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from numbers import Integral, Real
from pathlib import Path

import numpy as np
import pandas as pd

import sensor_data as sd

ALGORITHM = "sensor.gaze-step-events/v1"
VECTOR_COLUMNS = ["gazeDir.x", "gazeDir.y", "gazeDir.z"]
REQUIRED_COLUMNS = ["reltime", "gazeQ", *VECTOR_COLUMNS]
EVENT_COLUMNS = [
    "event_id",
    "start_row",
    "end_row",
    "start_time",
    "end_time",
    "duration",
    "sample_count",
]


def _parameter(value: float, name: str, *, positive: bool = False) -> float:
    condition = "positive" if positive else "nonnegative"
    message = f"{name} must be a finite {condition} real numeric scalar"
    if isinstance(value, (bool, np.bool_, np.timedelta64)) or not isinstance(value, Real):
        raise ValueError(message)
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(message) from error
    if not np.isfinite(result) or (result <= 0 if positive else result < 0):
        raise ValueError(message)
    return result


def _measurements(series: pd.Series) -> np.ndarray:
    """Convert real measurements to floats; invalid cells become run boundaries."""
    if (
        pd.api.types.is_numeric_dtype(series)
        and not pd.api.types.is_bool_dtype(series)
        and not pd.api.types.is_complex_dtype(series)
    ):
        return series.to_numpy(dtype=float, na_value=np.nan)

    def real_or_nan(value: object) -> float:
        if isinstance(value, (bool, np.bool_, np.timedelta64)) or not isinstance(value, Real):
            return np.nan
        try:
            return float(value)
        except (ValueError, OverflowError):
            return np.nan

    return np.fromiter((real_or_nan(value) for value in series), dtype=float, count=len(series))


def _valid_channel(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (bool, np.bool_, np.timedelta64)) or not isinstance(value, Real):
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (ValueError, OverflowError):
        return False


def _relative_times(series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Return times and a finite, nonnegative mask without rounding integer times."""
    numeric = _measurements(series)
    if pd.api.types.is_integer_dtype(series) and not pd.api.types.is_bool_dtype(series):
        # Object arrays box uint64 as Python integers, avoiding overflow/rounding
        # in differences of large timestamps and retaining exact CSV endpoints.
        return series.to_numpy(dtype=object), np.isfinite(numeric) & (numeric >= 0)
    for row, value in enumerate(series):
        if (
            np.isfinite(numeric[row])
            and isinstance(value, Integral)
            and int(value) != float(numeric[row])
        ):
            numeric[row] = np.nan
    return numeric, np.isfinite(numeric) & (numeric >= 0)


def detect_events(
    recording: pd.DataFrame,
    *,
    displacement_threshold: float,
    min_quality: float,
    max_gap_seconds: float,
    min_duration_seconds: float,
) -> pd.DataFrame:
    """Return candidate events without altering or sorting the input rows.

    Each event is a maximal run of valid adjacent samples whose Euclidean step
    is <= displacement_threshold and whose time increment is in (0, max_gap_seconds].
    Valid samples have finite, nonzero gaze vectors, finite nonnegative reltime,
    and finite gazeQ in [min_quality, 1]. Invalid samples break runs. When iSensor
    is present, missing/invalid identifiers and changes of identifier also break
    runs; otherwise the input is treated as one unidentified stream.

    Events include both endpoints and require duration >= min_duration_seconds.
    start_row/end_row are inclusive zero-based positions, independent of the
    DataFrame index. No calibration, angular conversion or biological validation
    is implied. Non-unit vectors retain their recorded scale.
    """
    cutoff = _parameter(displacement_threshold, "displacement_threshold")
    quality_cutoff = _parameter(min_quality, "min_quality")
    if quality_cutoff > 1:
        raise ValueError("min_quality must be in [0, 1]")
    gap = _parameter(max_gap_seconds, "max_gap_seconds", positive=True)
    minimum = _parameter(min_duration_seconds, "min_duration_seconds", positive=True)
    if not recording.columns.is_unique:
        raise ValueError("Input columns must be unique")
    missing = set(REQUIRED_COLUMNS) - set(recording.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    times, valid_times = _relative_times(recording["reltime"])
    quality = _measurements(recording["gazeQ"])
    vectors = np.column_stack([_measurements(recording[column]) for column in VECTOR_COLUMNS])
    valid = (
        valid_times
        & np.isfinite(quality)
        & (quality >= quality_cutoff)
        & (quality <= 1)
        & np.isfinite(vectors).all(axis=1)
        & np.any(vectors != 0, axis=1)
    )
    channels = None
    if "iSensor" in recording.columns:
        channels = recording["iSensor"].to_numpy(dtype=object)
        valid &= np.fromiter(map(_valid_channel, channels), dtype=bool, count=len(recording))

    events: list[dict[str, object]] = []

    def finish(start: int | None, end: int) -> None:
        if start is None or start == end:
            return
        duration = times[end] - times[start]
        if not np.isfinite(float(duration)) or duration < minimum:
            return
        event: dict[str, object] = {
            "event_id": len(events) + 1,
            "start_row": start,
            "end_row": end,
            "start_time": times[start],
            "end_time": times[end],
            "duration": duration,
            "sample_count": end - start + 1,
        }
        if channels is not None:
            event["iSensor"] = channels[start]
        events.append(event)

    start = None
    for row in range(len(recording)):
        if not valid[row]:
            finish(start, row - 1)
            start = None
            continue
        if start is None:
            start = row
            continue
        with np.errstate(over="ignore", invalid="ignore"):
            interval = times[row] - times[row - 1]
            distance = np.hypot.reduce(vectors[row] - vectors[row - 1])
        continuous = (
            0 < interval <= gap
            and np.isfinite(distance)
            and distance <= cutoff
            and (channels is None or channels[row] == channels[row - 1])
        )
        if not continuous:
            finish(start, row - 1)
            start = row
    finish(start, len(recording) - 1)

    columns = [*EVENT_COLUMNS, *(["iSensor"] if channels is not None else [])]
    result = pd.DataFrame(events, columns=columns)
    for column in ("event_id", "start_row", "end_row", "sample_count"):
        result[column] = result[column].astype("int64")
    if result.empty:
        for column in ("start_time", "end_time", "duration"):
            result[column] = result[column].astype(float)
    return result


def _same_output(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve() or (
            first.exists() and second.exists() and first.samefile(second)
        )
    except (OSError, RuntimeError) as error:
        raise ValueError(f"Cannot resolve event output paths: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write candidate gaze events and a JSON file with parameters and source hashes. "
            "Choose thresholds for your study; testing covers synthetic boundaries only."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--data-dir", type=Path, help="Directory containing sed.csv")
    parser.add_argument(
        "--output", required=True, type=Path, help="Write candidate events to this CSV"
    )
    parser.add_argument(
        "--displacement-threshold",
        required=True,
        type=float,
        help="Largest adjacent gaze-vector displacement, in recorded vector units (>= 0)",
    )
    parser.add_argument(
        "--min-quality", required=True, type=float, help="Lowest accepted gazeQ, inclusive (0 to 1)"
    )
    parser.add_argument(
        "--max-gap-seconds",
        required=True,
        type=float,
        help="Largest time gap between adjacent samples, in seconds (> 0)",
    )
    parser.add_argument(
        "--min-duration-seconds",
        required=True,
        type=float,
        help="Shortest candidate event duration, in seconds (> 0)",
    )
    args = parser.parse_args(argv)
    try:
        destination = sd.validate_output_path(args.output, args.data_dir)
        sidecar = sd.validate_output_path(Path(f"{destination}.json"), args.data_dir)
        if _same_output(destination, sidecar):
            raise ValueError("Event CSV and provenance sidecar must be separate files")
        for path in (destination, sidecar):
            if path.exists() and not path.is_file():
                raise ValueError(f"Output destination is not a regular file: {path}")
        source = sd.data_dir(args.data_dir) / sd.CSV_FILES["sed"]
        if not source.is_file():
            raise ValueError(f"Source sed.csv not found at {source}; use --data-dir CSV_DIRECTORY")
        source_bytes = source.read_bytes()
        header_stream = io.StringIO(source_bytes.decode("utf-8-sig"), newline="")
        # Match pandas' default skip_blank_lines behavior before checking the
        # actual header. Quoted empty fields and comma-only lines are headers.
        while True:
            position = header_stream.tell()
            line = header_stream.readline()
            if not line or line.strip():
                header_stream.seek(position)
                break
        header = next(csv.reader(header_stream), [])
        if len(header) != len(set(header)):
            raise ValueError("Input CSV columns must be unique")
        recording = pd.read_csv(io.BytesIO(source_bytes))
        parameters = {
            "displacement_threshold": args.displacement_threshold,
            "min_quality": args.min_quality,
            "max_gap_seconds": args.max_gap_seconds,
            "min_duration_seconds": args.min_duration_seconds,
        }
        events = detect_events(recording, **parameters)
        csv_bytes = events.to_csv(index=False).encode("utf-8")
        manifest = sd.data_dir(args.data_dir) / "RECORDING_PROVENANCE.json"
        recording_provenance = None
        if manifest.is_file():
            recording_provenance = {
                "path": str(manifest.resolve()),
                "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            }
        provenance = {
            "schema": "sensor.gaze-event-provenance/v1",
            "algorithm": ALGORITHM,
            "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source": {
                "path": str(source.resolve()),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "sample_count": len(recording),
            },
            "parameters": parameters,
            "distance_unit": "recorded_vector_units; no normalization or angular conversion",
            "time_unit": "seconds in recorded reltime",
            "channel_column": "iSensor" if "iSensor" in recording.columns else None,
            "recording_provenance": recording_provenance,
            "device_mapping": "unverified; consult recording provenance for available evidence",
            "calibration": "unverified; no calibration inferred by this detector",
            "event_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "event_count": len(events),
            "validation": {
                "scope": "synthetic boundary and CLI contract tests in tests/test_fixations.py",
                "empirical_validation": "not established",
                "limits": [
                    "Events are candidates; recorded vector and gazeQ semantics are unverified.",
                    "Thresholds have no established device or physiological calibration.",
                    "Pairwise steps can admit gradual drift; this is not a dispersion detector.",
                    "No inference of hardware, calibration, aggregation or participant identity.",
                ],
            },
        }
        json_bytes = (json.dumps(provenance, indent=2, allow_nan=False) + "\n").encode("utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(csv_bytes)
        sidecar.write_bytes(json_bytes)
        print(f"wrote {destination} ({len(events)} candidate events) and {sidecar}")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"fixations: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
