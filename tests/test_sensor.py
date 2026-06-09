"""Sensor platform tests — values, units, disabled-by-default, diagnostics."""

from __future__ import annotations

import pytest
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.visiblair.const import DOMAIN

from .conftest import state_for, uid

# Keys disabled by default (niche PM sizes + battery_voltage).
DISABLED_KEYS = {
    "pm_0_1",
    "pm_0_3",
    "pm_0_5",
    "pm_4_0",
    "pm_5_0",
    "battery_voltage",
}


async def test_sensor_values_and_units(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Core gauges surface with the expected value and unit."""
    cases = [
        ("co2", 523, "ppm"),
        ("temperature", 22.7, "°C"),
        ("humidity", 32.0, "%"),
        ("pm_2_5", 0.563, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
    ]
    for key, value, unit in cases:
        state = state_for(hass, "sensor", key)
        assert state is not None
        assert float(state.state) == pytest.approx(value)
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit


async def test_disabled_by_default(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Niche PM sizes + battery voltage are registered but disabled."""
    ent_reg = er.async_get(hass)
    for key in DISABLED_KEYS:
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid(key))
        assert entity_id is not None, key
        assert (
            ent_reg.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert hass.states.get(entity_id) is None


async def test_entity_counts(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """18 sensor entities registered; the 6 disabled ones have no state."""
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, init_integration.entry_id)
    sensors = [e for e in entries if e.domain == "sensor"]
    assert len(sensors) == 18
    enabled = [e for e in sensors if e.disabled_by is None]
    assert len(enabled) == 18 - len(DISABLED_KEYS)


async def test_firmware_is_diagnostic(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The firmware version sensor reports the version as a diagnostic."""
    state = state_for(hass, "sensor", "firmware_version")
    assert state is not None
    assert state.state == "1.7.2"

    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid("firmware_version"))
    assert ent_reg.async_get(entity_id).entity_category is EntityCategory.DIAGNOSTIC
