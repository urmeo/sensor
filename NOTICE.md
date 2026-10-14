# Rights and historical review corrections

## License scope

| Material | Scope |
|---|---|
| Python, notebook code, tests | [MIT](LICENSE) |
| Original observations and authored documentation | [CC BY 4.0](LICENSE-DATA), where the author holds rights |
| Questionnaire wording and answer options | Instrument rights remain; open redistribution permission is unestablished |
| Product images and trademarks | Respective owners; [image credits](docs/images/CREDITS.md), excluded from the CC BY grant |

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) permits commercial copyright reuse. Privacy and personality rights remain separate. The author's stated consent covers research and education; see [data ethics](DATA_ETHICS.md). The repository grants no instrument permissions and implies no endorsement.

| Instrument | Attribution and permission source |
|---|---|
| HADS | R. P. Snaith and A. S. Zigmond, 1983/1992/1994; [GL Assessment](https://www.gl-assessment.co.uk/products/hospital-anxiety-depression-scale/) and [permissions](https://www.gl-assessment.co.uk/policies/permissions/) |
| STAI-S / STAI-T | Charles D. Spielberger, 1968/1977; Mind Garden; [instrument](https://www.mindgarden.com/145-state-trait-anxiety-inventory-for-adults) and [publication permissions](https://www.mindgarden.com/mind-garden-forms/63-publication-application.html) |
| BFI-10 | Oliver P. John / Berkeley Personality Lab; [research terms](https://www.ocf.berkeley.edu/~johnlab/bfi.html); Rammstedt and John (2007) |
| FQ | Isaac M. Marks; Marks and Mathews (1979). Confirm permission for the intended use. |

Questionnaire wording and recorded responses have separate rights. Preserve the source records, and avoid republishing instrument wording in examples, wheels or derived outputs. Citation and deposit metadata describe these rights; they do not establish a Zenodo deposit or DOI.

## Historical documents

The seven original PDFs in [docs/reviews](docs/reviews/) are unchanged historical reviews and protocol drafts. They do not define current software behavior or provide validation results. The corrections below were checked against primary documentation on 6–7 October 2026.

| Source document | Correction |
|---|---|
| [Threshold](<docs/reviews/Threshold.pdf>) | Fixation, HRV, SCR and facial-movement proposals lack anxiety-classifier validation. Later README additions of 500 deg/s and 3.0/FACS C were absent from the original threshold table. |
| [Sensor Documentation](<docs/reviews/Sensor Documentation.pdf>) | HW401/E4/AXIS specifications and FaceReader method/accuracy need the model-specific corrections below. The added protocol phases total 35 min, not 30. |
| [Sensors overview](<docs/reviews/Sensors (Eye-tracking, HRV, GSR, Camera).pdf>) | HW401 is optical PPG; separate world video from eye sampling. Reviewed hardware does not establish CSV channel provenance. |
| [OpenFace vs Noldus](<docs/reviews/OpenFace vs Noldus.pdf>) | AU output and expression benchmarks are version-specific. Support speed and superiority were not measured. |
| [Sensor Comparison](<docs/reviews/Sensor Comparison.pdf>) | Compare matching models/modalities; categorical rate/reliability claims are unsupported. Prose/bibliography years conflict: Alrefaei 2019/2023, Gualniera 2019/2021, Rosler 2021/2020. The Erdi autobiographical thesis does not establish hardware reliability. Unlinked ANOVA and “To do” material are draft content. |
| [Experiment Scenario](<docs/reviews/Experiment Scenario.pdf>) | 10 min interview + 5 min setup + 15 min testing totals 30 min before baseline/debrief. The shipped raw recording spans about 535 s. |
| [List of Sensors](<docs/reviews/List of Sensors.pdf>) | Earlier list has 10 devices; consolidated review has 11, including HW401. Review coverage is separate from acquired channels. |

## Supported corrections

| Topic | Primary-source correction |
|---|---|
| HW401 | Optical PPG armband, rechargeable battery rated 25+ h. Historical ECG, CR2032/800 h, processor and R-R capability claims are unsupported. [Moofit](https://moo.fit/products/moofit-heart-rate-monitor-armband) |
| OpenFace | Supports AU23 lip tightening; AU24 lip pressing is absent from its output list. Intensity output spans 0–5; it supplies no validated anxiety cutoff. [AUs](https://github.com/TadasBaltrusaitis/OpenFace/wiki/Action-Units), [FACS names](https://www.cs.cmu.edu/~face/facs.htm) |
| E4 | Original retired E4: manufacturer comparison lists battery life up to 36 h. Historical 48/60 h claims are unsupported here. [Empatica](https://www.empatica.com/research/e4/) |
| AXIS P1275 | Original model: 1920×1080, maximum 25/30 fps, not 60 fps. [Model support](https://www.axis.com/en-gb/products/axis-p1275/support) |
| Pupil Core / SMI | World-camera frames and eye/gaze sampling are different quantities. Rates depend on model/configuration; no catalog option identifies the acquired CSV configuration. Generic SMI “60 Hz” needs a model qualifier. [Pupil documentation](https://docs.pupil-labs.com/core/getting-started/) |
| FaceReader | Version 10 describes deep-network face modeling; six basic expressions plus neutral. Manufacturer ADFES/WSEFEP expression accuracy: FR10 98.7%/97.2%; FR9 99.3%/95.7%. These do not measure anxiety detection in this sample. [Version 10 methods](https://noldus.com/shared/resources/book/noldus-product-documentation/chapter/facereader/page/facereader-10-how-does-facereader-work) |

## Measurement limits

- Literature on [pupillometry](https://doi.org/10.1177/1745691611427305), [arousal and saccades](https://doi.org/10.1016/j.neubiorev.2013.03.011), [task-specific velocity thresholds](https://pubmed.ncbi.nlm.nih.gov/21287116/) and [HRV measurement](https://doi.org/10.1161/01.CIR.93.5.1043) does not validate the historical anxiety rules on this one-person sample.
- Device mappings, calibration and clock synchronization between streams are unknown. Summary aggregation, baseline intervals and blink rules are undocumented. Reverse-keying and aggregate scoring of stored item codes are unverified.
- The analysis describes observations and historical low-movement runs. Repeated interval samples do not establish beat-level HRV. Response times and supplied flags do not establish psychological states.

## Recording provenance

[RECORDING_PROVENANCE.json](data/RECORDING_PROVENANCE.json) records the SHA-256 hash, session, row selector and observed channels for all six CSVs. Device identity and configuration, adapter and software versions, calibration, clock synchronization and aggregation rules are marked unknown where evidence is missing.

`iSensor` is local to each resource. Matching channel numbers across files do not establish a shared physical device. The historical “Smart Eye Data” name and the hardware reviews do not identify the acquired device either.

Session 1 includes raw streams, responses, supplied eye summaries and a historical derived file. Sessions 2–3 include supplied summaries only; their raw acquisition files are absent. Summary-to-raw linkage is unknown for all three sessions. `sed_fix` is a reproducible transformation of `sed`, not a separate acquisition. Reproducing it does not recover the original software environment or validate fixation events.

For each new recording, retain:

- The acquisition log, channel-to-unit mapping, device model, identifier, firmware and configuration, and adapter and software versions.
- The calibration procedure, date, outcome and report, plus coordinate units and reference frame.
- Clock settings and synchronization evidence.
- Aggregation source files, code version, parameters, windows, quality rules, baselines and blink definitions.

Mark unavailable information `unknown`, with null values and a reason. Use `not_applicable` only when a measurement does not apply, such as sensor calibration for questionnaire responses. A `verified` claim needs identifying details and recording-specific evidence. Catalog specifications and generic reviews are insufficient.

Run `python -m scripts.validate_provenance` to check source hashes, complete and nonoverlapping row/session coverage, channel coverage, metadata states and evidence references. This checks that evidence is available and consistent. It does not establish device identity or calibration accuracy, and a successful check leaves historical unknowns unverified.
