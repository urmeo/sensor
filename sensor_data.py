"""Load source CSVs and apply the recorded quality flags."""

from __future__ import annotations

from datetime import date, timedelta
from numbers import Real
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR: Path = Path(__file__).resolve().parent / "data"

CSV_FILES: dict[str, str] = {
    "hr": "hr.csv",
    "ibi": "ibi.csv",
    "sed": "sed.csv",
    "sed_fix": "sed_fix.csv",
    "eye_metrics": "eye_metrics.csv",
    "psych": "Psychometric_Test_Results.csv",
}


def data_dir(base: str | Path | None = None) -> Path:
    """Use a supplied CSV directory or the checkout's data directory."""
    return Path(base) if base is not None else DATA_DIR


def load(name: str, base: str | Path | None = None) -> pd.DataFrame:
    """Read a named dataset without changing its rows or quality flags."""
    if name not in CSV_FILES:
        raise KeyError(f"unknown dataset {name!r}; valid names: {sorted(CSV_FILES)}")
    path = data_dir(base) / CSV_FILES[name]
    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset {name!r} not found at {path}. CSVs are not bundled in installed wheels. "
            "Use a source checkout or load(..., base=CSV_DIRECTORY); "
            "module CLIs accept --data-dir CSV_DIRECTORY."
        )
    return pd.read_csv(path)


def load_all(base: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """Read each CSV listed in ``CSV_FILES``."""
    return {name: load(name, base) for name in CSV_FILES}


def valid_hr(hr: pd.DataFrame) -> pd.DataFrame:
    """Return rows whose recorded confidence flag equals one."""
    return hr[hr["confidence"] == 1.0].copy()


def valid_pupil(eye: pd.DataFrame, min_quality: float = 0.5) -> pd.DataFrame:
    """Keep finite positive pupil values with quality in (min_quality, 1].

    Boolean, date, datetime and timedelta values raise ValueError before numeric
    conversion. Numeric strings are accepted; missing and unparseable values are
    excluded. The returned copy preserves the retained rows' values and index.
    """
    message = "min_quality must be a finite numeric scalar in [0, 1]"
    if isinstance(min_quality, (bool, np.bool_, np.timedelta64)) or not isinstance(
        min_quality, Real
    ):
        raise ValueError(message)
    try:
        cutoff = float(min_quality)
    except (ValueError, OverflowError) as error:
        raise ValueError(message) from error
    if not np.isfinite(cutoff) or not 0 <= cutoff <= 1:
        raise ValueError(message)
    measurements = [eye[column] for column in ("pupil", "pupilQ")]
    for values in measurements:
        if (
            pd.api.types.is_bool_dtype(values)
            or pd.api.types.is_datetime64_any_dtype(values)
            or pd.api.types.is_timedelta64_dtype(values)
            or any(
                isinstance(value, (bool, np.bool_, date, timedelta, np.datetime64, np.timedelta64))
                for value in values
            )
        ):
            raise ValueError(
                "pupil and pupilQ must contain real measurements; "
                "boolean, datetime and timedelta values are not measurements"
            )
    numeric = [pd.to_numeric(values, errors="coerce") for values in measurements]
    if any(pd.api.types.is_complex_dtype(values) for values in numeric):
        raise ValueError("pupil and pupilQ must contain real measurements")
    pupil, quality = [values.to_numpy(dtype=float, na_value=np.nan) for values in numeric]
    keep = (
        np.isfinite(pupil)
        & np.isfinite(quality)
        & (pupil > 0)
        & (quality > cutoff)
        & (quality <= 1)
    )
    return eye.loc[keep].copy()


def fixation_durations(sed_fix: pd.DataFrame) -> pd.Series:
    """Positive spans of legacy low-movement runs, excluding zero-span runs."""
    durations = sed_fix[sed_fix["fixation"]].groupby("fixation_id")["duration"].max()
    return durations[durations > 0]


def validate_output_path(path: str | Path, base: str | Path | None = None) -> Path:
    """Reject destinations that alias source CSVs or recording provenance."""
    destination = Path(path)
    filenames = [*CSV_FILES.values(), "RECORDING_PROVENANCE.json"]
    sources = [data_dir(base) / filename for filename in filenames]
    sources.extend(DATA_DIR / filename for filename in filenames if (DATA_DIR / filename).exists())
    try:
        resolved = destination.resolve()
        for source in sources:
            if resolved == source.resolve() or (
                destination.exists() and source.exists() and destination.samefile(source)
            ):
                kind = "recording provenance" if source.suffix == ".json" else "source CSV"
                raise ValueError(f"Output would overwrite {kind}: {source}")
    except (OSError, RuntimeError) as error:
        raise ValueError(f"Cannot resolve output or source CSV path: {error}") from error
    return destination
