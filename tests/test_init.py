"""Setup / unload and coordinator error-path tests."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.visiblair.api import (
    VisiblAirAuthError,
    VisiblAirOfflineError,
    VisiblAirSensorData,
)
from custom_components.visiblair.const import DOMAIN

from .conftest import build_mock_api, setup_integration


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


async def test_setup_auth_failure_triggers_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """A rejected token on first refresh fails setup and starts reauth."""
    api = build_mock_api(sample_data)
    api.fetch_latest.side_effect = VisiblAirAuthError("bad token")

    await setup_integration(hass, mock_config_entry, api)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    reauth = [
        f
        for f in hass.config_entries.flow.async_progress()
        if f["context"].get("source") == "reauth"
    ]
    assert len(reauth) == 1


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
