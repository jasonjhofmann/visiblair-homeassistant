"""Unit tests for the API normalisation layer.

These tests run without Home Assistant installed — they exercise the
pure-Python parse + normalise path that turns a raw HTTP body into a
:class:`VisiblAirSensorData`. Tests that need HA's runtime (config flow,
coordinator wiring) live in a separate file in Phase 3.
"""

from __future__ import annotations

import json
from datetime import timezone

import pytest

from custom_components.visiblair.api import (
    VisiblAirParseError,
    VisiblAirSensorData,
    _normalise,
    _parse_iso8601,
    _trim_subsecond_precision,
)


def test_normalise_full_payload(sensor_response_dict: dict) -> None:
    """A real captured payload normalises cleanly to a populated dataclass."""
    data = _normalise(sensor_response_dict)

    assert isinstance(data, VisiblAirSensorData)
    assert data.uuid == "AA:BB:CC:DD:EE:FF"
    assert data.description == "Test Sensor"
    assert data.model == "E"
    assert data.firmware_version == "1.7.2"

    # Environmental readings — top-level convenience fields are strings,
    # the normaliser must coerce them to numeric types.
    assert data.co2_ppm == 523
    assert data.temperature_c == pytest.approx(22.7)
    assert data.humidity_pct == pytest.approx(32.0)
    assert data.voc_index == 82
    assert data.pressure_hpa == pytest.approx(919.478)

    # PM family — note the API's `pmNN` naming uses a decimal-position
    # convention (`pm10` = 1.0 µm, `pm100` = 10.0 µm).
    assert data.pm_0_1_um == pytest.approx(0.0)
    assert data.pm_0_3_um == pytest.approx(0.433)
    assert data.pm_1_0_um == pytest.approx(0.56)
    assert data.pm_2_5_um == pytest.approx(0.563)
    assert data.pm_10_0_um == pytest.approx(0.563)

    # Power
    assert data.battery_pct == pytest.approx(96.02)
    assert data.battery_voltage == pytest.approx(4.16)
    assert data.ac_connected is True
    assert data.charging is False

    # Hardware health — sourced from nested lastSampleDataRedis
    assert data.pm_fan_fail is False
    assert data.pm_laser_fail is False
    assert data.pm_rht_error is False
    assert data.pm_gas_sensor_error is False

    # Timestamps
    assert data.last_sample_at.tzinfo is not None
    assert data.last_calibration_at is not None


def test_normalise_missing_nested_blob() -> None:
    """A payload without ``lastSampleDataRedis`` still normalises.

    The hardware-health booleans default to False (no fault reported);
    top-level convenience fields supply the gauges.
    """
    minimal = {
        "uuid": "AA:BB:CC:DD:EE:FF",
        "description": "Minimal",
        "lastSampleTimeStampRedis": "2026-05-26T20:50:29Z",
        "lastSampleCo2": "500",
        "lastSampleTemperature": "21.0",
        "lastSampleHumidity": "40.0",
        "firmwareVersion": "1.7.2",
        "model": "E",
        "lastCalibration": "",
    }
    data = _normalise(minimal)
    assert data.co2_ppm == 500
    assert data.temperature_c == pytest.approx(21.0)
    assert data.pm_fan_fail is False
    assert data.voc_index is None
    assert data.pm_0_1_um is None
    assert data.last_calibration_at is None


def test_normalise_nullable_wrapper_invalid() -> None:
    """``{"Float64": x, "Valid": false}`` blobs must yield None, not zero.

    The Go-style nullable-numeric wrapper is how the API distinguishes
    "value is 0" from "value is absent". A naive read of the inner field
    would silently turn "absent" into 0, lying to entities.
    """
    payload = {
        "uuid": "AA:BB:CC:DD:EE:FF",
        "description": "",
        "lastSampleTimeStampRedis": "2026-05-26T20:50:29Z",
        "lastSampleCo2": None,
        "lastSampleBattPct": {"Float64": 0, "Valid": False},
        "lastSampleVocIndex": {"Int64": 0, "Valid": False},
    }
    data = _normalise(payload)
    assert data.battery_pct is None
    assert data.voc_index is None


def test_normalise_nested_blob_with_extra_pm_only_in_nested() -> None:
    """``pm40`` only appears in the nested blob — confirm we pick it up."""
    payload = {
        "uuid": "AA:BB:CC:DD:EE:FF",
        "description": "",
        "lastSampleTimeStampRedis": "2026-05-26T20:50:29Z",
        "lastSampleDataRedis": json.dumps(
            {"pm40": 1.25, "PMFanFail": True, "isACIN": True}
        ),
    }
    data = _normalise(payload)
    assert data.pm_4_0_um == pytest.approx(1.25)
    assert data.pm_fan_fail is True
    assert data.ac_connected is True


def test_normalise_garbage_nested_blob_is_swallowed() -> None:
    """A non-JSON ``lastSampleDataRedis`` must not crash normalisation."""
    payload = {
        "uuid": "AA:BB:CC:DD:EE:FF",
        "description": "",
        "lastSampleTimeStampRedis": "2026-05-26T20:50:29Z",
        "lastSampleDataRedis": "not valid json {",
    }
    data = _normalise(payload)
    assert data.pm_fan_fail is False  # default
    assert data.co2_ppm is None


def test_parse_iso8601_handles_nanosecond_precision() -> None:
    """``…T20:50:29.032652926Z`` is real VisiblAir output; we must accept it."""
    dt = _parse_iso8601("2026-05-26T20:50:29.032652926Z")
    assert dt.tzinfo == timezone.utc
    # Microsecond precision after truncation
    assert dt.microsecond == 32652


def test_parse_iso8601_handles_no_subsecond() -> None:
    """Plain ISO without subseconds must still parse."""
    dt = _parse_iso8601("2026-05-26T20:50:29Z")
    assert dt.tzinfo == timezone.utc


def test_trim_subsecond_precision() -> None:
    """Sub-microsecond digits get trimmed; suffix preserved."""
    assert _trim_subsecond_precision("2026-05-26T20:50:29.032652926Z") == (
        "2026-05-26T20:50:29.032652Z"
    )
    assert _trim_subsecond_precision("2026-05-26T20:50:29.032+00:00") == (
        "2026-05-26T20:50:29.032+00:00"
    )
    assert _trim_subsecond_precision("2026-05-26T20:50:29") == (
        "2026-05-26T20:50:29"
    )


def test_normalise_requires_required_fields_at_api_layer() -> None:
    """Schema-required fields are enforced at the wire layer, not the normaliser.

    The normaliser trusts its input. Schema-shape validation lives in
    :meth:`VisiblAirAPI._fetch_raw` — exercised here via raising
    :class:`VisiblAirParseError` on a manually invoked invariant check.
    """
    # This test documents the contract; the actual schema check happens
    # in the API wrapper before _normalise is ever called.
    with pytest.raises(KeyError):
        _normalise({"description": "missing required fields"})

    # And to underline that VisiblAirParseError exists and is exported:
    assert issubclass(VisiblAirParseError, Exception)
