"""Tests for UniPi entity classes."""

from __future__ import annotations

import pytest
from homeassistant.const import Platform

from custom_components.unipi.binary_sensor import UniPiBinarySensorEntity, async_setup_entry as binary_sensor_setup
from custom_components.unipi.light import UniPiLedEntity
from custom_components.unipi.light import async_setup_entry as light_setup
from custom_components.unipi.number import UniPiAnalogOutputEntity
from custom_components.unipi.number import async_setup_entry as number_setup
from custom_components.unipi.sensor import UniPiSensorEntity
from custom_components.unipi.sensor import async_setup_entry as sensor_setup
from custom_components.unipi.switch import UniPiSwitchEntity
from custom_components.unipi.switch import async_setup_entry as switch_setup


class DummyEntry:
    """Minimal config entry stub for platform setup tests."""

    def __init__(self, runtime_data) -> None:
        self.runtime_data = runtime_data


@pytest.mark.asyncio
async def test_switch_entity_turns_output_on_and_off(fake_hub) -> None:
    """Switch entities should write boolean-like EVOK values."""
    entity = UniPiSwitchEntity(fake_hub, fake_hub.get_item("ro:1_01"))

    assert entity.is_on is False

    await entity.async_turn_on()
    await entity.async_turn_off()

    assert fake_hub.set_calls == [("ro", "1_01", 1), ("ro", "1_01", 0)]


@pytest.mark.asyncio
async def test_led_entity_turns_on(fake_hub) -> None:
    """LED entities should be exposed as Home Assistant lights."""
    entity = UniPiLedEntity(fake_hub, fake_hub.get_item("led:1_01"))

    assert entity.is_on is False

    await entity.async_turn_on()

    assert entity.is_on is True
    assert fake_hub.set_calls[-1] == ("led", "1_01", 1)


@pytest.mark.asyncio
async def test_analog_output_entity_clamps_values(fake_hub) -> None:
    """Analog outputs should stay inside the required 0-10 range."""
    entity = UniPiAnalogOutputEntity(fake_hub, fake_hub.get_item("ao:1_01"))

    assert entity.native_min_value == 0.0
    assert entity.native_max_value == 10.0
    assert entity.native_unit_of_measurement == "V"

    await entity.async_set_native_value(14.2)
    await entity.async_set_native_value(-1.0)

    assert fake_hub.set_calls[-2:] == [("ao", "1_01", 10.0), ("ao", "1_01", 0.0)]


def test_binary_sensor_entity_reports_state(fake_hub) -> None:
    """Binary sensors should expose digital input state."""
    entity = UniPiBinarySensorEntity(fake_hub, fake_hub.get_item("di:2_01"))

    assert entity.is_on is True


def test_sensor_entity_exposes_value_and_unit(fake_hub) -> None:
    """Analog inputs should expose native value and unit."""
    entity = UniPiSensorEntity(fake_hub, fake_hub.get_item("ai:1_01"))

    assert entity.native_value == 2.5
    assert entity.native_unit_of_measurement == "V"
    assert entity.available is True
    assert entity.extra_state_attributes == {
        "evok_dev": "ai",
        "evok_circuit": "1_01",
        "mode": "Voltage",
    }


@pytest.mark.asyncio
async def test_platform_setup_functions_add_expected_entities(fake_hub) -> None:
    """Each platform setup should create entities for its matching EVOK items."""
    entry = DummyEntry(fake_hub)
    added = []

    def add_entities(entities) -> None:
        added.extend(list(entities))

    await switch_setup(None, entry, add_entities)
    await binary_sensor_setup(None, entry, add_entities)
    await light_setup(None, entry, add_entities)
    await sensor_setup(None, entry, add_entities)
    await number_setup(None, entry, add_entities)

    assert len(added) == 6
    assert {entity.entity_description.platform for entity in added} == {
        Platform.SWITCH,
        Platform.BINARY_SENSOR,
        Platform.LIGHT,
        Platform.SENSOR,
        Platform.NUMBER,
    }
