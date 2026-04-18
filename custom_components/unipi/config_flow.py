"""Config flow for the UniPi EVOK integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_DEVICE_UID, CONF_MODEL, DEFAULT_PORT, DOMAIN
from .hub import UniPiConnectionError, async_probe_unipi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class UniPiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniPi EVOK."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            try:
                probe = await async_probe_unipi(async_get_clientsession(self.hass), host, port)
            except UniPiConnectionError as err:
                _LOGGER.debug("Failed to probe EVOK device at %s:%s", host, port, exc_info=err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(probe.unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

                return self.async_create_entry(
                    title=probe.title,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_DEVICE_UID: probe.unique_id,
                        CONF_MODEL: probe.metadata.model or "",
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
