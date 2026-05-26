"""VisiblAir integration — entry point.

One HA config entry maps to one VisiblAir sensor. Each entry owns:

* a :class:`~.api.VisiblAirAPI` instance bound to that sensor's
  ``(uuid, view_token)`` pair
* a :class:`~.coordinator.VisiblAirCoordinator` polling on the entry's
  configured scan interval (default 60 s)

Per HA's modern pattern, the coordinator is stored on ``entry.runtime_data``
rather than ``hass.data[DOMAIN][entry.entry_id]``.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VisiblAirAPI
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_UUID,
    CONF_VIEW_TOKEN,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)
from .coordinator import VisiblAirCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type VisiblAirConfigEntry = ConfigEntry[VisiblAirCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: VisiblAirConfigEntry) -> bool:
    """Set up a single VisiblAir sensor from a config entry."""
    session = async_get_clientsession(hass)
    api = VisiblAirAPI(
        session=session,
        uuid=entry.data[CONF_UUID],
        view_token=entry.data[CONF_VIEW_TOKEN],
    )

    scan_seconds: int = entry.options.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
    )
    coordinator = VisiblAirCoordinator(
        hass, api=api, scan_interval=timedelta(seconds=scan_seconds)
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VisiblAirConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: VisiblAirConfigEntry
) -> None:
    """Reload when the user changes options (e.g. scan interval)."""
    _LOGGER.debug("Options updated for %s; reloading entry", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)
