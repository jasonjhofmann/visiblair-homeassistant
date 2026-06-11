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
import re
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from aiohttp import ClientSession

import aiohttp

from .const import API_BASE_URL, REQUIRED_RESPONSE_FIELDS

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Excerpts of non-JSON error bodies are embedded in VisiblAirParseError
# messages, which flow into UpdateFailed placeholders and config-flow
# WARNING logs. A captive portal / proxy that echoes the request URL back
# in its error page would put the viewToken in that excerpt — scrub both
# the configured token and any generic ``viewToken=…`` query pattern.
_TOKEN_QUERY_RE = re.compile(r"(viewToken=)[^&\s'\"<>]+", re.IGNORECASE)
_REDACTED = "**REDACTED**"


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

    # Power state and hardware health are tri-state: ``None`` means the
    # payload didn't report the flag at all (the ``lastSampleDataRedis``
    # blob that carries it was missing or unparseable). Defaulting these
    # to False would silently mask a real fault as "no fault" — platforms
    # mark the corresponding entities unavailable on None instead.

    # Power
    battery_pct: float | None
    battery_voltage: float | None
    ac_connected: bool | None
    charging: bool | None

    # Hardware health
    pm_fan_fail: bool | None
    pm_laser_fail: bool | None
    pm_rht_error: bool | None
    pm_gas_sensor_error: bool | None
    pm_fan_cleaning: bool | None
    pm_fan_speed_warning: bool | None


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
            # Redact BEFORE truncating so a token straddling the cut
            # can't partially survive (README: "viewToken is never
            # logged at any level" — this excerpt reaches logs).
            preview = self._redact_token(body).replace("\n", " ")[:120]
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

    def _redact_token(self, text: str) -> str:
        """Scrub the viewToken from server-controlled text before embedding.

        Covers the configured token verbatim plus any ``viewToken=…``
        query pattern (case-insensitive), so even a token we did not
        send — e.g. echoed by an intermediary — can't reach the logs.
        """
        if self._view_token:
            text = text.replace(self._view_token, _REDACTED)
        return _TOKEN_QUERY_RE.sub(rf"\1{_REDACTED}", text)


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
        last_calibration_at=_parse_naive_local(
            raw.get("lastCalibration"), raw.get("tz")
        ),
        # Top-level gauges are strings on the wire; an empty string
        # parses to None, so the nested fallback must be consulted
        # whenever the top-level value PARSES to nothing — not only
        # when the raw key is absent (see _first_int).
        co2_ppm=_first_int(raw.get("lastSampleCo2"), nested.get("co2")),
        temperature_c=_first_float(
            raw.get("lastSampleTemperature"), nested.get("temperature")
        ),
        humidity_pct=_first_float(
            raw.get("lastSampleHumidity"), nested.get("humidity")
        ),
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
        # Tri-state flags: an unreported flag stays None (entity goes
        # unavailable) rather than masquerading as False / "no fault".
        ac_connected=_as_bool(raw.get("lastSampleIsACIN", nested.get("isACIN"))),
        charging=_as_bool(raw.get("lastSampleIsCharging", nested.get("isCharging"))),
        pm_fan_fail=_as_bool(nested.get("PMFanFail")),
        pm_laser_fail=_as_bool(nested.get("PMLaserFail")),
        pm_rht_error=_as_bool(nested.get("PMRhtError")),
        pm_gas_sensor_error=_as_bool(nested.get("PMGasSensorError")),
        pm_fan_cleaning=_as_bool(nested.get("PMFanCleaning")),
        pm_fan_speed_warning=_as_bool(nested.get("PMFanSpeedWarning")),
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


def _first_int(*values: Any) -> int | None:
    """First value that *parses* to an int — not the first non-None raw value.

    The top-level convenience gauges arrive as strings; an empty string
    parses to None, so gating the nested fallback on the raw key being
    None would ignore a perfectly valid nested value and leave the
    entity unknown despite data being present.
    """
    for value in values:
        parsed = _as_int(value)
        if parsed is not None:
            return parsed
    return None


def _first_float(*values: Any) -> float | None:
    """Float twin of :func:`_first_int`."""
    for value in values:
        parsed = _as_float(value)
        if parsed is not None:
            return parsed
    return None


def _as_bool(value: Any) -> bool | None:
    """Coerce to bool, preserving None as "flag not reported".

    Distinguishes "device reported no fault" (False) from "the blob
    carrying this flag is missing" (None). Defaulting to False here
    would silently report OK while the hardware could be faulting.
    """
    if value is None:
        return None
    return bool(value)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso8601(value: str) -> datetime:
    """Parse an RFC3339-ish timestamp; assume UTC if no offset.

    The API emits ``lastSampleTimeStampRedis`` as
    ``2026-05-26T20:50:29.032652926Z`` — nanosecond precision plus a ``Z``
    suffix. Python's :func:`datetime.fromisoformat` accepts ``Z`` natively
    from 3.11 onwards. We trim to microsecond precision (Python's max).

    Raises:
        VisiblAirParseError: the value is not a parseable timestamp.
            Wrapped here so garbage from the wire surfaces through the
            normal ``VisiblAirError`` channel instead of escaping as a
            raw ``ValueError``.
    """
    trimmed = _trim_subsecond_precision(value)
    try:
        parsed = datetime.fromisoformat(trimmed)
    except ValueError as err:
        raise VisiblAirParseError(
            f"VisiblAir timestamp is not parseable: {value[:64]!r}"
        ) from err
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_naive_local(value: Any, tz_name: Any = None) -> datetime | None:
    """Parse the API's other timestamp form (``"2026-05-24 21:14:31"``).

    These naive strings are emitted in the sensor's local time zone. The
    payload carries that zone in its ``tz`` field (an IANA name such as
    ``America/Los_Angeles``), so we localise against it to recover the
    true instant. Only when ``tz`` is missing or not a valid IANA name do
    we fall back to stamping the naive string as UTC — orderable, but
    offset by the device's UTC offset.

    Raises:
        VisiblAirParseError: the value is present but not a parseable
            timestamp. Absent/empty values return ``None`` instead —
            ``lastCalibration`` is legitimately empty on never-calibrated
            devices.
    """
    if not isinstance(value, str) or not value:
        return None
    zone: tzinfo = UTC
    if isinstance(tz_name, str) and tz_name:
        try:
            zone = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            _LOGGER.debug(
                "Device tz %r is not a valid IANA zone; assuming UTC", tz_name
            )
    try:
        return datetime.fromisoformat(value).replace(tzinfo=zone)
    except ValueError as err:
        raise VisiblAirParseError(
            f"VisiblAir calibration timestamp is not parseable: {value[:64]!r}"
        ) from err


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
