"""Tests for the shared sensor_data loader module."""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import sensor_data as sd


def test_load_all_returns_every_csv():
    data = sd.load_all()
    assert set(data) == set(sd.CSV_FILES)
    assert data["eye_metrics"].shape[0] == 264
    assert data["psych"].shape[0] == 88


def test_valid_hr_keeps_only_confident_rows():
    hr = sd.load("hr")
    kept = sd.valid_hr(hr)
    assert (kept["confidence"] == 1.0).all()
    assert 0 < len(kept) <= len(hr)


def test_valid_pupil_drops_tracking_loss():
    kept = sd.valid_pupil(sd.load("sed_fix"))
    assert (kept["pupil"] > 0).all()
    assert (kept["pupilQ"] > 0.5).all()


def test_fixation_durations_match_independent_per_fixation_max():
    sed_fix = sd.load("sed_fix")
    durations = sd.fixation_durations(sed_fix)
    fixation_rows = sed_fix[sed_fix["fixation"]]
    expected = fixation_rows.groupby("fixation_id")["duration"].max()
    expected = expected[expected > 0]
    assert durations.equals(expected)
    assert durations.index.name == "fixation_id"


def test_explicit_data_directory_is_the_csv_directory(tmp_path):
    expected = pd.DataFrame({"confidence": [1.0], "hr": [60]})
    expected.to_csv(tmp_path / "hr.csv", index=False)
    pd.testing.assert_frame_equal(sd.load("hr", base=tmp_path), expected)


def test_missing_default_data_explains_installed_wheel_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "DATA_DIR", tmp_path)
    with pytest.raises(FileNotFoundError) as error:
        sd.load("hr")
    message = str(error.value)
    assert str(tmp_path / "hr.csv") in message
    assert "base=CSV_DIRECTORY" in message and "--data-dir" in message
    assert "not bundled" in message


def test_unknown_resource_is_rejected_before_loading(tmp_path):
    with pytest.raises(KeyError, match="unknown dataset"):
        sd.load("missing", base=tmp_path)


@pytest.mark.parametrize(
    "cutoff",
    [
        np.nan,
        np.inf,
        -np.inf,
        -1,
        1.1,
        True,
        np.bool_(False),
        "0.5",
        None,
        np.timedelta64(1, "ns"),
        np.timedelta64(1, "s"),
        np.timedelta64("NaT", "ns"),
    ],
)
def test_pupil_quality_cutoff_is_finite_and_in_range(cutoff):
    with pytest.raises(ValueError, match="min_quality"):
        sd.valid_pupil(pd.DataFrame({"pupil": [3.0], "pupilQ": [1.0]}), cutoff)


def test_pupil_filter_excludes_nonfinite_measurements_without_mutation():
    eye = pd.DataFrame(
        {
            "pupil": [3.0, np.inf, np.nan, 2.0, 2.0, 0.0, "bad", 2.0],
            "pupilQ": [0.8, 0.8, 0.8, np.inf, np.nan, 0.8, 0.8, 1.1],
        },
        index=[10, 11, 12, 13, 14, 15, 16, 17],
    )
    original = eye.copy(deep=True)
    kept = sd.valid_pupil(eye)
    assert kept.index.tolist() == [10]
    pd.testing.assert_frame_equal(eye, original)


def test_pupil_cutoff_boundaries_retain_strict_comparison():
    eye = pd.DataFrame({"pupil": [2.0, 2.0, 2.0], "pupilQ": [0.0, 0.5, 1.0]})
    assert sd.valid_pupil(eye, 0).index.tolist() == [1, 2]
    assert sd.valid_pupil(eye, 1).empty


@pytest.mark.parametrize("column", ["pupil", "pupilQ"])
def test_object_wrapped_complex_measurements_are_not_cast_to_real(column):
    frame = pd.DataFrame({"pupil": [2.0], "pupilQ": [0.8]})
    frame[column] = pd.Series([2 + 3j], dtype=object)
    with pytest.raises(ValueError, match="real measurements"):
        sd.valid_pupil(frame)


@pytest.mark.parametrize("column", ["pupil", "pupilQ"])
@pytest.mark.parametrize(
    "values",
    [
        pd.Series([True, False]),
        pd.Series([True, pd.NA], dtype="boolean"),
        pd.Series(pd.to_datetime([1, None], unit="ns")),
        pd.Series(pd.to_datetime([1, None], unit="ns", utc=True)),
        pd.Series(pd.to_timedelta([1, None], unit="ns")),
        pd.Series([True, False], dtype="category"),
        pd.Series(pd.to_datetime([1, 2], unit="ns"), dtype="category"),
        pd.Series(pd.to_timedelta([1, 2], unit="ns"), dtype="category"),
    ],
    ids=[
        "bool",
        "nullable-bool",
        "datetime",
        "utc",
        "timedelta",
        "category-bool",
        "category-datetime",
        "category-timedelta",
    ],
)
def test_non_measurement_pupil_column_types_are_rejected_without_mutation(column, values):
    frame = pd.DataFrame({"pupil": [2.0, 3.0], "pupilQ": [0.8, 0.9]})
    frame[column] = values
    original = frame.copy(deep=True)
    with pytest.raises(ValueError, match="real measurements"):
        sd.valid_pupil(frame)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("column", ["pupil", "pupilQ"])
@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        np.bool_(True),
        np.bool_(False),
        date(2024, 1, 1),
        datetime(2024, 1, 1),
        pd.Timestamp("2024-01-01", tz="UTC"),
        np.datetime64(1, "ns"),
        timedelta(microseconds=1),
        pd.Timedelta(1, "ns"),
        np.timedelta64(1, "ns"),
        pd.NaT,
        np.datetime64("NaT", "ns"),
        np.timedelta64("NaT", "ns"),
    ],
)
def test_non_measurement_scalars_in_mixed_object_columns_are_rejected(column, value):
    frame = pd.DataFrame({"pupil": [2.0, 3.0], "pupilQ": [0.8, 0.9]}, index=[10, 20])
    frame[column] = pd.Series([frame[column].iloc[0], value], index=frame.index, dtype=object)
    original = frame.copy(deep=True)
    with pytest.raises(ValueError, match="real measurements"):
        sd.valid_pupil(frame)
    pd.testing.assert_frame_equal(frame, original)


def test_pupil_filter_preserves_numeric_strings_and_ordinary_missing_value_handling():
    frame = pd.DataFrame(
        {
            "pupil": [2.0, "3.0", None, pd.NA, np.nan, "bad"],
            "pupilQ": [0.8, "0.9", 1.0, 1.0, 1.0, 1.0],
        },
        index=[10, 20, 30, 40, 50, 60],
    )
    original = frame.copy(deep=True)
    pd.testing.assert_frame_equal(sd.valid_pupil(frame), frame.loc[[10, 20]])
    pd.testing.assert_frame_equal(frame, original)


def test_cyclic_output_link_gives_a_clear_path_error(tmp_path):
    cycle = tmp_path / "cycle"
    cycle.symlink_to("cycle")
    with pytest.raises(ValueError, match="Cannot resolve"):
        sd.validate_output_path(cycle, tmp_path)


@pytest.mark.parametrize("alias_kind", ["direct", "symlink", "hardlink"])
def test_output_guard_protects_selected_sources_and_aliases(tmp_path, alias_kind):
    source = tmp_path / "hr.csv"
    source.write_text("hr\n60\n")
    destination = source
    if alias_kind != "direct":
        destination = tmp_path / "alias.csv"
        if alias_kind == "symlink":
            destination.symlink_to(source)
        else:
            destination.hardlink_to(source)
    with pytest.raises(ValueError, match="overwrite source CSV"):
        sd.validate_output_path(destination, tmp_path)
    assert source.read_text() == "hr\n60\n"


def test_custom_input_does_not_allow_overwriting_checkout_sources(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    source = canonical / "sed.csv"
    source.write_text("source\noriginal\n")
    other_input = tmp_path / "custom"
    other_input.mkdir()
    monkeypatch.setattr(sd, "DATA_DIR", canonical)
    alias = tmp_path / "canonical-alias.csv"
    alias.hardlink_to(source)
    for destination in (source, alias):
        with pytest.raises(ValueError, match="overwrite source CSV"):
            sd.validate_output_path(destination, other_input)
    assert source.read_text() == "source\noriginal\n"


@pytest.mark.parametrize("alias_kind", ["direct", "symlink", "hardlink"])
@pytest.mark.parametrize("custom_input", [False, True])
def test_output_guard_protects_recording_provenance(
    tmp_path, monkeypatch, alias_kind, custom_input
):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    source = canonical / "RECORDING_PROVENANCE.json"
    source.write_text('{"provenance": "preserved"}\n')
    destination = source
    if alias_kind != "direct":
        destination = tmp_path / "alias.json"
        if alias_kind == "symlink":
            destination.symlink_to(source)
        else:
            destination.hardlink_to(source)
    monkeypatch.setattr(sd, "DATA_DIR", canonical)
    base = tmp_path / "custom" if custom_input else canonical
    with pytest.raises(ValueError, match="overwrite recording provenance"):
        sd.validate_output_path(destination, base)
    assert source.read_text() == '{"provenance": "preserved"}\n'
