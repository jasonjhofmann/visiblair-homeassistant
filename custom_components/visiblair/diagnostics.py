"""Diagnostics platform — sanitised "Download diagnostics" snapshot.

Produces a JSON dump suitable for pasting into a GitHub issue. Includes:

* Config entry: title, data, options, unique_id, version (viewToken redacted)
* Coordinator: name, polling interval, last-update-success, last-error
* Latest reading: full :class:`~.api.VisiblAirSensorData` snapshot

Redacts:

* ``view_token`` — the per-sensor share token from the entry data
* The sensor MAC (``uuid``/``unique_id`` keys, plus its embedding in the
  coordinator name) — HA diagnostics guidance treats MAC addresses as
  data to redact.
* All hypothetical-future-payload keys that VisiblAir's raw API response
  exposes (latitude/longitude, email, MQTT credentials, delegate accounts,
  associatedUserID) — we never include the raw payload today, but the
  redact set documents what *would* need scrubbing if a future revision
  attaches it.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data

from .const import CONF_UUID, CONF_VIEW_TOKEN, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import VisiblAirConfigEntry


# Keys redacted at any depth in the diagnostics blob.
REDACT: set[str] = {
    # Entry-data keys
    CONF_VIEW_TOKEN,
    # The MAC address (HA diagnostics guidance: redact MACs). Covers
    # config_entry.data.uuid, config_entry.unique_id and
    # latest_reading.uuid; the coordinator name embeds the same MAC and
    # is scrubbed by string replacement below.
    CONF_UUID,
    "unique_id",
    # Raw-API-response keys we never include today but would need to scrub
    # if a future revision attaches the raw payload to the diagnostics dump.
    "viewToken",
    "latitude",
    "longitude",
    "email",
    "MQTTPassword",
    "MQTTUsername",
    "MQTTCert",
    "MQTTEndpoint",
    "MQTTTopic",
    "delegateAccounts",
    "delegatedAccounts",
    "associatedUserID",
}


def _serialise(obj: Any) -> Any:
    """JSON-safe representation for dataclasses + datetimes."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialise(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialise(v) for v in obj]
    return obj


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: VisiblAirConfigEntry,
) -> dict[str, Any]:
    """Return a sanitised diagnostics snapshot for this sensor."""
    coordinator = entry.runtime_data
    data = coordinator.data

    # The coordinator name is f"{DOMAIN}_{MAC}" — scrub the MAC while
    # keeping the surrounding structure visible for debugging.
    mac = str(entry.data.get(CONF_UUID, ""))
    coordinator_name = (
        coordinator.name.replace(mac, REDACTED) if mac else coordinator.name
    )

    payload: dict[str, Any] = {
        "integration_domain": DOMAIN,
        "config_entry": {
            "title": entry.title,
            "domain": entry.domain,
            "data": dict(entry.data),
            "options": dict(entry.options),
            "unique_id": entry.unique_id,
            "version": entry.version,
        },
        "coordinator": {
            "name": coordinator_name,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "last_update_success": coordinator.last_update_success,
            "last_exception_type": (
                type(coordinator.last_exception).__name__
                if coordinator.last_exception
                else None
            ),
        },
        "latest_reading": _serialise(data),
    }
    return async_redact_data(payload, REDACT)
