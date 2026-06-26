"""DataUpdateCoordinator — one per VisiblAir sensor / config entry."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    VisiblAirAPI,
    VisiblAirAuthError,
    VisiblAirError,
    VisiblAirSensorData,
)
from .const import CONF_UUID, DEFAULT_SCAN_INTERVAL, DOMAIN, STALE_AFTER

_LOGGER = logging.getLogger(__name__)

# The API's open catch-all answers ANY server-side anomaly with the same
# empty-body 200 that signals bad credentials, so a single auth-classified
# failure is weak evidence. Require this many CONSECUTIVE failures before
# escalating to ConfigEntryAuthFailed (which halts polling and prompts the
# user to reauthenticate); anything fewer is surfaced as a normal
# UpdateFailed so a transient cloud hiccup just marks entities unavailable
# for a poll or two.
AUTH_FAILURE_THRESHOLD: Final = 3


class VisiblAirCoordinator(DataUpdateCoordinator[VisiblAirSensorData]):
    """Polls a single VisiblAir sensor on a fixed cadence."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        api: VisiblAirAPI,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{api.uuid}",
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self._api = api
        self._entry_id = entry.entry_id
        # Canonical (uppercase) sensor MAC, sourced from the config entry —
        # never from the cloud response. Entity unique_ids derive from this
        # so a cloud-side casing change can't orphan registered entities.
        # entry.unique_id and entry.data[CONF_UUID] hold the same
        # canonicalised value; the data key covers the (theoretical)
        # unique_id-less entry for type narrowing.
        self.canonical_uuid: str = entry.unique_id or entry.data[CONF_UUID]

    @property
    def data_is_fresh(self) -> bool:
        """Whether the latest reading is recent enough to trust.

        After a sensor powers off the cloud keeps returning the last
        cached sample on every poll — the fetch succeeds and
        ``last_update_success`` stays ``True`` while
        ``lastSampleTimeStampRedis`` is frozen — so success alone can't
        distinguish a live device from a dead one. Measurement entities
        gate their availability on this so a stale reading goes
        ``unavailable`` instead of masquerading as current. The
        last-sample-timestamp diagnostic deliberately ignores this gate
        so the user can still see *how* stale the data is.

        Read only by entities, which exist only after the first
        successful refresh has populated ``self.data`` — so, as
        elsewhere in this integration, the reading is taken as present.
        """
        return dt_util.utcnow() - self.data.last_sample_at < STALE_AFTER

    @property
    def _auth_failure_store(self) -> dict[str, int]:
        """Consecutive-auth-failure counts, keyed by config entry id.

        Lives in ``hass.data`` rather than on the coordinator instance so
        the count survives setup retries (each retry builds a fresh
        coordinator) — a genuinely rotated token still reaches the reauth
        prompt after AUTH_FAILURE_THRESHOLD failed setup attempts.
        """
        store: dict[str, int] = self.hass.data.setdefault(DOMAIN, {})
        return store

    async def _async_update_data(self) -> VisiblAirSensorData:
        """Fetch one reading; map API exceptions onto HA's coordinator errors."""
        entry_id = self._entry_id
        try:
            data = await self._api.fetch_latest()
        except VisiblAirAuthError as err:
            failures = self._auth_failure_store.get(entry_id, 0) + 1
            self._auth_failure_store[entry_id] = failures
            if failures >= AUTH_FAILURE_THRESHOLD:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                ) from err
            _LOGGER.debug(
                "Auth-classified failure %d/%d for %s — treating as transient",
                failures,
                AUTH_FAILURE_THRESHOLD,
                self._api.uuid,
            )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        except VisiblAirError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        self._auth_failure_store.pop(entry_id, None)

        _LOGGER.debug(
            "Polled %s: CO2=%s ppm, PM2.5=%s µg/m³, battery=%s%%",
            self._api.uuid,
            data.co2_ppm,
            data.pm_2_5_um,
            data.battery_pct,
        )
        return data
