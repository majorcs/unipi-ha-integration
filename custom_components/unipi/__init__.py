"""The UniPi EVOK integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT, DOMAIN, SUPPORTED_PLATFORMS
from .hub import UniPiConnectionError, UniPiHub


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the UniPi EVOK integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniPi from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    hub = UniPiHub(hass, async_get_clientsession(hass), host, port)

    try:
        await hub.async_initialize()
    except UniPiConnectionError as err:
        raise ConfigEntryNotReady(f"Unable to connect to EVOK device at {host}:{port}: {err}") from err

    entry.runtime_data = hub
    hass.data[DOMAIN][entry.entry_id] = hub

    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a UniPi config entry."""
    hass.data.setdefault(DOMAIN, {})

    unload_ok = await hass.config_entries.async_unload_platforms(entry, SUPPORTED_PLATFORMS)

    hub: UniPiHub = entry.runtime_data
    await hub.async_shutdown()

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
