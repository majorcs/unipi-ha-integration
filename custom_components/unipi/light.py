"""Light platform for UniPi EVOK."""

from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_TO_PLATFORM
from .entity import UniPiEntity
from .hub import UniPiHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniPi light entities."""
    hub: UniPiHub = entry.runtime_data
    async_add_entities(
        UniPiLedEntity(hub, item)
        for item in hub.get_items_for_platform(DEVICE_TYPE_TO_PLATFORM["led"])
    )


class UniPiLedEntity(UniPiEntity, LightEntity):
    """Representation of a UniPi LED."""

    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool:
        """Return whether the LED is on."""
        item = self.entity_description
        return bool(item and item.value)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the LED on."""
        item = self.entity_description
        if item is None:
            return
        await self._hub.async_set_value(item.dev, item.circuit, 1)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the LED off."""
        item = self.entity_description
        if item is None:
            return
        await self._hub.async_set_value(item.dev, item.circuit, 0)
