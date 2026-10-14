"""Reproduce legacy low-movement runs from consecutive gaze-vector displacement.

The 0.01 cutoff is unvalidated and has no quality, gap or minimum-duration rule.
Run spans use the last reltime minus the first. CSV checks use an absolute
tolerance of 1e-9 for derived floats.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from numbers import Real
from pathlib import Path

import numpy as np
import pandas as pd

import sensor_data as sd

THRESHOLD: float = 0.01
DERIVED_COLUMNS: list[str] = ["gaze_diff", "fixation", "fixation_id", "duration"]
REQUIRED_COLUMNS: list[str] = ["gazeDir.x", "gazeDir.y", "gazeDir.z", "reltime"]


def detect_legacy_runs(sed: pd.DataFrame, threshold: float = THRESHOLD) -> pd.DataFrame:
    """Reproduce historical flags, including their quality and gap limitations.

    This compatibility calculation does not detect validated fixation events.
    Use :func:`scripts.fixations.detect_events` for explicitly configured,
    quality- and gap-aware candidate events.
    """
    message = "threshold must be a finite nonnegative numeric scalar"
    if isinstance(threshold, (bool, np.bool_, np.timedelta64)) or not isinstance(threshold, Real):
        raise ValueError(message)
    try:
        cutoff = float(threshold)
    except (ValueError, OverflowError) as error:
        raise ValueError(message) from error
    if not np.isfinite(cutoff) or cutoff < 0:
        raise ValueError(message)
    missing = set(REQUIRED_COLUMNS) - set(sed.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if not sed.columns.is_unique:
        raise ValueError("Input columns must be unique")
    if sed.empty:
        empty = sed.copy()
        for column, dtype in zip(DERIVED_COLUMNS, (float, bool, np.int64, float), strict=True):
            empty[column] = pd.Series(index=sed.index, dtype=dtype)
        return empty
    for column in REQUIRED_COLUMNS:
        if (
            not pd.api.types.is_numeric_dtype(sed[column])
            or pd.api.types.is_bool_dtype(sed[column])
            or pd.api.types.is_complex_dtype(sed[column])
        ):
            raise ValueError(f"{column} must contain finite real numeric values")
        if sed[column].isna().any() or not np.isfinite(sed[column]).all():
            raise ValueError(f"{column} must contain finite numeric values")
    times = sed["reltime"]
    if (times < 0).any() or not times.is_monotonic_increasing:
        raise ValueError("reltime must be nonnegative and nondecreasing")

    derived = sed.copy()
    vectors = sed[REQUIRED_COLUMNS[:3]].to_numpy(dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        step = np.sqrt(((vectors[1:] - vectors[:-1]) ** 2).sum(axis=1))
    if not np.isfinite(step).all():
        raise ValueError("Gaze displacement exceeds the finite numeric range")
    derived["gaze_diff"] = np.concatenate([[np.nan], step])
    derived["fixation"] = derived["gaze_diff"] < cutoff
    transition = derived["fixation"].ne(derived["fixation"].shift()).to_numpy(copy=True)
    transition[0] = False
    derived["fixation_id"] = np.cumsum(transition) + 1
    reltime = derived.groupby("fixation_id")["reltime"]
    span = reltime.transform("last") - reltime.transform("first")
    derived["duration"] = span.where(derived["fixation"])
    return derived


def detect_fixations(sed: pd.DataFrame, threshold: float = THRESHOLD) -> pd.DataFrame:
    """Deprecated historical API; use ``detect_legacy_runs`` for reproduction."""
    warnings.warn(
        "scripts.derive.detect_fixations reproduces legacy low-movement runs; "
        "use detect_legacy_runs for reproduction or scripts.fixations.detect_events "
        "for explicitly configured candidate events",
        DeprecationWarning,
        stacklevel=2,
    )
    return detect_legacy_runs(sed, threshold)


def check(base: str | Path | None = None) -> bool:
    """Compare source columns exactly and derived floats within atol=1e-9."""
    derived = detect_legacy_runs(sd.load("sed", base))
    committed = sd.load("sed_fix", base)
    if len(derived) != len(committed) or list(derived.columns) != list(committed.columns):
        return False
    if derived.empty:
        return True
    for column in committed.columns:
        actual, expected = derived[column], committed[column]
        if column in ("gaze_diff", "duration"):
            try:
                matches = np.allclose(
                    actual.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-9, equal_nan=True
                )
            except (TypeError, ValueError):
                return False
        else:
            matches = actual.equals(expected)
        if not matches:
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare legacy gaze runs with sed_fix.csv or write them to a separate CSV.",
        allow_abbrev=False,
    )
    parser.add_argument("--data-dir", type=Path, help="Directory containing the source CSVs")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check", action="store_true", help="Compare with sed_fix.csv (the default)"
    )
    modes.add_argument("--output", type=Path, help="Write legacy derived rows to this CSV path")
    args = parser.parse_args(argv)
    try:
        if args.output is None:
            matches = check(args.data_dir)
            print(f"matches sed_fix.csv (atol=1e-9): {matches}")
            return 0 if matches else 1
        destination = sd.validate_output_path(args.output, args.data_dir)
        out = detect_legacy_runs(sd.load("sed", args.data_dir))
        destination.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(destination, index=False)
        print(f"wrote {destination} ({len(out)} rows)")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"derive: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
