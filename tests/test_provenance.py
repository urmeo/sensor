"""Check historical inventory and reject lost lineage or unsupported metadata claims."""

import copy
import json
from pathlib import Path

import pytest

from scripts.validate_provenance import validate_provenance

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = json.loads((ROOT / "datapackage.json").read_text())
MANIFEST = json.loads((ROOT / PACKAGE["recordingProvenance"]).read_text())


@pytest.fixture
def manifest():
    return copy.deepcopy(MANIFEST)


@pytest.fixture
def manifest_with_verified_channel(manifest, tmp_path):
    """Exercise metadata linkage with synthetic evidence, not real device facts."""
    evidence = tmp_path / "synthetic-device-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "recording_id": "session-1",
                "resource": "hr",
                "unit_id": "synthetic-unit",
                "notes": "Synthetic test fixture only; no actual recording device is identified.",
            }
        ),
        encoding="utf-8",
    )
    stream = manifest["recordings"][0]["streams"][0]
    stream["device"].update(
        status="verified",
        manufacturer="synthetic-manufacturer",
        model="synthetic-model",
        unit_id="synthetic-unit",
        configuration={"mode": "synthetic-test"},
        evidence=[
            {
                "path": str(evidence),
                "description": "Synthetic recording-bound evidence for metadata contract tests.",
                "recording_id": "session-1",
                "resource": "hr",
            }
        ],
        notes="Synthetic test metadata; historical recording devices remain unknown.",
    )
    stream["channels"][0].update(mapping_status="verified", device_id="synthetic-unit")
    return manifest


def test_provenance_covers_all_recordings_rows_and_channels():
    validate_provenance(MANIFEST, PACKAGE, ROOT)


def test_historical_unknowns_are_explicit_and_summary_lineage_is_unverified():
    for recording in MANIFEST["recordings"]:
        for stream in recording["streams"]:
            assert stream["device"]["status"] == "unknown"
            assert all(channel["device_id"] is None for channel in stream["channels"])
            assert stream["clock"]["synchronization_status"] == "unknown"
            if stream["resource"] == "eye_metrics":
                assert stream["aggregation"]["status"] == "unknown"
                assert stream["aggregation"]["source_data"] is None
                assert stream["calibration"]["status"] == "unknown"
    assert [r["raw_sensor_data_available"] for r in MANIFEST["recordings"]] == [True, False, False]


def test_legacy_derived_stream_retains_explicit_sed_parent():
    stream = next(s for s in MANIFEST["recordings"][0]["streams"] if s["resource"] == "sed_fix")
    aggregation = stream["aggregation"]
    assert stream["kind"] == "legacy_derived"
    assert aggregation["status"] == "reproduced"
    assert aggregation["source_data"] == ["sed"]
    assert aggregation["parameters"]["gaze_displacement_threshold"] == 0.01


@pytest.mark.parametrize("resource", list(PACKAGE["resources"]))
def test_missing_source_inventory_is_rejected(manifest, resource):
    del manifest["sources"][resource["name"]]
    with pytest.raises(ValueError, match="inventory differs"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_missing_summary_recording_is_rejected(manifest):
    manifest["recordings"].pop()
    with pytest.raises(ValueError, match="unassigned source rows"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_duplicate_summary_selector_is_rejected(manifest):
    manifest["recordings"][2]["streams"][0]["selector"] = {"Test": "Test 02"}
    manifest["recordings"][2]["source_date"] = "2024-06-20"
    with pytest.raises(ValueError, match="assigned more than once"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_nonexistent_summary_selector_is_rejected(manifest):
    manifest["recordings"][2]["streams"][0]["selector"] = {"Test": "Test 99"}
    with pytest.raises(ValueError, match="no source rows"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_missing_channel_is_rejected(manifest):
    manifest["recordings"][0]["streams"][0]["channels"].pop()
    with pytest.raises(ValueError, match="channel inventory differs"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_source_checksum_drift_is_rejected(manifest):
    manifest["sources"]["sed"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum differs"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_unknown_device_cannot_silently_gain_a_model(manifest):
    manifest["recordings"][0]["streams"][0]["device"]["model"] = "reviewed model"
    with pytest.raises(ValueError, match="unknown device must retain null"):
        validate_provenance(manifest, PACKAGE, ROOT)


@pytest.mark.parametrize("metadata", ["device", "calibration", "aggregation"])
def test_verified_claim_requires_evidence(manifest, metadata):
    manifest["recordings"][0]["streams"][0][metadata]["status"] = "verified"
    with pytest.raises(ValueError, match="evidence required"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_hardware_review_cannot_support_a_verified_mapping(manifest):
    device = manifest["recordings"][0]["streams"][0]["device"]
    device["status"] = "verified"
    device["evidence"] = [
        {
            "path": "docs/reviews/Sensor Documentation.pdf",
            "description": "Hardware review only",
            "recording_id": "session-1",
            "resource": "hr",
        }
    ]
    with pytest.raises(ValueError, match="recording-specific evidence"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_verified_evidence_must_identify_the_recording(manifest):
    device = manifest["recordings"][0]["streams"][0]["device"]
    device["status"] = "verified"
    device["evidence"] = [{"path": "NOTICE.md", "description": "General notice only"}]
    with pytest.raises(ValueError, match="recording-specific evidence"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_channel_cannot_claim_verified_device_without_device_evidence(manifest):
    channel = manifest["recordings"][0]["streams"][0]["channels"][0]
    channel.update(mapping_status="verified", device_id="unsubstantiated-device")
    with pytest.raises(ValueError, match="verified channel needs verified device evidence"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_verified_channel_accepts_matching_recording_bound_device(manifest_with_verified_channel):
    validate_provenance(manifest_with_verified_channel, PACKAGE, ROOT)


def test_verified_channel_cannot_reference_a_different_unit(manifest_with_verified_channel):
    channel = manifest_with_verified_channel["recordings"][0]["streams"][0]["channels"][0]
    channel["device_id"] = "another-synthetic-unit"
    with pytest.raises(ValueError, match="verified channel needs verified device evidence"):
        validate_provenance(manifest_with_verified_channel, PACKAGE, ROOT)


def test_sensor_calibration_cannot_be_marked_not_applicable(manifest):
    manifest["recordings"][0]["streams"][0]["calibration"]["status"] = "not_applicable"
    with pytest.raises(ValueError, match="unsupported not_applicable"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_package_recording_references_cannot_drift():
    package = copy.deepcopy(PACKAGE)
    package["resources"][0]["recordingIds"] = ["session-2"]
    with pytest.raises(ValueError, match="recordingIds differ"):
        validate_provenance(MANIFEST, package, ROOT)


@pytest.mark.parametrize(
    ("field", "value"), [("timezone", "UTC"), ("timestamp_fields", ["wrong_field"])]
)
def test_clock_metadata_cannot_drift_from_the_source_contract(manifest, field, value):
    manifest["recordings"][0]["streams"][0]["clock"][field] = value
    with pytest.raises(ValueError, match="clock metadata differs"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_recording_date_must_match_its_selected_rows(manifest):
    manifest["recordings"][1]["source_date"] = "2024-06-24"
    with pytest.raises(ValueError, match="source_date differs"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_raw_availability_cannot_claim_absent_acquisitions(manifest):
    manifest["recordings"][1]["raw_sensor_data_available"] = True
    with pytest.raises(ValueError, match="raw sensor availability differs"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_reproduced_aggregation_must_reference_declared_parent_sources(manifest):
    derived = next(s for s in manifest["recordings"][0]["streams"] if s["resource"] == "sed_fix")
    derived["aggregation"]["source_data"] = ["unavailable-acquisition"]
    with pytest.raises(ValueError, match="reference parent resources"):
        validate_provenance(manifest, PACKAGE, ROOT)


def test_recording_bound_evidence_still_requires_device_identifying_details(manifest):
    device = manifest["recordings"][0]["streams"][0]["device"]
    device["status"] = "verified"
    device["evidence"] = [
        {
            "path": "NOTICE.md",
            "description": "Synthetic evidence association; identity remains missing",
            "recording_id": "session-1",
            "resource": "hr",
        }
    ]
    with pytest.raises(ValueError, match="device claim requires identifying details"):
        validate_provenance(manifest, PACKAGE, ROOT)
