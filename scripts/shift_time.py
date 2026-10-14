"""Write CSV copies with elapsed seconds in place of calendar timestamps.

Sensors retain recording-relative reltime; eye summaries use each Test's earliest
start; questionnaire rows use their earliest start. These origins differ and do
not establish synchronization or anonymity. Timestamps without a timezone remain
unspecified.
"""

from __future__ import annotations

import argparse
import sys
from numbers import Real
from pathlib import Path

import numpy as np
import pandas as pd

import sensor_data as sd

SENSOR_FILES: set[str] = {"hr", "ibi", "sed", "sed_fix"}


def parse_timestamps(values: pd.Series, column: str) -> pd.Series:
    """Parse non-null timestamps with one consistent zone or no zone."""
    if values.isna().any():
        raise ValueError(f"{column} must contain non-null timestamps")
    if any(isinstance(value, (Real, np.bool_)) for value in values):
        raise ValueError(f"{column} must contain calendar timestamps, not numbers")
    try:
        parsed = [pd.Timestamp(value) for value in values]
        zones = {str(value.tzinfo) if value.tzinfo is not None else None for value in parsed}
        if len(zones) > 1:
            raise ValueError("mixed timezone values")
        result = pd.Series(pd.DatetimeIndex(parsed), index=values.index, name=values.name)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f"{column} must contain parseable timestamps with one timezone") from error
    if result.isna().any():
        raise ValueError(f"{column} must contain non-null timestamps")
    return result


def to_relative(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Return a copy using the dataset's documented relative-time origin."""
    if name not in sd.CSV_FILES:
        raise KeyError(f"unknown dataset {name!r}; valid names: {sorted(sd.CSV_FILES)}")
    if not df.columns.is_unique:
        raise ValueError("Input columns must be unique")
    if name in SENSOR_FILES:
        required = {"datetime", "reltime"}
    elif name == "eye_metrics":
        required = {"Test", "Start Time", "End Time"}
    else:
        required = {"Question Start Time", "Question Answer Time"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns for {name}: {sorted(missing)}")
    if name in SENSOR_FILES:
        clock = parse_timestamps(df["datetime"], "datetime")
        if (clock.diff().dropna() < pd.Timedelta(0)).any():
            raise ValueError("datetime must be nondecreasing")
        if df.empty:
            return df.drop(columns=["datetime"])
        if (
            not pd.api.types.is_numeric_dtype(df["reltime"])
            or pd.api.types.is_bool_dtype(df["reltime"])
            or pd.api.types.is_complex_dtype(df["reltime"])
        ):
            raise ValueError("reltime must contain finite real numeric values")
        if (
            (df["reltime"] < 0).any()
            or not df["reltime"].is_monotonic_increasing
            or not np.isfinite(df["reltime"].to_numpy(dtype=float, na_value=np.nan)).all()
        ):
            raise ValueError("reltime must be finite, nonnegative and nondecreasing")
        return df.drop(columns=["datetime"])
    if name == "eye_metrics":
        if df["Test"].isna().any():
            raise ValueError("Test must contain non-null session labels")
        start_column, end_column = "Start Time", "End Time"
        relative_columns = ["Start (s)", "End (s)"]
    else:
        start_column, end_column = "Question Start Time", "Question Answer Time"
        relative_columns = ["Question Start (s)", "Question Answer (s)"]
    start = parse_timestamps(df[start_column], start_column)
    end = parse_timestamps(df[end_column], end_column)
    if start.dt.tz != end.dt.tz:
        raise ValueError("Start and end timestamps must use the same timezone")
    if (end < start).any():
        raise ValueError("End timestamps must not precede their start")
    origin = start.groupby(df["Test"]).transform("min") if name == "eye_metrics" else start.min()
    out = df.copy()
    out[relative_columns[0]] = (start - origin).dt.total_seconds()
    out[relative_columns[1]] = (end - origin).dt.total_seconds()
    out = out.drop(columns=[start_column, end_column])
    if not np.isfinite(out[relative_columns].to_numpy(dtype=float)).all():
        raise ValueError("Elapsed intervals must be finite")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove calendar timestamps and write relative-time CSV copies.",
        allow_abbrev=False,
    )
    parser.add_argument("--data-dir", type=Path, help="Directory containing the source CSVs")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Directory for the CSV copies"
    )
    args = parser.parse_args(argv)
    try:
        destinations = {
            name: sd.validate_output_path(args.output_dir / filename, args.data_dir)
            for name, filename in sd.CSV_FILES.items()
        }
        converted = {name: to_relative(df, name) for name, df in sd.load_all(args.data_dir).items()}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, out in converted.items():
            out.to_csv(destinations[name], index=False)
        print(f"wrote relative-time copies to {args.output_dir}")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"shift_time: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
