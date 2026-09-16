"""Sensor platform for UniPi EVOK."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
        [
            UniPiIpAddressSensorEntity(hub, "ip_address", "IP Address"),
            UniPiEvokVersionSensorEntity(hub, "evok_version", "EVOK Version"),
            UniPiBoardCountSensorEntity(hub, "board_count", "Board Count"),
            *(
                UniPiSensorEntity(hub, item)
                for item in hub.get_items_for_platform(DEVICE_TYPE_TO_PLATFORM["ai"])
            ),
        ]
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


class UniPiDiagnosticSensorEntity(SensorEntity):
    """Static device-level diagnostic sensor, not backed by an EVOK circuit item."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: UniPiHub, key: str, name: str) -> None:
        self._hub = hub
        self._attr_name = name
        self._attr_unique_id = f"{hub.device_identifier}-{key}"
        self._attr_device_info = hub.device_info


class UniPiIpAddressSensorEntity(UniPiDiagnosticSensorEntity):
    """Report the configured EVOK host address."""

    @property
    def native_value(self) -> str:
        """Return the configured host address."""
        return self._hub.host


class UniPiEvokVersionSensorEntity(UniPiDiagnosticSensorEntity):
    """Report the running EVOK software version."""

    @property
    def native_value(self) -> str | None:
        """Return the EVOK software version, if known."""
        return self._hub.evok_version

    @property
    def available(self) -> bool:
        """Return whether the EVOK version was successfully fetched."""
        return self._hub.evok_version is not None


class UniPiBoardCountSensorEntity(UniPiDiagnosticSensorEntity):
    """Report the number of extension boards reported by EVOK."""

    @property
    def native_value(self) -> int | None:
        """Return the board count, if known."""
        return self._hub.metadata.board_count

    @property
    def available(self) -> bool:
        """Return whether the board count was reported by EVOK."""
        return self._hub.metadata.board_count is not None
