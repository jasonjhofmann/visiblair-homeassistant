"""Coordinator tests — exception translation keys for auth/update failures."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.visiblair.api import (
    VisiblAirAuthError,
    VisiblAirOfflineError,
    VisiblAirSensorData,
)
from custom_components.visiblair.const import DOMAIN
from custom_components.visiblair.coordinator import VisiblAirCoordinator

from .conftest import build_mock_api


async def test_auth_error_is_translated(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """A rejected token raises ConfigEntryAuthFailed with a translation key."""
    mock_config_entry.add_to_hass(hass)
    api = build_mock_api(sample_data)
    api.fetch_latest.side_effect = VisiblAirAuthError("nope")
    coordinator = VisiblAirCoordinator(hass, mock_config_entry, api=api)

    with pytest.raises(ConfigEntryAuthFailed) as exc:
        await coordinator._async_update_data()

    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "auth_failed"


async def test_update_error_is_translated(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """Transport errors raise UpdateFailed with a translation key + detail."""
    mock_config_entry.add_to_hass(hass)
    api = build_mock_api(sample_data)
    api.fetch_latest.side_effect = VisiblAirOfflineError("timed out")
    coordinator = VisiblAirCoordinator(hass, mock_config_entry, api=api)

    with pytest.raises(UpdateFailed) as exc:
        await coordinator._async_update_data()

    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "update_failed"
    assert exc.value.translation_placeholders == {"error": "timed out"}
