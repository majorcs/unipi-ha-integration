"""Switch platform for UniPi EVOK."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import UniPiEntity
from .hub import UniPiHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniPi switch entities."""
    hub: UniPiHub = entry.runtime_data
    async_add_entities(UniPiSwitchEntity(hub, item) for item in hub.get_items_for_platform(Platform.SWITCH))


class UniPiSwitchEntity(UniPiEntity, SwitchEntity):
    """Representation of a UniPi relay or digital output."""

    @property
    def is_on(self) -> bool:
        """Return whether the output is on."""
        item = self.entity_description
        return bool(item and item.value)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the EVOK output on."""
        item = self.entity_description
        if item is None:
            return
        await self._hub.async_set_value(item.dev, item.circuit, 1)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the EVOK output off."""
        item = self.entity_description
        if item is None:
            return
        await self._hub.async_set_value(item.dev, item.circuit, 0)
