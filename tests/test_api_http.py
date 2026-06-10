"""Tests for the API client's HTTP layer + parse helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.visiblair.api import (
    VisiblAirAPI,
    VisiblAirAuthError,
    VisiblAirOfflineError,
    VisiblAirParseError,
    _as_float,
    _as_int,
    _nullable_field,
    _parse_iso8601,
    _parse_naive_local,
)
from custom_components.visiblair.const import API_BASE_URL


def _make_api(hass: HomeAssistant) -> VisiblAirAPI:
    return VisiblAirAPI(
        session=async_get_clientsession(hass),
        uuid="AA:BB:CC:DD:EE:FF",
        view_token="tok",
    )


async def test_fetch_success(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    sensor_response_raw: str,
) -> None:
    """A well-formed body is fetched and normalised."""
    aioclient_mock.get(API_BASE_URL, text=sensor_response_raw)
    api = _make_api(hass)
    assert api.uuid == "AA:BB:CC:DD:EE:FF"
    data = await api.fetch_latest()
    assert data.uuid == "AA:BB:CC:DD:EE:FF"
    assert data.co2_ppm == 523


async def test_fetch_server_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 5xx response is a transport failure."""
    aioclient_mock.get(API_BASE_URL, status=503)
    with pytest.raises(VisiblAirOfflineError):
        await _make_api(hass).fetch_latest()


@pytest.mark.parametrize("exc", [TimeoutError(), aiohttp.ClientError()])
async def test_fetch_transport_exceptions(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, exc: Exception
) -> None:
    """Timeouts and connection errors map to VisiblAirOfflineError."""
    aioclient_mock.get(API_BASE_URL, exc=exc)
    with pytest.raises(VisiblAirOfflineError):
        await _make_api(hass).fetch_latest()


async def test_fetch_empty_body_is_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An empty body means bad/unknown credentials."""
    aioclient_mock.get(API_BASE_URL, text="")
    with pytest.raises(VisiblAirAuthError):
        await _make_api(hass).fetch_latest()


@pytest.mark.parametrize(
    "body",
    [
        "<html>not json</html>",  # not JSON
        "[1, 2, 3]",  # JSON, but not an object
        '{"foo": 1}',  # object, but missing required fields
    ],
)
async def test_fetch_bad_payloads_are_parse_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, body: str
) -> None:
    """A non-payload body raises VisiblAirParseError."""
    aioclient_mock.get(API_BASE_URL, text=body)
    with pytest.raises(VisiblAirParseError):
        await _make_api(hass).fetch_latest()


@pytest.mark.parametrize("field", ["lastSampleTimeStampRedis", "lastCalibration"])
async def test_fetch_garbage_timestamp_is_parse_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    sensor_response_dict: dict,
    field: str,
) -> None:
    """A malformed timestamp anywhere in the payload surfaces as a parse error.

    Previously a raw ValueError escaped fetch_latest(), bypassing every
    `except VisiblAirError` handler in the coordinator and config flows.
    """
    sensor_response_dict[field] = "not-a-timestamp"
    aioclient_mock.get(API_BASE_URL, text=json.dumps(sensor_response_dict))
    with pytest.raises(VisiblAirParseError):
        await _make_api(hass).fetch_latest()


def test_as_int_edges() -> None:
    assert _as_int(None) is None
    assert _as_int("") is None
    assert _as_int("abc") is None
    assert _as_int("12.9") == 12


def test_as_float_edges() -> None:
    assert _as_float(None) is None
    assert _as_float("") is None
    assert _as_float("abc") is None
    assert _as_float("1.5") == 1.5


def test_nullable_field_edges() -> None:
    assert _nullable_field("not-a-dict", "Float64") is None
    assert _nullable_field({"Valid": False, "Float64": 1}, "Float64") is None
    assert _nullable_field({"Valid": True, "Float64": 2.0}, "Float64") == 2.0


def test_parse_naive_local_edges() -> None:
    assert _parse_naive_local(None) is None
    assert _parse_naive_local("") is None
    assert _parse_naive_local("2026-05-24 21:14:31") is not None


def test_parse_naive_local_garbage_raises_parse_error() -> None:
    """A present-but-malformed calibration timestamp is a parse error.

    It must surface as VisiblAirParseError (the VisiblAirError channel
    the coordinator and config flows already handle), never as a raw
    ValueError.
    """
    with pytest.raises(VisiblAirParseError) as exc:
        _parse_naive_local("not-a-date")
    assert "not-a-date" in str(exc.value)


def test_parse_naive_local_localises_with_payload_tz() -> None:
    """The payload `tz` anchors the naive local string to the true instant.

    2026-05-24 21:14:31 in America/Los_Angeles is PDT (UTC-7), i.e.
    2026-05-25T04:14:31Z.
    """
    parsed = _parse_naive_local("2026-05-24 21:14:31", "America/Los_Angeles")
    assert parsed is not None
    assert parsed == datetime(2026, 5, 25, 4, 14, 31, tzinfo=UTC)


@pytest.mark.parametrize("tz_name", [None, "", "Not/A_Zone", "../etc/passwd", 42])
def test_parse_naive_local_falls_back_to_utc(tz_name: object) -> None:
    """A missing or invalid `tz` falls back to the old stamp-as-UTC behavior."""
    parsed = _parse_naive_local("2026-05-24 21:14:31", tz_name)
    assert parsed == datetime(2026, 5, 24, 21, 14, 31, tzinfo=UTC)


def test_parse_iso8601_assumes_utc_without_offset() -> None:
    """A timestamp with no Z/offset is treated as UTC."""
    parsed = _parse_iso8601("2026-05-26T20:50:29")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_parse_iso8601_garbage_raises_parse_error() -> None:
    """A malformed required timestamp raises VisiblAirParseError, not ValueError.

    The offending value is included (truncated) for debuggability.
    """
    garbage = "garbage-timestamp" + "x" * 200
    with pytest.raises(VisiblAirParseError) as exc:
        _parse_iso8601(garbage)
    assert "garbage-timestamp" in str(exc.value)
    assert "x" * 100 not in str(exc.value)  # truncated
