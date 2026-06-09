"""Binary-sensor platform tests."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import state_for


async def test_binary_sensor_states(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Power + health flags reflect the fixture reading."""
    assert state_for(hass, "binary_sensor", "ac_connected").state == STATE_ON
    assert state_for(hass, "binary_sensor", "charging").state == STATE_OFF
    assert state_for(hass, "binary_sensor", "pm_fan_fail").state == STATE_OFF


async def test_binary_sensor_count(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """All eight binary sensors are registered."""
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, init_integration.entry_id)
    binary = [e for e in entries if e.domain == "binary_sensor"]
    assert len(binary) == 8
