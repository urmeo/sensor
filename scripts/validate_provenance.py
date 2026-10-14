"""Check recording coverage, source hashes and required metadata evidence files.

These checks do not establish device identity or calibration accuracy.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "data/RECORDING_PROVENANCE.json"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _evidence(
    metadata: dict[str, Any], label: str, root: Path, recording_id: str, resource: str
) -> None:
    references = metadata.get("evidence")
    if not isinstance(references, list) or not references:
        raise ValueError(f"{label}: evidence required")
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError(f"{label}: invalid evidence reference")
        path = reference.get("path", "")
        _require(bool(reference.get("description")), f"{label}: evidence description required")
        _require(bool(path) and (root / path).is_file(), f"{label}: evidence file missing")
        if metadata["status"] == "verified":
            _require(
                reference.get("recording_id") == recording_id
                and reference.get("resource") == resource
                and "reviews" not in Path(path).parts,
                f"{label}: verified claims need recording-specific evidence, not hardware reviews",
            )


def _metadata(stream: dict[str, Any], label: str, root: Path, recording_id: str) -> None:
    for name, fields in {
        "device": (
            "manufacturer",
            "model",
            "unit_id",
            "firmware",
            "configuration",
            "adapter",
            "acquisition_software",
            "acquisition_version",
        ),
        "calibration": (
            "procedure",
            "performed_at",
            "outcome",
            "report",
            "units",
            "coordinate_system",
        ),
        "aggregation": (
            "software",
            "version",
            "parameters",
            "source_data",
            "window",
            "baseline",
            "blink_rule",
            "quality_filter",
        ),
    }.items():
        metadata = stream.get(name)
        if not isinstance(metadata, dict):
            raise ValueError(f"{label}: {name} record required")
        _require(all(field in metadata for field in fields), f"{label}: incomplete {name} record")
        status = metadata.get("status")
        allowed = {"unknown", "verified", "not_applicable"}
        if name == "aggregation":
            allowed.add("reproduced")
        _require(status in allowed, f"{label}: invalid {name} status")
        _require(bool(metadata.get("notes")), f"{label}: {name} notes required")
        if status == "unknown":
            _require(
                all(metadata[field] is None for field in fields),
                f"{label}: unknown {name} must retain null values",
            )
        if status == "not_applicable":
            _require(stream["kind"] == "questionnaire", f"{label}: unsupported not_applicable")
        if status in {"verified", "reproduced"}:
            _evidence(metadata, f"{label}.{name}", root, recording_id, stream["resource"])
            required = {
                "device": ("manufacturer", "model", "unit_id", "configuration"),
                "calibration": ("procedure", "performed_at", "outcome", "report", "units"),
                "aggregation": ("software", "version", "parameters", "source_data"),
            }[name]
            _require(
                all(bool(metadata[field]) for field in required),
                f"{label}: {name} claim requires identifying details",
            )
    clock = stream.get("clock", {})
    _require(
        bool(clock.get("timestamp_fields"))
        and clock.get("timezone") in {"unspecified", "UTC"}
        and clock.get("synchronization_status") == "unknown"
        and bool(clock.get("notes")),
        f"{label}: explicit clock and synchronization metadata required",
    )


def validate_provenance(
    manifest: dict[str, Any], package: dict[str, Any], root: Path = ROOT
) -> None:
    """Require one recording assignment per source row and an explicit metadata state.

    A successful check establishes coverage and evidence-file availability only.
    Device identity, calibration accuracy, and scientific validity need separate review.
    """
    _require(manifest.get("schema_version") == 1, "unsupported provenance schema_version")
    _require(package.get("recordingProvenance") == MANIFEST, "package provenance link missing")
    sources = manifest.get("sources", {})
    resources = {resource["name"]: resource for resource in package["resources"]}
    _require(set(sources) == set(resources), "provenance source inventory differs from package")
    rows: dict[str, list[dict[str, str]]] = {}
    coverage: dict[str, set[int]] = {}
    assignments: dict[str, set[str]] = {name: set() for name in resources}
    for name, resource in resources.items():
        source = sources[name]
        _require(source.get("path") == resource["path"], f"{name}: source path differs")
        path = root / resource["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _require(source.get("sha256") == digest, f"{name}: source checksum differs")
        with path.open(newline="", encoding="utf-8") as handle:
            rows[name] = list(csv.DictReader(handle))
        _require(bool(rows[name]), f"{name}: source has no rows")
        coverage[name] = set()
    recordings = manifest.get("recordings", [])
    _require(bool(recordings), "recordings required")
    ids = [recording["id"] for recording in recordings]
    _require(len(ids) == len(set(ids)), "duplicate recording id")
    for recording in recordings:
        recording_id = recording["id"]
        _require(bool(recording.get("notes")), f"{recording_id}: recording notes required")
        _require(bool(recording.get("streams")), f"{recording_id}: streams required")
        source_date = recording.get("source_date")
        _require(
            isinstance(source_date, str)
            and date.fromisoformat(source_date).isoformat() == source_date,
            f"{recording_id}: ISO source_date required",
        )
        has_raw = any(stream.get("kind") == "raw_sensor" for stream in recording["streams"])
        _require(
            recording.get("raw_sensor_data_available") is has_raw,
            f"{recording_id}: raw sensor availability differs from streams",
        )
        for stream in recording["streams"]:
            name = stream["resource"]
            label = f"{recording_id}.{name}"
            _require(name in resources, f"{label}: undeclared source resource")
            _require(
                stream.get("kind") in {"raw_sensor", "legacy_derived", "summary", "questionnaire"},
                f"{label}: invalid stream kind",
            )
            _metadata(stream, label, root, recording_id)
            if stream["aggregation"]["status"] in {"verified", "reproduced"}:
                parents = stream["aggregation"]["source_data"]
                _require(
                    isinstance(parents, list)
                    and all(parent in resources and parent != name for parent in parents),
                    f"{label}: aggregation source_data must reference parent resources",
                )
            _require(
                stream["clock"]["timestamp_fields"] == resources[name]["timestampFields"]
                and stream["clock"]["timezone"] == resources[name]["timeZone"],
                f"{label}: clock metadata differs from package",
            )
            selector = stream.get("selector")
            if selector is not None:
                _require(
                    isinstance(selector, dict)
                    and bool(selector)
                    and all(column in rows[name][0] for column in selector),
                    f"{label}: invalid row selector",
                )
            selected = {
                index
                for index, row in enumerate(rows[name])
                if selector is None
                or all(row[column] == value for column, value in selector.items())
            }
            _require(bool(selected), f"{label}: selector has no source rows")
            _require(
                all(
                    rows[name][index][column][:10].replace("/", "-") == source_date
                    for index in selected
                    for column in resources[name]["timestampFields"]
                ),
                f"{label}: source_date differs from selected timestamp dates",
            )
            _require(not selected & coverage[name], f"{label}: source rows assigned more than once")
            coverage[name].update(selected)
            assignments[name].add(recording_id)
            channels = stream.get("channels")
            _require(isinstance(channels, list), f"{label}: channel inventory required")
            expected = (
                {int(rows[name][index]["iSensor"]) for index in selected}
                if "iSensor" in rows[name][0]
                else set()
            )
            actual = [channel.get("iSensor") for channel in channels]
            _require(
                len(actual) == len(set(actual)) and set(actual) == expected,
                f"{label}: channel inventory differs from source rows",
            )
            for channel in channels:
                mapping = channel.get("mapping_status")
                _require(mapping in {"unknown", "verified"}, f"{label}: invalid mapping status")
                if mapping == "unknown":
                    _require(channel.get("device_id") is None, f"{label}: unknown device mapping")
                else:
                    _require(
                        bool(channel.get("device_id"))
                        and channel["device_id"] == stream["device"]["unit_id"]
                        and stream["device"]["status"] == "verified",
                        f"{label}: verified channel needs verified device evidence",
                    )
    for name, resource in resources.items():
        _require(coverage[name] == set(range(len(rows[name]))), f"{name}: unassigned source rows")
        _require(
            set(resource.get("recordingIds", [])) == assignments[name],
            f"{name}: package recordingIds differ from manifest",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Source checkout directory")
    args = parser.parse_args()
    try:
        manifest = json.loads((args.root / MANIFEST).read_text(encoding="utf-8"))
        package = json.loads((args.root / "datapackage.json").read_text(encoding="utf-8"))
        validate_provenance(manifest, package, args.root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"provenance check failed: {error}\n")
    print("Recording coverage and source hashes match. Unknown metadata remains unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
