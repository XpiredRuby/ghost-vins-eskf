"""Versioned GHOST-X frame, timing, units, provenance, and schema helpers.

This module is deliberately ROS-independent so estimator libraries, offline
analysis, replay tools, and ROS adapters share one contract implementation.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft7Validator


CONTRACT_VERSION = "ghost-x-data-contract-v1"
SCHEMA_VERSION = 1
UNSPECIFIED_ID = "UNSPECIFIED"

SI_UNITS: dict[str, str] = {
    "position": "m",
    "velocity": "m/s",
    "acceleration": "m/s^2",
    "angle": "rad",
    "angular_rate": "rad/s",
    "covariance_position": "m^2",
    "covariance_velocity": "(m/s)^2",
    "time": "s",
    "latency": "s",
}

TIMESTAMP_SEMANTICS: dict[str, str] = {
    "source_time_s": "Sensor or simulator source timestamp in the active ROS clock domain.",
    "receipt_time_s": "Time the consumer callback received the measurement.",
    "processing_time_s": "Time estimator processing for the published sample completed.",
    "publication_time_s": "Time the output payload was published.",
}

VALIDITY_STATES = {
    "WAITING_FOR_TARGET",
    "VALID_TRACKING",
    "VALID_PREDICTION_ONLY",
    "DEGRADED",
    "INVALID",
    "MISSION_COMPLETE",
}


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes suitable for hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Return a prefixed SHA-256 identifier for a JSON-compatible value."""
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def artifact_sha256(path: str | os.PathLike[str] | None) -> str:
    """Hash a regular file, returning UNSPECIFIED for empty or missing paths.

    Missing calibration/configuration artifacts are explicit but nonfatal so
    software-only development remains possible without inventing provenance.
    Formal evidence acceptance can separately require a non-UNSPECIFIED value.
    """
    if path is None or str(path).strip() == "":
        return UNSPECIFIED_ID
    artifact = Path(path).expanduser()
    if not artifact.is_file():
        return UNSPECIFIED_ID
    digest = hashlib.sha256()
    with artifact.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def short_identifier(identifier: str, length: int = 12) -> str:
    """Return a human-readable short form without changing the stored ID."""
    if identifier == UNSPECIFIED_ID:
        return identifier
    value = identifier.split(":", 1)[-1]
    return value[: max(4, int(length))]


def build_run_identity(
    *,
    node_name: str,
    frame_id: str,
    configuration_label: str,
    configuration: Mapping[str, Any],
    calibration_artifact_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Build immutable provenance metadata from effective runtime settings."""
    normalized_configuration = {
        "node_name": str(node_name),
        "frame_id": str(frame_id),
        "configuration_label": str(configuration_label),
        "effective_configuration": dict(configuration),
    }
    return {
        "calibration_id": artifact_sha256(calibration_artifact_path),
        "configuration_id": canonical_sha256(normalized_configuration),
        "configuration_label": str(configuration_label),
    }


def build_timestamps(
    *,
    source_time_s: float | None,
    receipt_time_s: float | None,
    processing_time_s: float | None,
    publication_time_s: float | None,
) -> dict[str, float | None]:
    return {
        "source_time_s": _finite_or_none(source_time_s),
        "receipt_time_s": _finite_or_none(receipt_time_s),
        "processing_time_s": _finite_or_none(processing_time_s),
        "publication_time_s": _finite_or_none(publication_time_s),
    }


def build_validity(
    *,
    is_valid: bool,
    state: str,
    reason: str | None = None,
) -> dict[str, Any]:
    if state not in VALIDITY_STATES:
        raise ValueError(f"Unknown validity state: {state}")
    result: dict[str, Any] = {"is_valid": bool(is_valid), "state": state}
    if reason:
        result["reason"] = str(reason)
    return result


def contract_envelope(
    *,
    frame_id: str,
    provenance: Mapping[str, Any],
    timestamps: Mapping[str, Any],
    validity: Mapping[str, Any],
) -> dict[str, Any]:
    """Return fields shared by every versioned GHOST-X JSON payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "frame_id": str(frame_id),
        "units": dict(SI_UNITS),
        "provenance": dict(provenance),
        "timestamps": dict(timestamps),
        "validity": dict(validity),
    }


def default_schema_directory() -> Path:
    """Resolve source-tree or explicitly configured schema directory."""
    configured = os.environ.get("GHOST_X_SCHEMA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    # Source-tree layout: ghost_sim_ros2/ghost_sim_ros2/data_contract.py
    source_candidate = Path(__file__).resolve().parents[1] / "schemas"
    if source_candidate.is_dir():
        return source_candidate
    raise FileNotFoundError(
        "GHOST-X schema directory not found; set GHOST_X_SCHEMA_DIR to the installed share directory"
    )


def load_schema(schema_name: str, schema_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    directory = Path(schema_dir).expanduser() if schema_dir else default_schema_directory()
    path = directory / schema_name
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Schema must be a JSON object: {path}")
    Draft7Validator.check_schema(value)
    return value


def validate_payload(
    payload: Mapping[str, Any],
    schema_name: str,
    schema_dir: str | os.PathLike[str] | None = None,
) -> None:
    """Raise jsonschema.ValidationError when a payload violates its contract."""
    schema = load_schema(schema_name, schema_dir)
    Draft7Validator(schema).validate(dict(payload))


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number
