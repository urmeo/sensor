"""Validate the intended notebook and its plotting arithmetic."""

import ast
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd
import pytest

import sensor_data as sd

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = [ROOT / "notebooks" / "explore_data.ipynb"]


def test_notebooks_present():
    assert all(path.is_file() for path in NOTEBOOKS)


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[str(p.relative_to(ROOT)) for p in NOTEBOOKS])
def test_notebook_is_valid(path):
    nbformat.validate(nbformat.read(path, as_version=4))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[str(p.relative_to(ROOT)) for p in NOTEBOOKS])
def test_notebook_has_no_error_outputs(path):
    nb = nbformat.read(path, as_version=4)
    bad = [
        (i, out.get("ename"))
        for i, cell in enumerate(nb.cells)
        if cell.get("cell_type") == "code"
        for out in cell.get("outputs", [])
        if out.get("output_type") == "error"
    ]
    assert not bad, f"{path.name} was committed with error outputs: {bad}"


@pytest.fixture(scope="module")
def plot_helpers():
    notebook = nbformat.read(NOTEBOOKS[0], as_version=4)
    functions = []
    for cell in notebook.cells:
        if cell.cell_type == "code":
            functions.extend(
                node for node in ast.parse(cell.source).body if isinstance(node, ast.FunctionDef)
            )
    namespace = {"pd": pd, "np": np, "sd": sd}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(NOTEBOOKS[0]), "exec"), namespace)
    return namespace


def test_pupil_mean_uses_elapsed_seconds_and_breaks_recording_gaps(plot_helpers):
    eye = pd.DataFrame(
        {"reltime": [0, 0.1, 0.2, 0.3, 3, 3.1], "pupil": [1, 2, 3, 4, 30, 40], "pupilQ": 1}
    )
    original = eye.copy(deep=True)
    raw, mean = plot_helpers["pupil_trace"](eye, min_periods=1)
    assert mean.loc[pd.Timedelta(seconds=3)] == 30
    assert mean.loc[pd.Timedelta(seconds=3.1)] == 35
    assert np.isnan(raw.loc[pd.Timedelta(seconds=1.65)])
    assert np.isnan(mean.loc[pd.Timedelta(seconds=1.65)])
    pd.testing.assert_frame_equal(eye, original)


def test_pupil_trace_masks_loss_quality_and_requires_ten_observations(plot_helpers):
    eye = pd.DataFrame(
        {"reltime": [0, 0.5, 1, 1.5], "pupil": [2, 0, 6, 8], "pupilQ": [1, 1, 0.5, 1]}
    )
    raw, mean = plot_helpers["pupil_trace"](eye, min_periods=1)
    for second in (0.5, 1):
        assert np.isnan(raw.loc[pd.Timedelta(seconds=second)])
        assert np.isnan(mean.loc[pd.Timedelta(seconds=second)])
    assert mean.loc[pd.Timedelta(seconds=1.5)] == 5
    _, default_mean = plot_helpers["pupil_trace"](eye)
    assert default_mean.isna().all()


@pytest.mark.parametrize(
    ("column", "value"),
    [("pupil", np.inf), ("pupil", np.nan), ("pupilQ", np.inf), ("pupilQ", np.nan), ("pupilQ", 1.1)],
)
def test_pupil_trace_masks_nonfinite_values_and_invalid_quality(plot_helpers, column, value):
    eye = pd.DataFrame({"reltime": [0, 0.5, 1], "pupil": [2.0, 3.0, 4.0], "pupilQ": 1.0})
    eye.loc[1, column] = value
    raw, mean = plot_helpers["pupil_trace"](eye, min_periods=1)
    assert np.isnan(raw.loc[pd.Timedelta(seconds=0.5)])
    assert np.isnan(mean.loc[pd.Timedelta(seconds=0.5)])
    assert mean.loc[pd.Timedelta(seconds=1)] == 3


@pytest.mark.parametrize(
    "times", [[0, np.inf], [0, np.nan], [0, -1], [1, 0], ["0", "1"], [False, True]]
)
def test_pupil_trace_rejects_invalid_recording_time(plot_helpers, times):
    eye = pd.DataFrame({"reltime": times, "pupil": [2, 3], "pupilQ": 1.0})
    with pytest.raises(ValueError, match="reltime"):
        plot_helpers["pupil_trace"](eye)


@pytest.mark.parametrize("column", ["reltime", "pupil", "pupilQ"])
@pytest.mark.parametrize("dtype", [complex, object])
def test_pupil_trace_rejects_complex_measurements_before_casting(plot_helpers, column, dtype):
    eye = pd.DataFrame({"reltime": [0.0, 1.0], "pupil": [2.0, 3.0], "pupilQ": 1.0})
    eye[column] = pd.Series([2 + 3j, 4.0], dtype=dtype)
    with pytest.raises(ValueError, match=f"{column} must contain real measurements"):
        plot_helpers["pupil_trace"](eye)


@pytest.mark.parametrize("column", ["pupil", "pupilQ"])
@pytest.mark.parametrize(
    "values",
    [
        pytest.param([True, True], id="boolean"),
        pytest.param(pd.Series([True, pd.NA], dtype="boolean"), id="nullable-boolean"),
        pytest.param(pd.date_range("2024-01-01", periods=2), id="datetime"),
        pytest.param(pd.to_timedelta([1, 2], unit="s"), id="timedelta"),
        pytest.param(pd.Series([pd.NaT, pd.NaT]), id="temporal-nat"),
        pytest.param(pd.Series([2.0, True], dtype=object), id="mixed-boolean"),
        pytest.param(
            pd.Series([2.0, pd.Timestamp("2024-01-01")], dtype=object), id="mixed-datetime"
        ),
        pytest.param(pd.Series([2.0, pd.Timedelta(seconds=1)], dtype=object), id="mixed-timedelta"),
    ],
)
def test_pupil_trace_rejects_non_measurement_types(plot_helpers, column, values):
    eye = pd.DataFrame({"reltime": [0.0, 1.0], "pupil": [2.0, 3.0], "pupilQ": 1.0})
    eye[column] = values
    original = eye.copy(deep=True)
    with pytest.raises(ValueError, match="must contain real measurements"):
        plot_helpers["pupil_trace"](eye)
    pd.testing.assert_frame_equal(eye, original)


def test_pupil_trace_keeps_positional_boundaries_with_duplicate_indices(plot_helpers):
    eye = pd.DataFrame(
        {
            "reltime": [0.0, 0.5, 3.0, 3.5],
            "pupil": [2.0, 3.0, 4.0, 5.0],
            "pupilQ": [1.0, 0.0, 1.0, 1.0],
        },
        index=[7, 7, 7, 7],
    )
    original = eye.copy(deep=True)
    raw, mean = plot_helpers["pupil_trace"](eye, min_periods=1)
    for second in (0.5, 1.75):
        assert np.isnan(raw.loc[pd.Timedelta(seconds=second)])
        assert np.isnan(mean.loc[pd.Timedelta(seconds=second)])
    assert raw.loc[pd.Timedelta(seconds=3)] == 4
    assert mean.loc[pd.Timedelta(seconds=3)] == 4
    assert mean.loc[pd.Timedelta(seconds=3.5)] == 4.5
    pd.testing.assert_frame_equal(eye, original)


def test_interval_illustration_uses_thirty_readings_and_twenty_nine_differences(plot_helpers):
    values = pd.Series(np.arange(31, dtype=float) ** 2 + 500)
    rms, sample_sd = plot_helpers["interval_variation"](values)
    assert rms.iloc[:29].isna().all()
    assert sample_sd.iloc[:29].isna().all()
    for end in (29, 30):
        window = values.iloc[end - 29 : end + 1].to_numpy()
        assert len(np.diff(window)) == 29
        assert rms.iloc[end] == pytest.approx(np.sqrt(np.mean(np.diff(window) ** 2)))
        assert sample_sd.iloc[end] == pytest.approx(np.std(window, ddof=1))
