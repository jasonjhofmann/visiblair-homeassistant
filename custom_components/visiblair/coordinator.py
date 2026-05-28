"""DataUpdateCoordinator — one per VisiblAir sensor / config entry."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    VisiblAirAPI,
    VisiblAirAuthError,
    VisiblAirError,
    VisiblAirSensorData,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> VisiblAirSensorData:
        """Fetch one reading; map API exceptions onto HA's coordinator errors."""
        try:
            return await self._api.fetch_latest()
        except VisiblAirAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VisiblAirError as err:
            raise UpdateFailed(str(err)) from err
