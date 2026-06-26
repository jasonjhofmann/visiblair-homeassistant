"""Freshness-gate tests — stale (frozen) readings go unavailable.

After a VisiblAir sensor powers off, the cloud keeps serving the last
cached reading on every poll: the fetch succeeds (``last_update_success``
stays ``True``) but ``lastSampleTimeStampRedis`` is frozen. Without a
freshness gate the entities stay available with a stale value, and
downstream consumers assume the frozen reading is current. These tests
prove the gate flips live measurements to ``unavailable`` once a reading
ages past ``STALE_AFTER`` while the last-sample timestamp diagnostic
stays visible so the staleness is legible.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.visiblair.api import VisiblAirSensorData
from custom_components.visiblair.const import STALE_AFTER
from custom_components.visiblair.coordinator import VisiblAirCoordinator

from .conftest import build_mock_api, state_for

# Live measurements that must go unavailable once the reading is stale.
GATED_SENSOR_KEYS = ("co2", "temperature", "humidity", "pm_2_5", "battery")
# Diagnostics that intentionally survive staleness (static metadata + the
# staleness indicator itself).
EXEMPT_SENSOR_KEYS = ("firmware_version", "last_sample", "last_calibration")


async def _age_past_stale(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Advance the clock past STALE_AFTER and let one more poll land."""
    freezer.tick(STALE_AFTER + timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_fresh_reading_is_available(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A just-sampled reading surfaces normally — the gate is open."""
    state = state_for(hass, "sensor", "co2")
    assert state is not None
    assert state.state == "523"


async def test_stale_measurements_go_unavailable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Live gauges go unavailable once the cached reading ages out.

    The cloud keeps returning the same (frozen-timestamp) payload, so the
    poll keeps succeeding — only the freshness gate makes the entity drop.
    """
    assert state_for(hass, "sensor", "co2").state == "523"

    await _age_past_stale(hass, freezer)

    for key in GATED_SENSOR_KEYS:
        assert state_for(hass, "sensor", key).state == STATE_UNAVAILABLE, key


async def test_stale_binary_sensors_go_unavailable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Power/health flags stop reporting a frozen value once stale.

    This is the in-car case from the bug report: a parked, powered-off
    sensor must not keep reporting *AC connected* / *Charging*.
    """
    assert state_for(hass, "binary_sensor", "ac_connected").state == "on"

    await _age_past_stale(hass, freezer)

    for key in ("ac_connected", "charging", "pm_fan_fail"):
        assert state_for(hass, "binary_sensor", key).state == STATE_UNAVAILABLE, key


async def test_exempt_diagnostics_survive_staleness(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The last-sample timestamp (and static metadata) stay visible.

    The whole point of the gate is that the user can still see *when* the
    device last reported — gating that timestamp on freshness would hide
    the one value that explains why everything else went unavailable.
    """
    await _age_past_stale(hass, freezer)

    for key in EXEMPT_SENSOR_KEYS:
        state = state_for(hass, "sensor", key)
        assert state is not None, key
        assert state.state != STATE_UNAVAILABLE, key

    # And the last-sample diagnostic still reads the original sample time.
    assert state_for(hass, "sensor", "firmware_version").state == "1.7.2"


async def test_data_is_fresh_property(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Unit-check the coordinator's freshness boundary at STALE_AFTER."""
    mock_config_entry.add_to_hass(hass)
    coordinator = VisiblAirCoordinator(
        hass, mock_config_entry, api=build_mock_api(sample_data)
    )
    await coordinator.async_refresh()

    assert coordinator.data_is_fresh is True

    # Just inside the window — still fresh.
    freezer.tick(STALE_AFTER - timedelta(seconds=5))
    assert coordinator.data_is_fresh is True

    # Tip over the edge — now stale.
    freezer.tick(timedelta(seconds=10))
    assert coordinator.data_is_fresh is False


async def test_recovery_clears_staleness(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_api: object,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A device coming back online (fresh timestamp) restores availability."""
    await _age_past_stale(hass, freezer)
    assert state_for(hass, "sensor", "co2").state == STATE_UNAVAILABLE

    # The device powers back on: next poll carries a current sample time.
    fresh = dataclasses.replace(
        init_integration.runtime_data.data, last_sample_at=dt_util.utcnow()
    )
    mock_api.fetch_latest.return_value = fresh  # type: ignore[attr-defined]
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert state_for(hass, "sensor", "co2").state == "523"
