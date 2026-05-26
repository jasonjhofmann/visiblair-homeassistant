"""Tests for the diagnostics platform — primarily that redaction works."""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.visiblair.api import _normalise
from custom_components.visiblair.const import CONF_UUID, CONF_VIEW_TOKEN
from custom_components.visiblair.diagnostics import (
    REDACT,
    async_get_config_entry_diagnostics,
)


def _build_fake_entry(coordinator: SimpleNamespace) -> SimpleNamespace:
    """Build a minimum config-entry stand-in that the diagnostics handler accepts."""
    entry = SimpleNamespace(
        title="Test VisiblAir Sensor",
        domain="visiblair",
        data={
            CONF_UUID: "AA:BB:CC:DD:EE:FF",
            CONF_VIEW_TOKEN: "supersecret",
        },
        options={"scan_interval": 60},
        unique_id="AA:BB:CC:DD:EE:FF",
        version=1,
        runtime_data=coordinator,
    )
    return entry


def _build_fake_coordinator(data: object) -> SimpleNamespace:
    return SimpleNamespace(
        name="visiblair_AA:BB:CC:DD:EE:FF",
        update_interval=timedelta(seconds=60),
        last_update_success=True,
        last_exception=None,
        data=data,
    )


async def test_view_token_is_redacted(sensor_response_dict: dict) -> None:
    """The user-pasted viewToken in entry.data must not survive the dump."""
    data = _normalise(sensor_response_dict)
    coordinator = _build_fake_coordinator(data)
    entry = _build_fake_entry(coordinator)

    result = await async_get_config_entry_diagnostics(MagicMock(), entry)
    blob = json.dumps(result)

    assert "supersecret" not in blob, "Raw viewToken leaked into diagnostics output"
    assert result["config_entry"]["data"][CONF_VIEW_TOKEN] == "**REDACTED**"


async def test_uuid_and_other_metadata_survive(sensor_response_dict: dict) -> None:
    """Non-sensitive metadata (uuid, model, firmware, readings) must round-trip."""
    data = _normalise(sensor_response_dict)
    coordinator = _build_fake_coordinator(data)
    entry = _build_fake_entry(coordinator)

    result = await async_get_config_entry_diagnostics(MagicMock(), entry)

    assert result["config_entry"]["data"][CONF_UUID] == "AA:BB:CC:DD:EE:FF"
    assert result["coordinator"]["update_interval_seconds"] == 60
    assert result["coordinator"]["last_update_success"] is True
    # The dataclass round-tripped: a known fixture value should still be there.
    assert result["latest_reading"]["co2_ppm"] == 523
    assert result["latest_reading"]["firmware_version"] == "1.7.2"


def test_redact_set_includes_all_documented_keys() -> None:
    """Lock the redact set against silent drift.

    The architecture doc enumerates which raw-API fields must be scrubbed
    if they ever appear in diagnostics output. This test fails loudly if
    any are missing from REDACT.
    """
    must_redact = {
        "view_token",
        "viewToken",
        "latitude",
        "longitude",
        "email",
        "MQTTPassword",
        "MQTTUsername",
        "MQTTCert",
        "delegateAccounts",
        "delegatedAccounts",
        "associatedUserID",
    }
    missing = must_redact - REDACT
    assert not missing, f"REDACT is missing documented keys: {sorted(missing)}"
