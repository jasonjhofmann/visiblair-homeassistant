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
from custom_components.visiblair.coordinator import (
    AUTH_FAILURE_THRESHOLD,
    VisiblAirCoordinator,
)

from .conftest import build_mock_api


async def test_auth_error_is_damped_then_translated(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """Auth-classified failures escalate to reauth only on the 3rd in a row.

    The API's catch-all returns the same empty 200 for any server-side
    anomaly, so the first two failures must surface as plain UpdateFailed;
    the third consecutive one raises ConfigEntryAuthFailed with the
    translation key.
    """
    mock_config_entry.add_to_hass(hass)
    api = build_mock_api(sample_data)
    api.fetch_latest.side_effect = VisiblAirAuthError("nope")
    coordinator = VisiblAirCoordinator(hass, mock_config_entry, api=api)

    for _ in range(AUTH_FAILURE_THRESHOLD - 1):
        with pytest.raises(UpdateFailed) as update_exc:
            await coordinator._async_update_data()
        assert update_exc.value.translation_key == "update_failed"

    with pytest.raises(ConfigEntryAuthFailed) as exc:
        await coordinator._async_update_data()

    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "auth_failed"


async def test_auth_failure_counter_resets_on_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """A successful poll between auth failures resets the damping counter."""
    mock_config_entry.add_to_hass(hass)
    api = build_mock_api(sample_data)
    coordinator = VisiblAirCoordinator(hass, mock_config_entry, api=api)

    # Two failures — one short of the threshold…
    api.fetch_latest.side_effect = VisiblAirAuthError("nope")
    for _ in range(AUTH_FAILURE_THRESHOLD - 1):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    # …then a recovery resets the counter…
    api.fetch_latest.side_effect = None
    assert await coordinator._async_update_data() == sample_data

    # …so the next two failures are still damped, not escalated.
    api.fetch_latest.side_effect = VisiblAirAuthError("nope")
    for _ in range(AUTH_FAILURE_THRESHOLD - 1):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


async def test_auth_failure_counter_survives_coordinator_rebuild(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    sample_data: VisiblAirSensorData,
) -> None:
    """The counter persists across coordinator instances (setup retries).

    Each SETUP_RETRY attempt builds a fresh coordinator; a genuinely
    rotated token must still reach the reauth prompt after the third
    failed attempt rather than retrying forever.
    """
    mock_config_entry.add_to_hass(hass)

    for _ in range(AUTH_FAILURE_THRESHOLD - 1):
        api = build_mock_api(sample_data)
        api.fetch_latest.side_effect = VisiblAirAuthError("nope")
        coordinator = VisiblAirCoordinator(hass, mock_config_entry, api=api)
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    api = build_mock_api(sample_data)
    api.fetch_latest.side_effect = VisiblAirAuthError("nope")
    coordinator = VisiblAirCoordinator(hass, mock_config_entry, api=api)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


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
