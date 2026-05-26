"""Smoke tests for the entity-description tables.

These tests confirm that:

* every description's ``value_fn`` runs against a real captured payload
  without raising,
* the description-key set covers every entity-worthy
  :class:`~custom_components.visiblair.api.VisiblAirSensorData` field
  (and fields surfaced via ``DeviceInfo`` are explicitly listed so an
  accidental orphan stands out),
* a few canonical metric values match what the live fixture says.

The wired-up entity classes themselves are exercised only enough to
confirm the description plumbing works — full entity-registry / state-
machine tests live in Phase 3 alongside config-flow tests, both of
which need ``pytest-homeassistant-custom-component``.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime

import pytest

from custom_components.visiblair.api import VisiblAirSensorData, _normalise
from custom_components.visiblair.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
from custom_components.visiblair.sensor import SENSOR_DESCRIPTIONS


# Authoritative wiring map. Adding a field to VisiblAirSensorData *must*
# show up here too — the test below fails closed if you forget.
DATACLASS_FIELD_TO_ENTITY_KEY: dict[str, str | None] = {
    # Surfaced via DeviceInfo (device tile), not as standalone entities.
    "uuid": None,
    "description": None,
    "model": None,
    # Surfaced as sensor entities.
    "firmware_version": "firmware_version",
    "last_sample_at": "last_sample",
    "last_calibration_at": "last_calibration",
    "co2_ppm": "co2",
    "temperature_c": "temperature",
    "humidity_pct": "humidity",
    "voc_index": "voc_index",
    "pressure_hpa": "pressure",
    "pm_0_1_um": "pm_0_1",
    "pm_0_3_um": "pm_0_3",
    "pm_0_5_um": "pm_0_5",
    "pm_1_0_um": "pm_1_0",
    "pm_2_5_um": "pm_2_5",
    "pm_4_0_um": "pm_4_0",
    "pm_5_0_um": "pm_5_0",
    "pm_10_0_um": "pm_10_0",
    "battery_pct": "battery",
    "battery_voltage": "battery_voltage",
    # Surfaced as binary sensors.
    "ac_connected": "ac_connected",
    "charging": "charging",
    "pm_fan_fail": "pm_fan_fail",
    "pm_laser_fail": "pm_laser_fail",
    "pm_rht_error": "pm_rht_error",
    "pm_gas_sensor_error": "pm_gas_sensor_error",
    "pm_fan_cleaning": "pm_fan_cleaning",
    "pm_fan_speed_warning": "pm_fan_speed_warning",
}


def test_dataclass_wiring_map_is_complete() -> None:
    """Every VisiblAirSensorData field must appear in the wiring map."""
    actual = {f.name for f in fields(VisiblAirSensorData)}
    declared = set(DATACLASS_FIELD_TO_ENTITY_KEY)
    missing = actual - declared
    extra = declared - actual
    assert not missing, (
        f"Dataclass fields not declared in DATACLASS_FIELD_TO_ENTITY_KEY: "
        f"{sorted(missing)}. Add them with an entity key or None."
    )
    assert not extra, (
        f"DATACLASS_FIELD_TO_ENTITY_KEY references removed dataclass fields: "
        f"{sorted(extra)}."
    )


def test_every_entity_key_has_a_description() -> None:
    """Every non-None entity key in the wiring map must have a description."""
    sensor_keys = {d.key for d in SENSOR_DESCRIPTIONS}
    binary_keys = {d.key for d in BINARY_SENSOR_DESCRIPTIONS}
    all_keys = sensor_keys | binary_keys
    declared_entity_keys = {
        k for k in DATACLASS_FIELD_TO_ENTITY_KEY.values() if k is not None
    }
    missing = declared_entity_keys - all_keys
    assert not missing, (
        f"Wiring map declares entity keys with no matching description: "
        f"{sorted(missing)}"
    )


def test_no_duplicate_keys_across_platforms() -> None:
    """Sensor and binary-sensor keys must not collide.

    The unique_id format is ``visiblair_{uuid}_{key}`` — collisions across
    platforms would produce duplicate unique_ids.
    """
    sensor_keys = {d.key for d in SENSOR_DESCRIPTIONS}
    binary_keys = {d.key for d in BINARY_SENSOR_DESCRIPTIONS}
    collisions = sensor_keys & binary_keys
    assert not collisions, f"Keys appear on both platforms: {sorted(collisions)}"


def test_sensor_value_fns_against_fixture(sensor_response_dict: dict) -> None:
    """Each sensor value_fn must run cleanly and return a sensible type."""
    data = _normalise(sensor_response_dict)
    for desc in SENSOR_DESCRIPTIONS:
        value = desc.value_fn(data)
        # Acceptable types for a sensor's native_value
        assert value is None or isinstance(value, (int, float, str, datetime)), (
            f"{desc.key} returned unexpected type {type(value).__name__}: {value!r}"
        )


def test_binary_sensor_value_fns_against_fixture(sensor_response_dict: dict) -> None:
    """Every binary-sensor value_fn must return a bool."""
    data = _normalise(sensor_response_dict)
    for desc in BINARY_SENSOR_DESCRIPTIONS:
        value = desc.value_fn(data)
        assert isinstance(value, bool), (
            f"{desc.key} returned {type(value).__name__} ({value!r}), expected bool"
        )


def test_canonical_values_from_fixture(sensor_response_dict: dict) -> None:
    """Spot-check a few entities against known captured values."""
    data = _normalise(sensor_response_dict)
    by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}

    assert by_key["co2"].value_fn(data) == 523
    assert by_key["temperature"].value_fn(data) == pytest.approx(22.7)
    assert by_key["humidity"].value_fn(data) == pytest.approx(32.0)
    assert by_key["voc_index"].value_fn(data) == 82
    assert by_key["battery"].value_fn(data) == pytest.approx(96.02)
    assert by_key["battery_voltage"].value_fn(data) == pytest.approx(4.16)
    assert by_key["firmware_version"].value_fn(data) == "1.7.2"

    by_bkey = {d.key: d for d in BINARY_SENSOR_DESCRIPTIONS}
    assert by_bkey["ac_connected"].value_fn(data) is True
    assert by_bkey["charging"].value_fn(data) is False
    assert by_bkey["pm_fan_fail"].value_fn(data) is False
    assert by_bkey["pm_laser_fail"].value_fn(data) is False
