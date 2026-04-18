"""Bootstrap helper to auto-configure the UniPi integration in a local E2E Home Assistant instance."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later

DOMAIN = "unipi_e2e_bootstrap"
TARGET_DOMAIN = "unipi"
DEFAULT_PORT = 8080
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Schedule automatic creation of the UniPi config entry for local E2E runs."""
    component_config = config.get(DOMAIN)
    if component_config is None:
        return True

    host = component_config[CONF_HOST]
    port = component_config[CONF_PORT]

    async def _bootstrap(_event: Event | None = None) -> None:
        existing_entries = hass.config_entries.async_entries(TARGET_DOMAIN)
        for entry in existing_entries:
            if entry.data.get(CONF_HOST) == host and entry.data.get(CONF_PORT, DEFAULT_PORT) == port:
                _LOGGER.info("UniPi config entry for %s:%s already exists", host, port)
                return

        result = await hass.config_entries.flow.async_init(
            TARGET_DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_HOST: host, CONF_PORT: port},
        )
        _LOGGER.info("UniPi bootstrap flow result: %s", result.get("type"))
        if result.get("type") != "create_entry":
            _LOGGER.warning("Unexpected UniPi bootstrap result: %s", result)

    async def _delayed_bootstrap(_now) -> None:
        await _bootstrap()

    def _handle_started(_event: Event) -> None:
        async_call_later(hass, 5, _delayed_bootstrap)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _handle_started)
    return True
