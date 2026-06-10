"""Setup / unload and coordinator error-path tests."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.visiblair.api import (
    VisiblAirAuthError,
    VisiblAirOfflineError,
    VisiblAirSensorData,
)
from custom_components.visiblair.const import API_BASE_URL, DOMAIN
from custom_components.visiblair.coordinator import AUTH_FAILURE_THRESHOLD

from .conftest import build_mock_api, patch_apis, setup_integration, state_for


def _reauth_flows(hass: HomeAssistant) -> list[dict]:
    return [
        f
        for f in hass.config_entries.flow.async_progress()
        if f["context"].get("source") == "reauth"
    ]


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A healthy setup loads, stores runtime data, then unloads cleanly."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_and_poll_logged_at_debug(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Setup and the first poll emit secret-safe debug lines."""
    with caplog.at_level(logging.DEBUG, logger="custom_components.visiblair"):
        await setup_integration(hass, mock_config_entry, mock_api)

    assert "Set up VisiblAir sensor" in caplog.text
    assert "Polled" in caplog.text
    # The viewToken must never appear in logs.
    assert "test-view-token" not in caplog.text


async def test_device_registered(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The sensor is registered as a device with a MAC connection."""
    device_reg = dr.async_get(hass)
    device = device_reg.async_get_device(identifiers={(DOMAIN, "AA:BB:CC:DD:EE:FF")})
    assert device is not None
    assert device.manufacturer == "VisiblAir"


async def test_setup_auth_failure_is_damped_then_triggers_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """One auth-classified failure at setup retries; the 3rd starts reauth.

    The API's catch-all answers any server-side anomaly with the same
    empty 200, so a single failure must not fire a reauth prompt. The
    consecutive-failure count persists across setup retries (it lives in
    hass.data), so a genuinely rotated token still reaches reauth.
    """
    api = build_mock_api(sample_data)
    api.fetch_latest.side_effect = VisiblAirAuthError("bad token")

    # First failed attempt: retry, no reauth prompt.
    await setup_integration(hass, mock_config_entry, api)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not _reauth_flows(hass)

    # Simulate the prior attempts having pushed the count to the threshold.
    hass.data[DOMAIN][mock_config_entry.entry_id] = AUTH_FAILURE_THRESHOLD - 1
    with patch_apis(api):
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


async def test_setup_api_error_is_retried(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """A transport error on first refresh leaves the entry in retry state."""
    api = build_mock_api(sample_data)
    api.fetch_latest.side_effect = VisiblAirOfflineError("timeout")

    await setup_integration(hass, mock_config_entry, api)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def _tick_one_poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_empty_body_damping_end_to_end(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    sensor_response_raw: str,
    freezer: FrozenDateTimeFactory,
) -> None:
    """1–2 empty 200s mark entities unavailable; the 3rd in a row reauths.

    Exercises the real API client against a mocked wire: the cloud's
    catch-all empty 200 must not fire an instant reauth prompt, a
    recovery must reset the damping counter, and only three consecutive
    failures escalate.
    """
    aioclient_mock.get(API_BASE_URL, text=sensor_response_raw)
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert state_for(hass, "sensor", "co2").state == "523"

    # The cloud hiccups: catch-all empty 200 on every poll.
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_BASE_URL, text="")

    for _ in range(AUTH_FAILURE_THRESHOLD - 1):
        await _tick_one_poll(hass, freezer)
        assert state_for(hass, "sensor", "co2").state == STATE_UNAVAILABLE
        assert not _reauth_flows(hass), "reauth fired before the threshold"

    # Recovery: a good response resets the counter and the entity.
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_BASE_URL, text=sensor_response_raw)
    await _tick_one_poll(hass, freezer)
    assert state_for(hass, "sensor", "co2").state == "523"
    assert not _reauth_flows(hass)

    # Three consecutive failures: the third escalates to reauth.
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_BASE_URL, text="")
    for _ in range(AUTH_FAILURE_THRESHOLD - 1):
        await _tick_one_poll(hass, freezer)
        assert not _reauth_flows(hass)
    await _tick_one_poll(hass, freezer)
    assert len(_reauth_flows(hass)) == 1


async def test_garbage_timestamp_does_not_crash_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    sensor_response_dict: dict,
) -> None:
    """A malformed required timestamp goes through the UpdateFailed path.

    Previously the raw ValueError escaped the coordinator's
    `except VisiblAirError` and crashed setup; now it must land in
    SETUP_RETRY like any other parse error.
    """
    sensor_response_dict["lastSampleTimeStampRedis"] = "not-a-timestamp"
    aioclient_mock.get(API_BASE_URL, text=json.dumps(sensor_response_dict))
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not _reauth_flows(hass)
