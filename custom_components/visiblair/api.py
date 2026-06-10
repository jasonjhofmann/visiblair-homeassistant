"""VisiblAir cloud REST client + response normalizer.

Wraps the single documented endpoint
``https://api.visiblair.com:11000/api/v1/sensor?uuid=…&viewToken=…`` and
turns its quirky raw payload into a typed :class:`VisiblAirSensorData`
dataclass that platforms can consume directly.

The defensive parsing rules implemented here are documented in
``docs/architecture.md``. Highlights:

* The server has an open catch-all that returns ``200 OK`` with
  ``Content-Length: 0`` for any URL that isn't an exact route match.
  Treat empty body as failure regardless of HTTP status.
* Responses are advertised as ``Content-Type: text/plain`` despite being
  JSON — parse as JSON anyway.
* The top-level payload duplicates a *subset* of sample fields as strings
  (e.g. ``lastSampleCo2: "523"``). Richer per-metric values, plus all the
  hardware-health booleans, live inside ``lastSampleDataRedis``, which
  is itself a JSON-encoded string (not a nested object).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiohttp import ClientSession

import aiohttp

from .const import API_BASE_URL, REQUIRED_RESPONSE_FIELDS

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=15)


class VisiblAirError(Exception):
    """Base for all VisiblAir API errors."""


class VisiblAirAuthError(VisiblAirError):
    """Raised when the API rejects credentials.

    The VisiblAir cloud API does not distinguish auth failure from
    "unknown sensor" or "missing parameters" — every error case returns
    the same empty-body 200. We surface all of these as auth failures
    since the only user-actionable response is to re-check the
    (MAC, viewToken) pair.
    """


class VisiblAirOfflineError(VisiblAirError):
    """Raised on transport-level failures (timeout, 5xx, connection error)."""


class VisiblAirParseError(VisiblAirError):
    """Raised when the API returns a body but it isn't a recognisable payload."""


@dataclass(frozen=True, slots=True)
class VisiblAirSensorData:
    """Normalised view of one VisiblAir sensor reading.

    Everything platforms need lives here. Optional fields (``| None``) are
    those that may legitimately be absent from a given device's payload
    (e.g. wind sensors are absent on the indoor Model E variant) — wire
    those up as ``None`` rather than zero so platforms can skip-or-mark-
    unavailable correctly.
    """

    # Identity
    uuid: str
    description: str
    model: str
    firmware_version: str

    # Timestamps
    last_sample_at: datetime
    last_calibration_at: datetime | None

    # Environmental gauges
    co2_ppm: int | None
    temperature_c: float | None
    humidity_pct: float | None
    voc_index: int | None
    pressure_hpa: float | None

    # Particulate matter (µg/m³)
    pm_0_1_um: float | None
    pm_0_3_um: float | None
    pm_0_5_um: float | None
    pm_1_0_um: float | None
    pm_2_5_um: float | None
    pm_4_0_um: float | None
    pm_5_0_um: float | None
    pm_10_0_um: float | None

    # Power
    battery_pct: float | None
    battery_voltage: float | None
    ac_connected: bool
    charging: bool

    # Hardware health
    pm_fan_fail: bool
    pm_laser_fail: bool
    pm_rht_error: bool
    pm_gas_sensor_error: bool
    pm_fan_cleaning: bool
    pm_fan_speed_warning: bool


class VisiblAirAPI:
    """Per-sensor API client.

    One instance per HA config entry. Reuses HA's shared aiohttp session
    rather than owning its own connector.
    """

    def __init__(
        self,
        session: ClientSession,
        uuid: str,
        view_token: str,
    ) -> None:
        self._session = session
        self._uuid = uuid
        self._view_token = view_token

    @property
    def uuid(self) -> str:
        return self._uuid

    async def fetch_latest(self) -> VisiblAirSensorData:
        """Hit the API and return a normalised reading.

        Raises:
            VisiblAirAuthError: empty body — credentials wrong, sensor
                unknown to the cloud, or required parameters missing.
            VisiblAirOfflineError: transport failure, 5xx response.
            VisiblAirParseError: body present but not recognisable as a
                sensor payload.
        """
        raw = await self._fetch_raw()
        return _normalise(raw)

    async def _fetch_raw(self) -> dict[str, Any]:
        params = {"uuid": self._uuid, "viewToken": self._view_token}
        try:
            async with self._session.get(
                API_BASE_URL, params=params, timeout=_TIMEOUT
            ) as resp:
                if resp.status >= 500:
                    raise VisiblAirOfflineError(
                        f"VisiblAir API returned HTTP {resp.status}"
                    )
                body = await resp.text()
        except TimeoutError as err:
            raise VisiblAirOfflineError("VisiblAir API timed out") from err
        except aiohttp.ClientError as err:
            raise VisiblAirOfflineError(
                f"VisiblAir API connection error: {err}"
            ) from err

        if not body:
            raise VisiblAirAuthError(
                "VisiblAir API returned empty body — check uuid/viewToken"
            )

        # Don't trust Content-Type (the API serves JSON as text/plain).
        try:
            data = json.loads(body)
        except json.JSONDecodeError as err:
            preview = body[:120].replace("\n", " ")
            raise VisiblAirParseError(
                f"VisiblAir response is not JSON: {preview!r}"
            ) from err

        if not isinstance(data, dict):
            raise VisiblAirParseError(
                f"VisiblAir response is not a JSON object: {type(data).__name__}"
            )

        missing = REQUIRED_RESPONSE_FIELDS - set(data)
        if missing:
            raise VisiblAirParseError(
                f"VisiblAir response missing required fields: {sorted(missing)}"
            )

        return data


# ---- normalisation ---------------------------------------------------------


def _normalise(raw: dict[str, Any]) -> VisiblAirSensorData:
    """Turn the raw API response into a :class:`VisiblAirSensorData`."""
    nested = _parse_nested(raw.get("lastSampleDataRedis"))

    return VisiblAirSensorData(
        uuid=str(raw["uuid"]),
        description=str(raw.get("description") or ""),
        model=str(nested.get("model") or raw.get("model") or ""),
        firmware_version=str(
            raw.get("firmwareVersion") or nested.get("firmwareVersion") or ""
        ),
        last_sample_at=_parse_iso8601(str(raw["lastSampleTimeStampRedis"])),
        last_calibration_at=_parse_naive_local(raw.get("lastCalibration")),
        co2_ppm=_as_int(raw.get("lastSampleCo2"))
        if raw.get("lastSampleCo2") is not None
        else _as_int(nested.get("co2")),
        temperature_c=_as_float(raw.get("lastSampleTemperature"))
        if raw.get("lastSampleTemperature") is not None
        else _as_float(nested.get("temperature")),
        humidity_pct=_as_float(raw.get("lastSampleHumidity"))
        if raw.get("lastSampleHumidity") is not None
        else _as_float(nested.get("humidity")),
        voc_index=_as_int(_nullable_field(raw.get("lastSampleVocIndex"), "Int64"))
        if isinstance(raw.get("lastSampleVocIndex"), dict)
        else _as_int(nested.get("voc")),
        pressure_hpa=_as_float(
            _nullable_field(raw.get("lastSamplePressure"), "Float64")
        )
        if isinstance(raw.get("lastSamplePressure"), dict)
        else _as_float(nested.get("P")),
        pm_0_1_um=_first_pm(raw, nested, "lastSamplePm01", "pm01"),
        pm_0_3_um=_first_pm(raw, nested, "lastSamplePm03", "pm03"),
        pm_0_5_um=_first_pm(raw, nested, "lastSamplePm05", "pm05"),
        pm_1_0_um=_first_pm(raw, nested, "lastSamplePm10", "pm10"),
        pm_2_5_um=_first_pm(raw, nested, "lastSamplePm25", "pm25"),
        pm_4_0_um=_first_pm(raw, nested, None, "pm40"),
        pm_5_0_um=_first_pm(raw, nested, "lastSamplePm50", "pm50"),
        pm_10_0_um=_first_pm(raw, nested, "lastSamplePm100", "pm100"),
        battery_pct=_as_float(_nullable_field(raw.get("lastSampleBattPct"), "Float64"))
        if isinstance(raw.get("lastSampleBattPct"), dict)
        else _as_float(nested.get("battPct")),
        battery_voltage=_as_float(
            _nullable_field(raw.get("lastSampleBattVoltage"), "Float64")
        )
        if isinstance(raw.get("lastSampleBattVoltage"), dict)
        else _as_float(nested.get("battVoltage")),
        ac_connected=bool(raw.get("lastSampleIsACIN", nested.get("isACIN", False))),
        charging=bool(raw.get("lastSampleIsCharging", nested.get("isCharging", False))),
        pm_fan_fail=bool(nested.get("PMFanFail", False)),
        pm_laser_fail=bool(nested.get("PMLaserFail", False)),
        pm_rht_error=bool(nested.get("PMRhtError", False)),
        pm_gas_sensor_error=bool(nested.get("PMGasSensorError", False)),
        pm_fan_cleaning=bool(nested.get("PMFanCleaning", False)),
        pm_fan_speed_warning=bool(nested.get("PMFanSpeedWarning", False)),
    )


def _parse_nested(value: Any) -> dict[str, Any]:
    """Decode ``lastSampleDataRedis`` — a JSON string, not a nested object."""
    if not isinstance(value, str) or not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        _LOGGER.debug("lastSampleDataRedis was not valid JSON; treating as empty")
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _nullable_field(blob: Any, key: str) -> Any:
    """Pull a value from a Go-style ``{"Float64": …, "Valid": bool}`` blob.

    The API wraps SQL-nullable numeric fields in this shape. When ``Valid``
    is false the value is meaningless — return ``None`` so downstream
    coercion produces a clean ``None`` rather than a misleading 0.
    """
    if not isinstance(blob, dict):
        return None
    if not blob.get("Valid", False):
        return None
    return blob.get(key)


def _first_pm(
    raw: dict[str, Any],
    nested: dict[str, Any],
    top_key: str | None,
    nested_key: str,
) -> float | None:
    """Prefer the top-level nullable-numeric for PM, fall back to nested."""
    if top_key and isinstance(raw.get(top_key), dict):
        value = _nullable_field(raw.get(top_key), "Float64")
        if value is not None:
            return _as_float(value)
    if nested_key in nested:
        return _as_float(nested.get(nested_key))
    return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except TypeError, ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _parse_iso8601(value: str) -> datetime:
    """Parse an RFC3339-ish timestamp; assume UTC if no offset.

    The API emits ``lastSampleTimeStampRedis`` as
    ``2026-05-26T20:50:29.032652926Z`` — nanosecond precision plus a ``Z``
    suffix. Python's :func:`datetime.fromisoformat` accepts ``Z`` natively
    from 3.11 onwards. We trim to microsecond precision (Python's max).
    """
    trimmed = _trim_subsecond_precision(value)
    parsed = datetime.fromisoformat(trimmed)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_naive_local(value: Any) -> datetime | None:
    """Parse the API's other timestamp form (``"2026-05-24 21:14:31"``).

    These naive strings are emitted in the sensor's local time zone; we
    have no offset to anchor them precisely without the device's ``tz``
    field. Returning naive UTC is the least-bad option — platforms get
    something orderable, with a known caveat. Phase 2 may revisit once
    the entity surface exposes timezone-aware diagnostic timestamps.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def _trim_subsecond_precision(value: str) -> str:
    """Truncate any sub-microsecond precision so fromisoformat accepts it."""
    if "." not in value:
        return value
    head, dot, tail = value.partition(".")
    # tail may end with Z or +HH:MM; preserve that suffix
    suffix = ""
    for marker in ("Z", "+", "-"):
        idx = tail.find(marker)
        if idx != -1:
            suffix = tail[idx:]
            tail = tail[:idx]
            break
    return f"{head}{dot}{tail[:6]}{suffix}"
