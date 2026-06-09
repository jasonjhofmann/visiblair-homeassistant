"""Shared pytest fixtures for the VisiblAir test suite."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.visiblair.api import VisiblAirSensorData, _normalise
from custom_components.visiblair.const import CONF_UUID, CONF_VIEW_TOKEN, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"

TEST_VIEW_TOKEN = "test-view-token-abcdef"
TEST_UUID = "AA:BB:CC:DD:EE:FF"


def uid(key: str) -> str:
    """The unique_id the integration builds for an entity key."""
    return f"{DOMAIN}_{TEST_UUID}_{key}"


def state_for(hass: HomeAssistant, platform: str, key: str) -> State | None:
    """Resolve an entity's state by its description key."""
    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id(platform, DOMAIN, uid(key))
    assert entity_id, f"no entity registered for key {key!r}"
    return hass.states.get(entity_id)


@pytest.fixture
def sensor_response_raw() -> str:
    """The captured (and credential-redacted) live API payload, as a string.

    Tests should parse this with the same defensive parser the integration
    uses — exercising end-to-end means hitting both the JSON parse step
    *and* the nested ``lastSampleDataRedis`` decode.
    """
    return (FIXTURES / "sensor_response.json").read_text()


@pytest.fixture
def sensor_response_dict(sensor_response_raw: str) -> dict[str, Any]:
    """The same payload parsed to a Python dict."""
    return json.loads(sensor_response_raw)


# --- Home Assistant harness fixtures ---------------------------------------


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make HA load the integration from ``custom_components/`` in every test."""


@pytest.fixture
def sample_data(sensor_response_dict: dict[str, Any]) -> VisiblAirSensorData:
    """A normalised reading built from the synthetic fixture payload."""
    return _normalise(sensor_response_dict)


def build_mock_api(data: VisiblAirSensorData) -> MagicMock:
    """A MagicMock standing in for ``VisiblAirAPI`` with an async fetch."""
    api = MagicMock()
    api.uuid = data.uuid
    api.fetch_latest = AsyncMock(return_value=data)
    return api


@pytest.fixture
def mock_api(sample_data: VisiblAirSensorData) -> MagicMock:
    """A healthy default API returning the sample reading."""
    return build_mock_api(sample_data)


@pytest.fixture
def mock_config_entry(sample_data: VisiblAirSensorData) -> MockConfigEntry:
    """A config entry whose unique_id matches the sample sensor's MAC."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=sample_data.description,
        data={CONF_UUID: sample_data.uuid, CONF_VIEW_TOKEN: TEST_VIEW_TOKEN},
        unique_id=sample_data.uuid,
    )


@contextmanager
def patch_apis(api: MagicMock) -> Iterator[MagicMock]:
    """Patch ``VisiblAirAPI`` in both the entry-setup and config-flow paths."""
    with (
        patch("custom_components.visiblair.VisiblAirAPI", return_value=api),
        patch("custom_components.visiblair.config_flow.VisiblAirAPI", return_value=api),
    ):
        yield api


async def setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry, api: MagicMock
) -> None:
    """Add the entry and run setup with the API patched in both call sites."""
    entry.add_to_hass(hass)
    with patch_apis(api):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
) -> MockConfigEntry:
    """Set up the integration with the healthy default API and return the entry."""
    await setup_integration(hass, mock_config_entry, mock_api)
    return mock_config_entry
