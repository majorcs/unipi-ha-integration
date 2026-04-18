"""Tests for integration setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unipi import async_setup_entry, async_unload_entry
from custom_components.unipi.const import DEFAULT_PORT, DOMAIN, SUPPORTED_PLATFORMS
from custom_components.unipi.hub import UniPiConnectionError


@pytest.mark.asyncio
async def test_async_setup_entry_initializes_hub(hass) -> None:
    """Config entry setup should initialize the runtime hub and forward platforms."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.10", CONF_PORT: DEFAULT_PORT},
    )
    entry.add_to_hass(hass)

    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    with patch("custom_components.unipi.UniPiHub") as hub_cls:
        hub = hub_cls.return_value
        hub.async_initialize = AsyncMock()

        assert await async_setup_entry(hass, entry) is True

    hub_cls.assert_called_once()
    hub.async_initialize.assert_awaited_once()
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, SUPPORTED_PLATFORMS)
    assert hass.data[DOMAIN][entry.entry_id] is hub
    assert entry.runtime_data is hub


@pytest.mark.asyncio
async def test_async_setup_entry_raises_config_entry_not_ready(hass) -> None:
    """Connection failures during setup should retry later."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.10", CONF_PORT: DEFAULT_PORT},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.unipi.UniPiHub") as hub_cls:
        hub_cls.return_value.async_initialize = AsyncMock(side_effect=UniPiConnectionError("cannot_connect"))

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_unload_entry_shuts_down_hub(hass) -> None:
    """Unloading should tear down platforms and stop the runtime hub."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.10", CONF_PORT: DEFAULT_PORT},
    )
    entry.add_to_hass(hass)

    hub = AsyncMock()
    entry.runtime_data = hub
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    assert await async_unload_entry(hass, entry) is True

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, SUPPORTED_PLATFORMS)
    hub.async_shutdown.assert_awaited_once()
    assert entry.entry_id not in hass.data[DOMAIN]
