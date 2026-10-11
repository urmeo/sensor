# Sensor

**Biosignals · Eye tracking · Timing · Provenance**

**11 devices · 2 facial tools · 1 participant · 6 CSVs · 3 summary sessions.** Raw: Session 1.

## Data flow

```mermaid
flowchart LR
    A[CSVs] --> B[Schema/clock checks]
    B --> C[Gaze runs]
    B --> D[Plots]
    C --> D
```

## Data

| CSV | Rows | Content |
| --- | ---: | --- |
| `hr` | 4,032 | HR samples |
| `ibi` | 2,394 | Intervals |
| `sed` | 34,171 | Gaze/pupil |
| `sed_fix` | 34,171 | Runs |
| `eye_metrics` | 264 | Summaries |
| `Psychometric_Test_Results` | 88 | Responses/timing |

[Dictionary](data/DATA_DICTIONARY.md) · [Schema](datapackage.json) · [Notebook](notebooks/explore_data.ipynb)

## Equipment

<table>
<tr>
<td align="center" valign="top" width="33%"><img src="docs/images/pupil-labs-core.jpg" width="180" alt="Pupil Labs Core"><br>Pupil Labs Core</td>
<td align="center" valign="top" width="33%"><img src="docs/images/tobii-pro-glasses-3.jpg" width="180" alt="Tobii Pro Glasses 3"><br>Tobii Pro Glasses 3</td>
<td align="center" valign="top" width="33%"><img src="docs/images/smi-eye-tracking.jpg" width="180" alt="SMI eye tracking"><br>SMI eye tracking</td>
</tr>
<tr>
<td align="center" valign="top" width="33%"><img src="docs/images/polar-h10.jpg" width="180" alt="Polar H10"><br>Polar H10</td>
<td align="center" valign="top" width="33%"><img src="docs/images/moofit-hw401.jpg" width="180" alt="Moofit HW401"><br>Moofit HW401</td>
<td align="center" valign="top" width="33%"><img src="docs/images/empatica-e4.jpg" width="180" alt="Empatica E4"><br>Empatica E4</td>
</tr>
<tr>
<td align="center" valign="top" width="33%"><img src="docs/images/tea-captiv-t-sens-gsr.jpg" width="180" alt="TEA T-SENS GSR"><br>TEA T-SENS GSR</td>
<td align="center" valign="top" width="33%"><img src="docs/images/biopac-eda.jpg" width="180" alt="BIOPAC EDA"><br>BIOPAC EDA</td>
<td align="center" valign="top" width="33%"><img src="docs/images/axis-p1275.jpg" width="180" alt="AXIS P1275"><br>AXIS P1275</td>
</tr>
<tr>
<td align="center" valign="top" width="33%"><img src="docs/images/axis-p1245.jpg" width="180" alt="AXIS P1245"><br>AXIS P1245</td>
<td align="center" valign="top" width="33%"><img src="docs/images/optitrack-slim-x13.jpg" width="180" alt="OptiTrack Slim X13"><br>OptiTrack Slim X13</td>
<td align="center" valign="top" width="33%"><img src="docs/images/openface.jpg" width="180" alt="OpenFace"><br>OpenFace</td>
</tr>
<tr>
<td align="center" valign="top" width="33%"><img src="docs/images/noldus-facereader.jpg" width="180" alt="Noldus FaceReader"><br>Noldus FaceReader</td>
</tr>
</table>

Channel mapping unverified. [Corrections](NOTICE.md#supported-corrections) · [Image credits](docs/images/CREDITS.md)

## Setup

The notebook is in `notebooks/`; data commands are in `scripts/`. Reviews and equipment images are in `docs/`.

```bash
python -m pip install -e .
python -m scripts.derive --check
```

Wheels require `--data-dir /path/to/data`. [Commands](CONTRIBUTING.md).

| Stack | Tools |
| --- | --- |
| Runtime | Python ≥3.11, NumPy, pandas, Matplotlib |
| Verification | pytest, nbmake, Ruff, mypy |

## Limits

- **1 participant:** no classifier or diagnostic/population validation.
- **Clocks:** sensors/eyes naive; questionnaire UTC. Alignment unverified.
- **Measures:** gaze heuristic, interval samples; summary derivation missing.

## Sources and rights

**7 [reviews](docs/reviews)**; [corrections](NOTICE.md), [consent/privacy](DATA_ETHICS.md), [citation](CITATION.cff).

Code: [MIT](LICENSE). Authored data/docs: [CC BY 4.0](LICENSE-DATA). Instrument/media rights remain; instrument redistribution permission unestablished.

[Multimodal-Multisensor](https://github.com/urmeo/multimodal-multisensor) · [CalmSense](https://github.com/urmeo/calm-sense)
