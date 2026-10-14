"""Legacy derivation matches within its stated floating-point tolerance."""

import hashlib
import runpy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sensor_data as sd
from scripts import derive


def test_detect_legacy_runs_reproduces_committed_file():
    derived = derive.detect_legacy_runs(sd.load("sed"))
    committed = sd.load("sed_fix")

    assert list(derived.columns) == list(committed.columns)
    for col in committed.columns:
        a, b = derived[col], committed[col]
        if col in ("gaze_diff", "duration"):
            assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=1e-9, equal_nan=True), col
        else:
            assert a.equals(b), col


def test_check_helper_passes():
    assert derive.check() is True


def test_detect_legacy_runs_accepts_empty_recording():
    empty = pd.DataFrame(columns=["gazeDir.x", "gazeDir.y", "gazeDir.z", "reltime"], dtype=float)
    out = derive.detect_legacy_runs(empty)
    assert out.empty
    assert list(out.columns) == list(empty.columns) + derive.DERIVED_COLUMNS


@pytest.mark.parametrize("matches", [True, False])
def test_check_command_exit_status(monkeypatch, capsys, matches):
    raw = pd.DataFrame(
        {
            "gazeDir.x": [0.0, 0.0],
            "gazeDir.y": [0.0, 0.0],
            "gazeDir.z": [1.0, 1.0],
            "reltime": [0.0, 1.0],
        }
    )
    committed = derive.detect_legacy_runs(raw)
    if not matches:
        committed.loc[1, "duration"] = 99.0
    monkeypatch.setattr(sd, "load", lambda name, base=None: raw if name == "sed" else committed)
    monkeypatch.setattr(sys, "argv", ["scripts/derive.py", "--check"])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(derive.__file__, run_name="__main__")
    assert result.value.code == (0 if matches else 1)
    assert str(matches) in capsys.readouterr().out


def raw_frame():
    return pd.DataFrame(
        {
            "gazeDir.x": [0.0, 0.0, 0.003, 0.03, 0.03, 0.03, 0.5],
            "gazeDir.y": [0.0] * 7,
            "gazeDir.z": [1.0] * 7,
            "reltime": [0.0, 0.02, 0.15, 0.16, 0.5, 1.0, 1.3],
            "source": ["kept"] * 7,
        },
        index=[2, 4, 6, 8, 10, 12, 14],
    )


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "scripts.derive", *map(str, arguments)],
        cwd=Path(derive.__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def test_nonuniform_legacy_runs_and_input_preservation():
    raw = raw_frame()
    original = raw.copy(deep=True)
    out = derive.detect_legacy_runs(raw)
    assert out.index.equals(raw.index)
    pd.testing.assert_frame_equal(out[raw.columns], raw)
    pd.testing.assert_frame_equal(raw, original)
    assert out["fixation"].tolist() == [False, True, True, False, True, True, False]
    assert out["fixation_id"].tolist() == [1, 2, 2, 3, 4, 4, 5]
    np.testing.assert_allclose(out["duration"], [np.nan, 0.13, 0.13, np.nan, 0.5, 0.5, np.nan])


def test_singleton_has_no_measured_fixation_span():
    raw = raw_frame().iloc[:1]
    out = derive.detect_legacy_runs(raw)
    assert out.index.equals(raw.index) and len(out) == 1
    assert not out["fixation"].iloc[0] and out["fixation_id"].iloc[0] == 1
    assert out[["gaze_diff", "duration"]].isna().all().all()


@pytest.mark.parametrize(
    "threshold",
    [
        np.nan,
        np.inf,
        -np.inf,
        -1,
        True,
        np.bool_(False),
        "0.01",
        None,
        [0.01],
        np.timedelta64(1, "ns"),
        np.timedelta64(1, "s"),
        np.timedelta64("NaT", "ns"),
    ],
)
def test_invalid_threshold_is_rejected(threshold):
    with pytest.raises(ValueError, match="threshold"):
        derive.detect_legacy_runs(raw_frame(), threshold)


@pytest.mark.parametrize("column", derive.REQUIRED_COLUMNS)
@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_nonfinite_required_values_are_rejected(column, bad_value):
    raw = raw_frame()
    raw.loc[raw.index[1], column] = bad_value
    with pytest.raises(ValueError, match="finite"):
        derive.detect_legacy_runs(raw)


@pytest.mark.parametrize("values", [["bad"] * 7, [True] * 7, [1 + 1j] * 7])
def test_required_values_must_be_real_numeric_columns(values):
    raw = raw_frame()
    raw["gazeDir.x"] = values
    with pytest.raises(ValueError, match="real numeric"):
        derive.detect_legacy_runs(raw)


@pytest.mark.parametrize("times", [[-1, 0, 1, 2, 3, 4, 5], [0, 2, 1, 3, 4, 5, 6]])
def test_invalid_relative_times_are_rejected(times):
    raw = raw_frame()
    raw["reltime"] = times
    with pytest.raises(ValueError, match="nonnegative and nondecreasing"):
        derive.detect_legacy_runs(raw)


def test_equal_timestamps_are_preserved():
    raw = raw_frame()
    raw["reltime"] = 0.0
    out = derive.detect_legacy_runs(raw)
    assert (out.loc[out["fixation"], "duration"] == 0).all()


def test_large_integer_times_are_checked_before_float_rounding():
    raw = raw_frame().iloc[:3].copy()
    raw["reltime"] = np.array([2**60, 2**60 + 1, 2**60], dtype=np.uint64)
    with pytest.raises(ValueError, match="nondecreasing"):
        derive.detect_legacy_runs(raw)
    raw["reltime"] = np.array([2**60, 2**60 + 1, 2**60 + 2], dtype=np.uint64)
    out = derive.detect_legacy_runs(raw)
    assert out["duration"].iloc[1] == 1
    pd.testing.assert_series_equal(out["reltime"], raw["reltime"])


def test_missing_and_duplicate_columns_are_rejected():
    with pytest.raises(ValueError, match="Missing required"):
        derive.detect_legacy_runs(raw_frame().drop(columns="reltime"))
    duplicate = pd.concat([raw_frame(), raw_frame()[["reltime"]]], axis=1)
    with pytest.raises(ValueError, match="unique"):
        derive.detect_legacy_runs(duplicate)


@pytest.mark.parametrize(
    "arguments,status",
    [
        ([], 0),
        (["--check"], 0),
        (["--help"], 0),
        (["--chek"], 2),
        (["--out", "unused"], 2),
        (["--check", "--output", "unused"], 2),
    ],
)
def test_actual_module_modes_never_modify_inputs(tmp_path, arguments, status):
    raw = raw_frame().reset_index(drop=True)
    raw.to_csv(tmp_path / "sed.csv", index=False)
    derive.detect_legacy_runs(raw).to_csv(tmp_path / "sed_fix.csv", index=False)
    before = {file.name: hashlib.sha256(file.read_bytes()).digest() for file in tmp_path.iterdir()}
    arguments = [
        str(tmp_path / "unused.csv") if value == "unused" else value for value in arguments
    ]
    result = run_cli("--data-dir", tmp_path, *arguments)
    assert result.returncode == status, result.stderr
    after = {file.name: hashlib.sha256(file.read_bytes()).digest() for file in tmp_path.iterdir()}
    assert before == after


def test_actual_module_mismatch_and_explicit_output(tmp_path):
    data = tmp_path / "input"
    data.mkdir()
    raw = raw_frame().reset_index(drop=True)
    raw.to_csv(data / "sed.csv", index=False)
    committed = derive.detect_legacy_runs(raw)
    committed.loc[1, "duration"] = 99.0
    committed.to_csv(data / "sed_fix.csv", index=False)
    assert run_cli("--data-dir", data, "--check").returncode == 1
    destination = tmp_path / "outputs" / "derived.csv"
    result = run_cli("--data-dir", data, "--output", destination)
    assert result.returncode == 0, result.stderr
    pd.testing.assert_frame_equal(pd.read_csv(destination), derive.detect_legacy_runs(raw))
    result = run_cli("--data-dir", data, "--output", data / "sed.csv")
    assert result.returncode == 1 and "overwrite source CSV" in result.stderr
    pd.testing.assert_frame_equal(pd.read_csv(data / "sed.csv"), raw)


def test_actual_module_empty_csv_stays_empty(tmp_path):
    raw = pd.DataFrame(columns=derive.REQUIRED_COLUMNS)
    raw.to_csv(tmp_path / "sed.csv", index=False)
    expected = derive.detect_legacy_runs(raw)
    assert expected.dtypes[derive.DERIVED_COLUMNS].astype(str).tolist() == [
        "float64",
        "bool",
        "int64",
        "float64",
    ]
    expected.to_csv(tmp_path / "sed_fix.csv", index=False)
    destination = tmp_path / "empty-output.csv"
    result = run_cli("--data-dir", tmp_path, "--output", destination)
    assert result.returncode == 0, result.stderr
    assert pd.read_csv(destination).empty
    assert run_cli("--data-dir", tmp_path, "--check").returncode == 0


def test_missing_input_cli_gives_helpful_error(tmp_path):
    result = run_cli("--data-dir", tmp_path, "--check")
    assert result.returncode == 1
    assert "--data-dir" in result.stderr and "not found" in result.stderr


def test_cyclic_output_cli_is_an_input_error_without_a_traceback(tmp_path):
    cycle = tmp_path / "cycle"
    cycle.symlink_to("cycle")
    result = run_cli("--data-dir", tmp_path, "--output", cycle)
    assert result.returncode == 1 and "Cannot resolve" in result.stderr
    assert "Traceback" not in result.stderr


def test_deprecated_fixation_name_preserves_legacy_reproduction():
    raw = raw_frame()
    with pytest.warns(DeprecationWarning, match="legacy low-movement runs"):
        historical = derive.detect_fixations(raw)
    pd.testing.assert_frame_equal(historical, derive.detect_legacy_runs(raw))


def test_legacy_reproduction_retains_quality_and_gap_defect():
    """Lock historical behavior separately from the candidate event detector."""
    raw = pd.DataFrame(
        {
            "gazeDir.x": [0.0, 0.0, 0.0],
            "gazeDir.y": [0.0, 0.0, 0.0],
            "gazeDir.z": [1.0, 1.0, 1.0],
            "reltime": [0.0, 1.0, 100.0],
            "gazeQ": [1.0, 0.0, 1.0],
        }
    )
    out = derive.detect_legacy_runs(raw)
    assert out["fixation"].tolist() == [False, True, True]
    assert out["fixation_id"].tolist() == [1, 2, 2]
    np.testing.assert_allclose(out["duration"], [np.nan, 99.0, 99.0])
