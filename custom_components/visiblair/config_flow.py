"""Config + options flows for VisiblAir.

User pastes the sensor's MAC and viewToken (both visible in the
VisiblAir cloud portal's "Public view" URL); we validate by hitting
the live API once. One config entry per sensor — the MAC is the
unique_id, so adding the same sensor twice is rejected automatically.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    VisiblAirAPI,
    VisiblAirAuthError,
    VisiblAirOfflineError,
    VisiblAirParseError,
    VisiblAirSensorData,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_UUID,
    CONF_VIEW_TOKEN,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UUID): str,
        vol.Required(CONF_VIEW_TOKEN): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_VIEW_TOKEN): str})


class VisiblAirConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup + reauth."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self,
        user_input: Mapping[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Prompt for the sensor's MAC + viewToken."""
        errors: dict[str, str] = {}

        if user_input is not None:
            uuid_raw: str = user_input[CONF_UUID].strip()
            view_token: str = user_input[CONF_VIEW_TOKEN].strip()

            if not _MAC_RE.match(uuid_raw):
                errors[CONF_UUID] = "invalid_mac"
            else:
                uuid = _normalise_mac(uuid_raw)
                await self.async_set_unique_id(uuid)
                self._abort_if_unique_id_configured()

                try:
                    sensor = await self._validate(uuid, view_token)
                except VisiblAirAuthError:
                    errors["base"] = "invalid_auth"
                except VisiblAirOfflineError as err:
                    _LOGGER.warning("VisiblAir transport error: %s", err)
                    errors["base"] = "cannot_connect"
                except VisiblAirParseError as err:
                    _LOGGER.warning("VisiblAir parse error: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=sensor.description or DEFAULT_NAME,
                        data={CONF_UUID: uuid, CONF_VIEW_TOKEN: view_token},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Triggered when the coordinator raises ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: Mapping[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Prompt for a fresh viewToken — the MAC doesn't change."""
        errors: dict[str, str] = {}
        existing = self._get_reauth_entry()
        uuid: str = existing.data[CONF_UUID]

        if user_input is not None:
            view_token: str = user_input[CONF_VIEW_TOKEN].strip()
            try:
                await self._validate(uuid, view_token)
            except VisiblAirAuthError:
                errors["base"] = "invalid_auth"
            except VisiblAirOfflineError:
                errors["base"] = "cannot_connect"
            except VisiblAirParseError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    existing,
                    data={**existing.data, CONF_VIEW_TOKEN: view_token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"uuid": uuid},
        )

    async def _validate(self, uuid: str, view_token: str) -> VisiblAirSensorData:
        """One live fetch to confirm the credentials work."""
        session = async_get_clientsession(self.hass)
        api = VisiblAirAPI(session=session, uuid=uuid, view_token=view_token)
        return await api.fetch_latest()

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VisiblAirOptionsFlow(config_entry)


class VisiblAirOptionsFlow(OptionsFlow):
    """Per-entry runtime options — currently just the poll interval."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        # HA's OptionsFlow exposes config_entry as a property since 2024.12;
        # we hold an aliased reference to keep IDE refactors clean.
        self._entry = config_entry

    async def async_step_init(
        self,
        user_input: Mapping[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=dict(user_input))

        current = self._entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_SCAN_INTERVAL_SECONDS,
                        max=MAX_SCAN_INTERVAL_SECONDS,
                    ),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _normalise_mac(value: str) -> str:
    """Canonicalise to upper-case colon-separated form."""
    return value.upper()
