"""Shared pytest fixtures for the UniPi integration tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.unipi.const import DOMAIN
from custom_components.unipi.hub import _metadata_from_raw, _normalize_item

_SAMPLE_INVENTORY: list[dict[str, Any]] = [
    {
        "dev": "device_info",
        "family": "Neuron",
        "model": "L203",
        "sn": 167,
        "board_count": 3,
        "circuit": "L203",
    },
    {
        "dev": "ro",
        "circuit": "1_01",
        "value": 0,
    },
    {
        "dev": "do",
        "circuit": "1_02",
        "value": 1,
        "pending": False,
        "mode": "Simple",
        "modes": ["Simple", "PWM"],
    },
    {
        "dev": "di",
        "circuit": "2_01",
        "value": 1,
        "debounce": 50,
        "counter": 0,
        "mode": "Simple",
        "modes": ["Simple", "DirectSwitch"],
    },
    {
        "dev": "led",
        "circuit": "1_01",
        "value": 0,
    },
    {
        "dev": "ai",
        "circuit": "1_01",
        "value": 2.5,
        "unit": "V",
        "mode": "Voltage",
        "modes": {
            "Voltage": {"value": 0, "unit": "V", "range": [0, 10]},
            "Current": {"value": 1, "unit": "mA", "range": [0, 20]},
        },
        "range": [0, 10],
    },
    {
        "dev": "ao",
        "circuit": "1_01",
        "value": 0.0,
        "mode": "Voltage",
        "modes": {
            "Voltage": {"value": 0, "unit": "V", "range": [0, 10]},
        },
        "unit": "V",
    },
    {
        "dev": "temp",
        "circuit": "28409D1F0000801E",
        "value": 26.9,
        "lost": False,
        "type": "DS18B20",
    },
]

_LEGACY_SAMPLE_INVENTORY: list[dict[str, Any]] = [
    {
        "dev": "neuron",
        "model": "M205",
        "sn": 31,
        "board_count": 2,
        "circuit": "1",
    },
    {
        "dev": "relay",
        "circuit": "2_11",
        "value": 0,
        "pending": False,
        "mode": "Simple",
        "modes": ["Simple"],
    },
    {
        "dev": "input",
        "circuit": "2_11",
        "value": 1,
        "debounce": 50,
        "counter": 0,
        "counter_mode": "Enabled",
        "mode": "Simple",
        "modes": ["Simple", "DirectSwitch"],
    },
    {
        "dev": "led",
        "circuit": "1_01",
        "value": 0,
    },
    {
        "dev": "ai",
        "circuit": "1_01",
        "value": 0.0078,
        "unit": "V",
        "mode": "Voltage",
        "modes": ["Voltage", "Current"],
        "range_modes": ["10.0"],
        "range": "10.0",
    },
    {
        "dev": "ao",
        "circuit": "1_01",
        "value": 0.0,
        "mode": "Voltage",
        "modes": ["Voltage", "Current", "Resistance"],
        "unit": "V",
    },
    {
        "dev": "temp",
        "circuit": "28409D1F0000801E",
        "value": 21.3,
        "lost": False,
        "type": "DS18B20",
    },
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def sample_inventory() -> list[dict[str, Any]]:
    """Return a fresh EVOK inventory payload."""
    return deepcopy(_SAMPLE_INVENTORY)


@pytest.fixture
def sample_metadata(sample_inventory):
    """Return normalized metadata from the sample device_info item."""
    return _metadata_from_raw(sample_inventory[0])


@pytest.fixture
def legacy_inventory() -> list[dict[str, Any]]:
    """Return a fresh legacy EVOK inventory payload."""
    return deepcopy(_LEGACY_SAMPLE_INVENTORY)


@pytest.fixture
def legacy_metadata(legacy_inventory):
    """Return normalized metadata from the legacy device metadata item."""
    return _metadata_from_raw(legacy_inventory[0])


class FakeHub:
    """Simple hub stub for entity unit tests."""

    def __init__(self, sample_inventory: list[dict[str, Any]], sample_metadata) -> None:
        self.available = True
        self.host = "127.0.0.1"
        self.port = 8080
        self.evok_version = "v3.2.1"
        self.metadata = sample_metadata
        self.device_identifier = sample_metadata.unique_id(self.host, self.port)
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer="UniPi Technology",
            model=sample_metadata.model,
            name=sample_metadata.title,
            serial_number=sample_metadata.serial_number,
        )
        self._items = {
            item.key: item
            for item in (
                _normalize_item(raw_item)
                for raw_item in sample_inventory
                if raw_item["dev"] != "device_info"
            )
            if item is not None
        }
        self.set_calls: list[tuple[str, str, Any]] = []
        self.listeners: dict[str, list] = {}

    def get_item(self, key: str):
        """Return one cached item."""
        return self._items.get(key)

    def get_items_for_platform(self, platform):
        """Return items for a Home Assistant platform."""
        return [item for item in self._items.values() if item.platform == platform]

    async def async_set_value(self, dev: str, circuit: str, value: Any) -> None:
        """Record a writable action and update local state."""
        self.set_calls.append((dev, circuit, value))
        item = self._items[f"{dev}:{circuit}"]
        item.value = value
        for listener in self.listeners.get(item.key, []):
            listener()

    def async_add_listener(self, key, update_callback):
        """Register an update callback."""
        self.listeners.setdefault(key, []).append(update_callback)

        def _remove():
            self.listeners[key].remove(update_callback)

        return _remove


@pytest.fixture
def fake_hub(sample_inventory, sample_metadata) -> FakeHub:
    """Return a fake hub for entity tests."""
    return FakeHub(sample_inventory, sample_metadata)
