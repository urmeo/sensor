# Historical runs and candidate gaze events

`data/sed_fix.csv` contains historical low-movement runs. The function
`scripts.derive.detect_legacy_runs` reproduces them from gaze displacement,
without checking gaze quality, maximum time gaps or minimum duration. The old
`detect_fixations` import is a deprecated compatibility wrapper. Existing
descriptive results use this historical file; its runs are not validated
fixation events.

For example, three identical gaze vectors at `reltime=[0, 1, 100]` with
`gazeQ=[1, 0, 1]` produce one 99-second historical run across the last two
samples. Its duration starts at the first row labelled as low movement. It
excludes the preceding sample used to calculate that row's displacement.

`scripts.fixations.detect_events` and its CLI generate separate candidate gaze
events using the rules below. Synthetic tests check these rules. Device identity,
calibration, the meaning of gaze quality, parameter suitability and physiological
fixation accuracy remain unverified. Neither the historical runs nor the new
candidates are clinically or biologically validated fixations.

## Required parameters and inputs

The API requires four keyword arguments. The CLI requires the corresponding
flags. There are no default study parameters:

| API argument | CLI flag | Meaning |
| --- | --- | --- |
| `displacement_threshold` | `--displacement-threshold` | Finite nonnegative maximum Euclidean step in the recorded gaze-vector units. |
| `min_quality` | `--min-quality` | Finite minimum recorded `gazeQ`, in `[0, 1]`. |
| `max_gap_seconds` | `--max-gap-seconds` | Finite positive maximum adjacent `reltime` difference, in seconds. |
| `min_duration_seconds` | `--min-duration-seconds` | Finite positive minimum event span, in seconds. |

The required columns are `reltime`, `gazeQ`, `gazeDir.x`, `gazeDir.y` and
`gazeDir.z`. Values must be real numbers. Booleans, strings, complex values,
missing values and nonfinite values invalidate the sample. `reltime` must be
nonnegative, and an all-zero gaze vector is invalid. The detector keeps the
recorded vector scale. It does not normalize vectors or convert displacement
to degrees, so scaling the vectors can change the result.

`iSensor` is optional. When present, events stay within one recorded identifier
and include it in the output. Finite real numbers and nonempty strings are
accepted as identifiers. A changed or missing identifier, a nonfinite number,
a boolean or an empty string breaks the run. These labels do not establish
hardware mappings. When `iSensor` is absent, the caller must supply a single
recording stream. The detector cannot infer hidden channels or recording
boundaries.

The detector processes rows in their supplied order. It does not sort them or
drop invalid rows before checking adjacent samples. Duplicate column names are
rejected, including CSV headers that pandas would otherwise rename. The header
check skips leading blank or whitespace-only CSV lines, as the CSV loader does.

## Boundary and duration contract

An event is a maximal run of valid adjacent samples. Two adjacent samples belong
to the same run only when all of these conditions hold:

- Both endpoint samples are valid and meet `min_quality <= gazeQ <= 1`.
- The time difference is strictly positive and at most `max_gap_seconds`.
- The finite Euclidean vector step is at most `displacement_threshold`.
- The recorded channel identifier is unchanged when `iSensor` is present.

Every invalid sample breaks the run. Repeated or decreasing time, a long gap,
a large or overflowed displacement, and a channel change also end it. The next
valid sample can start a new run. Samples on opposite sides of an invalid sample
are never reconnected. The 99-second historical example therefore produces no
candidate event.

Both endpoints belong to an event. Its duration is the last `reltime` minus the
first `reltime`; no sampling rate is assumed. A run is retained when its duration
is at least `min_duration_seconds`. A single sample has no positive measured
duration and cannot be an event. Equality is accepted for displacement, maximum
gap, quality cutoff and minimum duration. Time must increase strictly.

Integer-typed timestamps use exact integer subtraction and keep integer
endpoints and durations. This prevents floating-point rounding of large
`uint64` values from changing whether a gap is allowed. In mixed object columns,
integer timestamps that cannot be converted to a float and back exactly are
invalid samples. Use an integer dtype when exact integer times are needed.
Floating-point timestamps use their recorded precision.

This rule checks consecutive steps, rather than dispersion or velocity. A series
of small steps can drift far during a long event. Duration and gap limits do not
establish biological validity, compensate for an unverified device or recover
missing samples. Threshold choices need independent study and device evidence.

## Separate exports and provenance

This example shows the API with the supplied eye stream. The parameters are
illustrative; they are neither recommended nor calibrated settings:

```python
import sensor_data as sd
from scripts.fixations import detect_events

events = detect_events(
    sd.load("sed"),
    displacement_threshold=0.01,
    min_quality=0.5,
    max_gap_seconds=0.05,
    min_duration_seconds=0.1,
)
```

The CLI exports a separate event table and a JSON sidecar. For example:

```sh
python -m scripts.fixations \
  --data-dir data \
  --output outputs/candidate_events.csv \
  --displacement-threshold 0.01 \
  --min-quality 0.5 \
  --max-gap-seconds 0.05 \
  --min-duration-seconds 0.1
```

The table has one row per candidate, with `event_id`, inclusive zero-based
`start_row` and `end_row` positions, `start_time`, `end_time`, `duration`, and
`sample_count`. `iSensor` is included when it exists in the input. Row positions
refer to the source CSV data rows and are independent of a DataFrame's index.
An empty export keeps its column headers. The input is not modified.

`outputs/candidate_events.csv.json` records:

- The algorithm identifier `sensor.gaze-step-events/v1`, implementation SHA-256,
  exact source CSV SHA-256, source path and sample count.
- All four parameters, distance and time units, and the channel column.
- The exported CSV SHA-256, candidate count, validation scope and limitations.

If `RECORDING_PROVENANCE.json` is in the input directory, the sidecar includes
its path and SHA-256. Device mapping and calibration remain marked unverified.
The acquisition manifest records available evidence and unknowns separately from
the detector parameters.

The CSV and sidecar must be different files. Both destinations are checked
against the source CSVs and acquisition manifest, including symbolic links and
hard links. Exports cannot overwrite `sed_fix.csv` or any other protected source
file. Choosing an existing separate output path replaces that export.

## Checks

Run the synthetic and CLI tests with:

```sh
python -m pytest tests/test_fixations.py
```

The suite covers the exact 99-second historical failure, invalid and low quality,
nonfinite and invalid vectors, zero vectors, long gaps, equal and decreasing
times, channel changes, minimum spans, inclusive parameter boundaries, input
preservation, large integer timestamps, empty and singleton recordings, invalid
parameters, duplicate CSV headers, protection against overwriting source files
through links, and sidecar source and parameter identity. These checks test the
implementation's rules. Empirical
validation requires separate labelled recordings and verified acquisition and
calibration provenance.
