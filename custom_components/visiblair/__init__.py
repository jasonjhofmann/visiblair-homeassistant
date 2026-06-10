"""VisiblAir integration — entry point.

One HA config entry maps to one VisiblAir sensor. Each entry owns:

* a :class:`~.api.VisiblAirAPI` instance bound to that sensor's
  ``(uuid, view_token)`` pair
* a :class:`~.coordinator.VisiblAirCoordinator` polling at the fixed
  :data:`~.const.DEFAULT_SCAN_INTERVAL`

Per HA's modern pattern, the coordinator is stored on ``entry.runtime_data``
rather than ``hass.data[DOMAIN][entry.entry_id]``.

Poll interval is not user-configurable (HA Core convention — the integration
owns its cadence).
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VisiblAirAPI
from .const import CONF_UUID, CONF_VIEW_TOKEN, DOMAIN
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

    coordinator = VisiblAirCoordinator(hass, entry, api=api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _LOGGER.debug(
        "Set up VisiblAir sensor '%s' (%s), polling every %s",
        coordinator.data.description,
        entry.data[CONF_UUID],
        coordinator.update_interval,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VisiblAirConfigEntry) -> bool:
    """Unload a config entry."""
    # Drop this entry's consecutive-auth-failure count (see coordinator.py).
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
