"""Shared entity helpers for the UniPi EVOK integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import Entity

from .hub import UniPiHub
from .models import UniPiEntityDescription


class UniPiEntity(Entity):
    """Base entity backed by the UniPi runtime hub."""

    _attr_has_entity_name = True

    def __init__(self, hub: UniPiHub, item: UniPiEntityDescription) -> None:
        self._hub = hub
        self._item_key = item.key
        self._attr_name = item.name
        self._attr_unique_id = f"{hub.device_identifier}-{item.dev}-{item.circuit}"
        self._attr_device_info = hub.device_info

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return self._hub.available and self.entity_description is not None

    @property
    def entity_description(self) -> UniPiEntityDescription | None:
        """Return the cached EVOK entity description."""
        return self._hub.get_item(self._item_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return debug-friendly EVOK metadata."""
        item = self.entity_description
        if item is None:
            return {}

        return {
            "evok_dev": item.dev,
            "evok_circuit": item.circuit,
            "mode": item.mode,
        }

    async def async_added_to_hass(self) -> None:
        """Register runtime callbacks."""
        self.async_on_remove(self._hub.async_add_listener(self._item_key, self._handle_hub_update))

    def _handle_hub_update(self) -> None:
        """Update Home Assistant state from runtime callbacks."""
        self.async_write_ha_state()
