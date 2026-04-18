"""Tests for low-level model helpers."""

from custom_components.unipi.const import DEFAULT_NUMBER_MAX, DEFAULT_NUMBER_MIN, DEFAULT_NUMBER_STEP
from custom_components.unipi.hub import _normalize_item, _serialize_value


def test_normalize_analog_output_enforces_voltage_range() -> None:
    """Analog outputs should always map to 0-10V numbers."""
    item = _normalize_item({"dev": "ao", "circuit": "1_01", "value": 0.0})

    assert item is not None
    assert item.value_range == (0.0, 10.0)
    assert item.unit == "V"
    assert item.min_value == DEFAULT_NUMBER_MIN
    assert item.max_value == DEFAULT_NUMBER_MAX
    assert item.step == DEFAULT_NUMBER_STEP


def test_normalize_unsupported_item_returns_none() -> None:
    """Unsupported EVOK device types should be ignored."""
    assert _normalize_item({"dev": "wd", "circuit": "1_01", "value": 0}) is None


def test_serialize_value_handles_supported_types() -> None:
    """Writable payloads should be normalized to EVOK form values."""
    assert _serialize_value(True) == "1"
    assert _serialize_value(False) == "0"
    assert _serialize_value(5) == "5"
    assert _serialize_value(5.5) == "5.5"
    assert _serialize_value(5.0) == "5"
    assert _serialize_value("abc") == "abc"


def test_sample_metadata_helpers(sample_metadata) -> None:
    """Device metadata should expose title and stable unique id."""
    assert sample_metadata.title == "Neuron L203 (SN 167)"
    assert sample_metadata.unique_id("192.168.1.10", 8080) == "neuron-l203-167"


def test_metadata_title_fallbacks() -> None:
    """Metadata title should include serial numbers when available."""
    from custom_components.unipi.models import UniPiDeviceMetadata

    assert UniPiDeviceMetadata(circuit="Neuron").title == "Neuron"
    assert UniPiDeviceMetadata(model="L203").title == "L203"
    assert UniPiDeviceMetadata(family="Neuron", model="L203", serial_number="167").title == "Neuron L203 (SN 167)"
    assert UniPiDeviceMetadata(family="Neuron", circuit="L203").title == "Neuron L203"
    assert UniPiDeviceMetadata().title == "UniPi"


def test_entity_description_range_fallbacks() -> None:
    """Non-analog outputs should use discovered ranges when present."""
    item = _normalize_item({"dev": "ai", "circuit": "1_01", "value": 1.2, "range": [1, 5], "unit": "V"})

    assert item is not None
    assert item.min_value == 1.0
    assert item.max_value == 5.0
