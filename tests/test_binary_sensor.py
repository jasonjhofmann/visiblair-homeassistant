"""Binary-sensor platform tests."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.visiblair.api import _normalise
from custom_components.visiblair.const import CONF_UUID, CONF_VIEW_TOKEN, DOMAIN

from .conftest import TEST_VIEW_TOKEN, build_mock_api, setup_integration, state_for


async def test_binary_sensor_states(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Power + health flags reflect the fixture reading."""
    assert state_for(hass, "binary_sensor", "ac_connected").state == STATE_ON
    assert state_for(hass, "binary_sensor", "charging").state == STATE_OFF
    assert state_for(hass, "binary_sensor", "pm_fan_fail").state == STATE_OFF


async def test_flags_unavailable_when_unreported(
    hass: HomeAssistant, sensor_response_dict: dict
) -> None:
    """Health/power flags go unavailable — not off — when unreported.

    With ``lastSampleDataRedis`` (and the top-level power keys) absent
    from the payload, all eight flags are unreported (None). Reporting
    ``off`` would mask a real fault as "no fault"; *unavailable* (rather
    than unknown) is deliberate — the backing data feed is missing,
    which is HA's unavailable semantic.
    """
    stripped = dict(sensor_response_dict)
    del stripped["lastSampleDataRedis"]
    del stripped["lastSampleIsACIN"]
    del stripped["lastSampleIsCharging"]
    data = _normalise(stripped)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=data.description,
        data={CONF_UUID: data.uuid, CONF_VIEW_TOKEN: TEST_VIEW_TOKEN},
        unique_id=data.uuid,
    )
    await setup_integration(hass, entry, build_mock_api(data))

    for key in (
        "ac_connected",
        "charging",
        "pm_fan_fail",
        "pm_laser_fail",
        "pm_rht_error",
        "pm_gas_sensor_error",
        "pm_fan_cleaning",
        "pm_fan_speed_warning",
    ):
        state = state_for(hass, "binary_sensor", key)
        assert state is not None, key
        assert state.state == STATE_UNAVAILABLE, key


async def test_binary_sensor_count(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """All eight binary sensors are registered."""
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, init_integration.entry_id)
    binary = [e for e in entries if e.domain == "binary_sensor"]
    assert len(binary) == 8
