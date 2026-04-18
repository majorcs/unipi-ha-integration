"""Sensor platform for UniPi EVOK."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
    """Set up UniPi sensor entities."""
    hub: UniPiHub = entry.runtime_data
    async_add_entities(
        UniPiSensorEntity(hub, item)
        for item in hub.get_items_for_platform(DEVICE_TYPE_TO_PLATFORM["ai"])
    )


class UniPiSensorEntity(UniPiEntity, SensorEntity):
    """Representation of a UniPi analog input."""

    @property
    def native_value(self):
        """Return the sensor value."""
        item = self.entity_description
        return None if item is None else item.value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        item = self.entity_description
        return None if item is None else item.unit
