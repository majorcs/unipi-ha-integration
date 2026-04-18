"""Binary sensor platform for UniPi EVOK."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up UniPi binary sensor entities."""
    hub: UniPiHub = entry.runtime_data
    async_add_entities(
        UniPiBinarySensorEntity(hub, item)
        for item in hub.get_items_for_platform(DEVICE_TYPE_TO_PLATFORM["di"])
    )


class UniPiBinarySensorEntity(UniPiEntity, BinarySensorEntity):
    """Representation of a UniPi digital input."""

    @property
    def is_on(self) -> bool:
        """Return whether the digital input is on."""
        item = self.entity_description
        return bool(item and item.value)
