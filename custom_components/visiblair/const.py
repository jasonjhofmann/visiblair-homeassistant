"""Constants for the VisiblAir integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "visiblair"
MANUFACTURER: Final = "VisiblAir"
DEFAULT_NAME: Final = "VisiblAir Sensor"

CONF_UUID: Final = "uuid"
CONF_VIEW_TOKEN: Final = "view_token"

# VisiblAir sensors emit a new sample on a configurable on-device interval
# (default 60 s). Polling faster than the sensor's own sample rate yields no
# new data; the default is matched to the factory sample rate. Not
# user-configurable per HA Core conventions (the integration owns its cadence).
DEFAULT_SCAN_INTERVAL_SECONDS: Final = 60
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)

# Cloud API base URL — see docs/architecture.md. Note the non-standard port
# 11000 and that this is the *entire* documented surface for this API.
API_BASE_URL: Final = "https://api.visiblair.com:11000/api/v1/sensor"

# A response is only "data" if it contains these fields. The API's open
# catch-all returns `200 OK` + empty body on any unrecognised route, so
# field presence — not HTTP status — is the authoritative signal.
REQUIRED_RESPONSE_FIELDS: Final = frozenset({"uuid", "lastSampleTimeStampRedis"})
