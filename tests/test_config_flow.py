"""Config / reauth / reconfigure flow tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.visiblair.api import (
    VisiblAirAuthError,
    VisiblAirOfflineError,
    VisiblAirParseError,
)
from custom_components.visiblair.const import (
    API_BASE_URL,
    CONF_UUID,
    CONF_VIEW_TOKEN,
    DOMAIN,
)

from .conftest import TEST_VIEW_TOKEN, patch_apis

MAC_INPUT = "aa:bb:cc:dd:ee:ff"
MAC_CANON = "AA:BB:CC:DD:EE:FF"


async def test_user_flow_success(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """A valid MAC + token creates an entry titled from the device description."""
    with patch_apis(mock_api):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_UUID: f"  {MAC_INPUT}  ", CONF_VIEW_TOKEN: "tok-123"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Sensor"
    assert result["data"] == {CONF_UUID: MAC_CANON, CONF_VIEW_TOKEN: "tok-123"}


async def test_user_flow_invalid_mac(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """A malformed MAC is rejected before any API call."""
    with patch_apis(mock_api):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_UUID: "not-a-mac", CONF_VIEW_TOKEN: "tok"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_UUID: "invalid_mac"}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (VisiblAirAuthError("bad"), "invalid_auth"),
        (VisiblAirOfflineError("down"), "cannot_connect"),
        (VisiblAirParseError("garbage"), "cannot_connect"),
    ],
)
async def test_user_flow_validation_errors(
    hass: HomeAssistant, mock_api: MagicMock, error: Exception, expected: str
) -> None:
    """API failures during validation surface as base errors."""
    mock_api.fetch_latest.side_effect = error
    with patch_apis(mock_api):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_UUID: MAC_INPUT, CONF_VIEW_TOKEN: "tok"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_user_flow_garbage_timestamp_is_cannot_connect(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    sensor_response_dict: dict,
) -> None:
    """A malformed wire timestamp shows cannot_connect, not "Unknown error".

    Exercises the real API client end-to-end: the ValueError from
    datetime.fromisoformat must be wrapped into VisiblAirParseError so
    the flow's `except VisiblAirParseError` handler catches it.
    """
    sensor_response_dict["lastSampleTimeStampRedis"] = "not-a-timestamp"
    aioclient_mock.get(API_BASE_URL, text=json.dumps(sensor_response_dict))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_UUID: MAC_INPUT, CONF_VIEW_TOKEN: "tok"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_aborts_on_duplicate(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
) -> None:
    """Re-adding the same MAC aborts as already_configured."""
    mock_config_entry.add_to_hass(hass)
    with patch_apis(mock_api):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_UUID: MAC_INPUT, CONF_VIEW_TOKEN: "tok"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
) -> None:
    """Reauth updates the stored viewToken and reloads."""
    mock_config_entry.add_to_hass(hass)
    with patch_apis(mock_api):
        result = await mock_config_entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_VIEW_TOKEN: "fresh-token"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_VIEW_TOKEN] == "fresh-token"


async def test_reconfigure_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
) -> None:
    """Reconfigure swaps in a new viewToken without re-adding the sensor."""
    mock_config_entry.add_to_hass(hass)
    with patch_apis(mock_api):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_VIEW_TOKEN: "rotated-token"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_VIEW_TOKEN] == "rotated-token"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (VisiblAirAuthError("bad"), "invalid_auth"),
        (VisiblAirOfflineError("down"), "cannot_connect"),
        (VisiblAirParseError("garbage"), "cannot_connect"),
    ],
)
async def test_reauth_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
    error: Exception,
    expected: str,
) -> None:
    """A failed reauth re-shows the form with the right error."""
    mock_config_entry.add_to_hass(hass)
    mock_api.fetch_latest.side_effect = error
    with patch_apis(mock_api):
        result = await mock_config_entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_VIEW_TOKEN: "x"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert mock_config_entry.data[CONF_VIEW_TOKEN] == TEST_VIEW_TOKEN


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (VisiblAirAuthError("bad"), "invalid_auth"),
        (VisiblAirOfflineError("down"), "cannot_connect"),
        (VisiblAirParseError("garbage"), "cannot_connect"),
    ],
)
async def test_reconfigure_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
    error: Exception,
    expected: str,
) -> None:
    """A failed reconfigure re-shows the form, leaving the token unchanged."""
    mock_config_entry.add_to_hass(hass)
    mock_api.fetch_latest.side_effect = error
    with patch_apis(mock_api):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_VIEW_TOKEN: "x"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert mock_config_entry.data[CONF_VIEW_TOKEN] == TEST_VIEW_TOKEN
