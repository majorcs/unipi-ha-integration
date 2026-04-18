"""Number platform for UniPi EVOK."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up UniPi number entities."""
    hub: UniPiHub = entry.runtime_data
    async_add_entities(
        UniPiAnalogOutputEntity(hub, item)
        for item in hub.get_items_for_platform(DEVICE_TYPE_TO_PLATFORM["ao"])
    )


class UniPiAnalogOutputEntity(UniPiEntity, NumberEntity):
    """Representation of a UniPi analog output."""

    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float | None:
        """Return the current analog output value."""
        item = self.entity_description
        return None if item is None or item.value is None else float(item.value)

    @property
    def native_min_value(self) -> float:
        """Return the minimum allowed value."""
        item = self.entity_description
        return 0.0 if item is None else item.min_value

    @property
    def native_max_value(self) -> float:
        """Return the maximum allowed value."""
        item = self.entity_description
        return 10.0 if item is None else item.max_value

    @property
    def native_step(self) -> float:
        """Return the step size."""
        item = self.entity_description
        return 0.1 if item is None else item.step

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        item = self.entity_description
        return None if item is None else item.unit

    async def async_set_native_value(self, value: float) -> None:
        """Write the analog output value."""
        item = self.entity_description
        if item is None:
            return
        await self._hub.async_set_value(item.dev, item.circuit, max(item.min_value, min(item.max_value, value)))
