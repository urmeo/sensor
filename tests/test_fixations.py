"""Synthetic boundary checks for candidate events; no empirical validation claims."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sensor_data as sd
from scripts import derive, fixations

PARAMETERS = {
    "displacement_threshold": 0.01,
    "min_quality": 0.5,
    "max_gap_seconds": 0.5,
    "min_duration_seconds": 0.25,
}


def recording(times=None):
    if times is None:
        times = [0.0, 0.25, 0.5, 0.75, 1.0]
    return pd.DataFrame(
        {
            "reltime": times,
            "gazeDir.x": [0.0] * len(times),
            "gazeDir.y": [0.0] * len(times),
            "gazeDir.z": [1.0] * len(times),
            "gazeQ": [1.0] * len(times),
            "iSensor": [0] * len(times),
        }
    )


def detect(raw, **overrides):
    return fixations.detect_events(raw, **(PARAMETERS | overrides))


def bounds(events):
    return list(zip(events["start_row"], events["end_row"], strict=True))


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "scripts.fixations", *map(str, arguments)],
        cwd=Path(fixations.__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def cli_parameters():
    return [
        "--displacement-threshold",
        "0.01",
        "--min-quality",
        "0.5",
        "--max-gap-seconds",
        "0.5",
        "--min-duration-seconds",
        "0.25",
    ]


def test_includes_both_endpoints_without_modifying_input_or_index():
    raw = recording()
    raw.index = ["same", "same", "third", "fourth", "fifth"]
    before = raw.copy(deep=True)
    out = detect(raw)
    pd.testing.assert_frame_equal(raw, before)
    assert list(out.columns) == [*fixations.EVENT_COLUMNS, "iSensor"]
    assert out.iloc[0].to_dict() == {
        "event_id": 1,
        "start_row": 0,
        "end_row": 4,
        "start_time": 0.0,
        "end_time": 1.0,
        "duration": 1.0,
        "sample_count": 5,
        "iSensor": 0,
    }


def test_exact_legacy_99_second_defect_cannot_be_a_new_event():
    raw = recording([0.0, 1.0, 100.0])
    raw["gazeQ"] = [1.0, 0.0, 1.0]
    legacy = derive.detect_legacy_runs(raw)
    assert legacy["fixation"].tolist() == [False, True, True]
    assert legacy["duration"].iloc[1:].tolist() == [99.0, 99.0]
    assert detect(raw).empty


@pytest.mark.parametrize("quality", [0.49, -0.1, 1.1, np.nan, np.inf, -np.inf])
def test_bad_quality_breaks_adjacency_instead_of_filtering_then_joining(quality):
    raw = recording()
    raw.loc[2, "gazeQ"] = quality
    out = detect(raw)
    assert bounds(out) == [(0, 1), (3, 4)]
    assert out["duration"].tolist() == [0.25, 0.25]


@pytest.mark.parametrize("column", fixations.REQUIRED_COLUMNS)
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_measurement_is_a_boundary(column, value):
    raw = recording()
    raw.loc[2, column] = value
    assert bounds(detect(raw)) == [(0, 1), (3, 4)]


@pytest.mark.parametrize("column", fixations.REQUIRED_COLUMNS)
@pytest.mark.parametrize("value", [True, "invalid", "0.5", 1 + 0j, None])
def test_invalid_scalar_is_a_boundary(column, value):
    raw = recording()
    raw[column] = raw[column].astype(object)
    raw.loc[2, column] = value
    assert bounds(detect(raw)) == [(0, 1), (3, 4)]


@pytest.mark.parametrize("column", [*fixations.REQUIRED_COLUMNS, "iSensor"])
@pytest.mark.parametrize("unit", ["ns", "s", "NaT"])
def test_numpy_timedelta_measurements_and_channels_break_runs(column, unit):
    raw = recording([0, 1, 2, 3, 4])
    numeric_value = int(raw[column].iloc[2])
    value = np.timedelta64("NaT", "ns") if unit == "NaT" else np.timedelta64(numeric_value, unit)
    raw[column] = raw[column].astype(object)
    raw.loc[2, column] = value
    assert bounds(detect(raw, max_gap_seconds=1, min_duration_seconds=1)) == [(0, 1), (3, 4)]


def test_zero_vector_is_a_boundary_but_nonunit_scale_is_preserved():
    raw = recording()
    raw.loc[2, fixations.VECTOR_COLUMNS] = 0
    assert bounds(detect(raw, displacement_threshold=10)) == [(0, 1), (3, 4)]
    raw = recording([0.0, 0.25])
    raw["gazeDir.z"] = [2.0, 2.25]
    assert detect(raw, displacement_threshold=0.2).empty
    assert bounds(detect(raw, displacement_threshold=0.25)) == [(0, 1)]


def test_gap_splits_separate_valid_runs():
    raw = recording([0.0, 0.25, 99.25, 99.5, 99.75])
    assert bounds(detect(raw)) == [(0, 1), (2, 4)]
    assert detect(recording([0.0, 99.0])).empty


@pytest.mark.parametrize("times", [[0, 0.25, 0.25, 0.5, 0.75], [0, 0.25, 0.0, 0.25, 0.5]])
def test_nonincreasing_time_splits_without_sorting_or_bridging(times):
    out = detect(recording(times))
    assert bounds(out) == [(0, 1), (2, 4)]
    assert out["duration"].tolist() == [0.25, 0.5]


def test_negative_time_is_invalid():
    raw = recording()
    raw.loc[2, "reltime"] = -1
    assert bounds(detect(raw)) == [(0, 1), (3, 4)]


def test_integer_timestamps_preserve_gap_comparisons_before_float_rounding():
    raw = recording([2**53 + 2, 2**53 + 5])
    raw["reltime"] = raw["reltime"].astype("uint64")
    assert detect(raw, max_gap_seconds=2, min_duration_seconds=1).empty
    out = detect(raw, max_gap_seconds=3, min_duration_seconds=3)
    assert int(out["start_time"].iloc[0]) == 2**53 + 2
    assert int(out["end_time"].iloc[0]) == 2**53 + 5
    assert out["duration"].iloc[0] == 3
    raw["reltime"] = np.array([2**53 + 1, 2**53 + 2], dtype=np.uint64)
    assert bounds(detect(raw, max_gap_seconds=1, min_duration_seconds=1)) == [(0, 1)]
    raw["reltime"] = np.array([1, 2**53 + 2], dtype=np.uint64)
    assert detect(raw, max_gap_seconds=2**53, min_duration_seconds=1).empty


def test_nullable_integer_times_keep_exact_differences_and_break_on_missing():
    raw = recording()
    raw["reltime"] = pd.Series([2**60, 2**60 + 1, pd.NA, 2**60 + 3, 2**60 + 4], dtype="UInt64")
    out = detect(raw, max_gap_seconds=1, min_duration_seconds=1)
    assert bounds(out) == [(0, 1), (3, 4)]
    assert out["duration"].tolist() == [1, 1]


def test_unrepresentable_integer_time_in_mixed_object_column_is_a_boundary():
    raw = recording([0.0, 0.25, 0.5, 0.75, 1.0])
    raw["reltime"] = raw["reltime"].astype(object)
    raw.loc[2, "reltime"] = 2**53 + 1
    assert bounds(detect(raw, max_gap_seconds=2**54)) == [(0, 1), (3, 4)]


def test_channel_change_splits_and_preserves_recorded_channel_identity():
    raw = recording()
    raw["iSensor"] = [0, 0, 1, 1, 1]
    out = detect(raw)
    assert bounds(out) == [(0, 1), (2, 4)]
    assert out["iSensor"].tolist() == [0, 1]
    assert out["event_id"].tolist() == [1, 2]


@pytest.mark.parametrize("channel", [np.nan, np.inf, None, "", True])
def test_missing_or_invalid_channel_is_a_boundary(channel):
    raw = recording()
    raw["iSensor"] = raw["iSensor"].astype(object)
    raw.loc[2, "iSensor"] = channel
    assert bounds(detect(raw)) == [(0, 1), (3, 4)]


def test_absent_channel_is_one_unidentified_stream():
    out = detect(recording().drop(columns="iSensor"))
    assert list(out.columns) == fixations.EVENT_COLUMNS
    assert bounds(out) == [(0, 4)]


def test_displacement_includes_anchor_and_splits_at_large_step():
    raw = recording()
    raw["gazeDir.x"] = [0.0, 0.005, 0.5, 0.505, 0.51]
    assert bounds(detect(raw)) == [(0, 1), (2, 4)]


def test_threshold_quality_gap_and_duration_equalities_are_inclusive():
    raw = recording([0.0, 0.25])
    raw["gazeDir.x"] = [0.0, 0.25]
    raw["gazeQ"] = 0.5
    assert bounds(detect(raw, displacement_threshold=0.25, max_gap_seconds=0.25)) == [(0, 1)]
    assert detect(raw, displacement_threshold=0.25, min_duration_seconds=0.251).empty
    assert bounds(detect(recording([0.0, 0.25]), displacement_threshold=0)) == [(0, 1)]


@pytest.mark.parametrize("length", [0, 1])
def test_empty_and_singleton_have_typed_empty_event_table(length):
    out = detect(recording().iloc[:length])
    assert out.empty
    assert out["event_id"].dtype == np.dtype("int64")
    assert out["duration"].dtype == np.dtype("float64")


@pytest.mark.parametrize("parameter", PARAMETERS)
@pytest.mark.parametrize(
    "value",
    [
        np.nan,
        np.inf,
        -np.inf,
        -1,
        True,
        "0.5",
        None,
        np.timedelta64(1, "ns"),
        np.timedelta64(1, "s"),
        np.timedelta64("NaT", "ns"),
    ],
)
def test_invalid_parameters_are_rejected(parameter, value):
    with pytest.raises(ValueError, match=parameter):
        detect(recording(), **{parameter: value})


@pytest.mark.parametrize("parameter", ["max_gap_seconds", "min_duration_seconds"])
def test_gap_and_duration_must_be_positive(parameter):
    with pytest.raises(ValueError, match=parameter):
        detect(recording(), **{parameter: 0})


def test_quality_cutoff_cannot_exceed_one():
    with pytest.raises(ValueError, match="min_quality"):
        detect(recording(), min_quality=1.01)


def test_required_parameters_are_not_silently_defaulted():
    with pytest.raises(TypeError):
        fixations.detect_events(recording())


@pytest.mark.parametrize("column", fixations.REQUIRED_COLUMNS)
def test_missing_required_column_is_rejected(column):
    with pytest.raises(ValueError, match="Missing required columns"):
        detect(recording().drop(columns=column))


def test_duplicate_column_is_rejected():
    raw = recording()
    with pytest.raises(ValueError, match="unique"):
        detect(pd.concat([raw, raw[["reltime"]]], axis=1))


def test_extreme_finite_vectors_do_not_make_overflowed_displacement_an_event():
    raw = recording([0.0, 0.25])
    raw["gazeDir.x"] = [np.finfo(float).max, -np.finfo(float).max]
    assert detect(raw, displacement_threshold=np.finfo(float).max).empty
    raw["gazeDir.x"] = [0.0, 1e200]
    assert bounds(detect(raw, displacement_threshold=1e200)) == [(0, 1)]


def test_nullable_numeric_measurements_break_at_missing_values():
    raw = recording()
    raw["gazeQ"] = raw["gazeQ"].astype("Float64")
    raw.loc[2, "gazeQ"] = pd.NA
    assert bounds(detect(raw)) == [(0, 1), (3, 4)]


def test_cli_writes_separate_events_and_source_parameter_provenance(tmp_path):
    data = tmp_path / "input"
    data.mkdir()
    raw = recording()
    raw.to_csv(data / "sed.csv", index=False)
    (data / "RECORDING_PROVENANCE.json").write_text('{"schema_version": 1}\n')
    before = (data / "sed.csv").read_bytes()
    output = tmp_path / "output" / "candidate-events.csv"
    result = run_cli("--data-dir", data, "--output", output, *cli_parameters())
    assert result.returncode == 0, result.stderr
    pd.testing.assert_frame_equal(pd.read_csv(output), detect(raw))
    sidecar = json.loads(Path(f"{output}.json").read_text())
    assert sidecar["algorithm"] == fixations.ALGORITHM
    assert sidecar["parameters"] == PARAMETERS
    assert sidecar["source"]["sha256"] == hashlib.sha256(before).hexdigest()
    assert sidecar["source"]["sample_count"] == len(raw)
    assert sidecar["event_csv_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = data / "RECORDING_PROVENANCE.json"
    assert sidecar["recording_provenance"]["path"] == str(manifest.resolve())
    assert (
        sidecar["recording_provenance"]["sha256"]
        == hashlib.sha256(manifest.read_bytes()).hexdigest()
    )
    assert sidecar["validation"]["empirical_validation"] == "not established"
    assert "unverified" in sidecar["device_mapping"]
    assert (data / "sed.csv").read_bytes() == before


@pytest.mark.parametrize("filename", sd.CSV_FILES.values())
def test_cli_cannot_overwrite_any_source_resource(tmp_path, filename):
    raw = recording()
    raw.to_csv(tmp_path / "sed.csv", index=False)
    source = tmp_path / filename
    if not source.exists():
        source.write_text("preserved\n")
    before = source.read_bytes()
    result = run_cli("--data-dir", tmp_path, "--output", source, *cli_parameters())
    assert result.returncode == 1
    assert "overwrite source" in result.stderr
    assert source.read_bytes() == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "sidecar_symlink"])
def test_cli_rejects_source_aliases_before_writing(tmp_path, kind):
    source = tmp_path / "sed.csv"
    recording().to_csv(source, index=False)
    output = tmp_path / "events.csv"
    if kind == "symlink":
        output.symlink_to(source)
    elif kind == "hardlink":
        output.hardlink_to(source)
    else:
        Path(f"{output}.json").symlink_to(source)
    before = source.read_bytes()
    result = run_cli("--data-dir", tmp_path, "--output", output, *cli_parameters())
    assert result.returncode == 1 and "overwrite source" in result.stderr
    assert source.read_bytes() == before
    if kind == "sidecar_symlink":
        assert not output.exists()


def test_cli_rejects_csv_sidecar_alias(tmp_path):
    recording().to_csv(tmp_path / "sed.csv", index=False)
    output = tmp_path / "events.csv"
    output.write_text("preserved\n")
    Path(f"{output}.json").hardlink_to(output)
    result = run_cli("--data-dir", tmp_path, "--output", output, *cli_parameters())
    assert result.returncode == 1 and "separate files" in result.stderr
    assert output.read_text() == "preserved\n"


def test_cli_rejects_directory_sidecar_before_writing_csv(tmp_path):
    recording().to_csv(tmp_path / "sed.csv", index=False)
    output = tmp_path / "events.csv"
    Path(f"{output}.json").mkdir()
    result = run_cli("--data-dir", tmp_path, "--output", output, *cli_parameters())
    assert result.returncode == 1 and "regular file" in result.stderr
    assert not output.exists()


def test_cli_parameters_are_required_and_invalid_values_do_not_write(tmp_path):
    recording().to_csv(tmp_path / "sed.csv", index=False)
    output = tmp_path / "events.csv"
    assert run_cli("--data-dir", tmp_path, "--output", output).returncode == 2
    result = run_cli(
        "--data-dir",
        tmp_path,
        "--output",
        output,
        *cli_parameters(),
        "--max-gap-seconds",
        "0",
    )
    assert result.returncode == 1 and "max_gap_seconds" in result.stderr
    assert not output.exists()
    assert not Path(f"{output}.json").exists()


@pytest.mark.parametrize("prefix", ["", "\n", " \t\n", "\n \t\r\n", "\ufeff\n", "\ufeff \t\r\n"])
def test_cli_rejects_duplicate_raw_csv_headers_before_pandas_renames_them(tmp_path, prefix):
    source = tmp_path / "sed.csv"
    source.write_text(
        prefix + "reltime,gazeQ,gazeQ,gazeDir.x,gazeDir.y,gazeDir.z\n0,1,0,0,0,1\n0.25,1,0,0,0,1\n"
    )
    output = tmp_path / "events.csv"
    result = run_cli("--data-dir", tmp_path, "--output", output, *cli_parameters())
    assert result.returncode == 1 and "unique" in result.stderr
    assert not output.exists()
    assert not Path(f"{output}.json").exists()


@pytest.mark.parametrize("prefix", ["\n", " \t\n", "\n \t\r\n", "\ufeff\n", "\ufeff \t\r\n"])
def test_cli_header_validation_accepts_leading_blank_lines_like_pandas(tmp_path, prefix):
    raw = recording()
    (tmp_path / "sed.csv").write_text(prefix + raw.to_csv(index=False))
    output = tmp_path / "events.csv"
    result = run_cli("--data-dir", tmp_path, "--output", output, *cli_parameters())
    assert result.returncode == 0, result.stderr
    pd.testing.assert_frame_equal(pd.read_csv(output), detect(raw))


def test_cli_missing_input_and_cyclic_output_are_handled_without_traceback(tmp_path):
    output = tmp_path / "events.csv"
    result = run_cli("--data-dir", tmp_path, "--output", output, *cli_parameters())
    assert result.returncode == 1 and "--data-dir" in result.stderr
    cycle = tmp_path / "cycle"
    cycle.symlink_to("cycle")
    result = run_cli("--data-dir", tmp_path, "--output", cycle, *cli_parameters())
    assert result.returncode == 1 and "Cannot resolve" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_empty_source_writes_header_and_no_candidates(tmp_path):
    recording().iloc[:0].to_csv(tmp_path / "sed.csv", index=False)
    output = tmp_path / "events.csv"
    result = run_cli("--data-dir", tmp_path, "--output", output, *cli_parameters())
    assert result.returncode == 0, result.stderr
    assert pd.read_csv(output).empty
    assert json.loads(Path(f"{output}.json").read_text())["event_count"] == 0
