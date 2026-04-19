"""Tests for the EVOK protocol compatibility layer."""

from __future__ import annotations

from custom_components.unipi.hub import _metadata_from_raw, _normalize_item
from custom_components.unipi.protocol import EVOKLegacyProtocolAdapter, EVOKV3ProtocolAdapter, detect_evok_protocol


def test_detect_current_protocol(sample_inventory) -> None:
    """EVOK 3.0.1+ payloads should use the current protocol adapter."""
    adapter = detect_evok_protocol(sample_inventory)

    assert isinstance(adapter, EVOKV3ProtocolAdapter)


def test_detect_legacy_protocol(legacy_inventory) -> None:
    """Pre-3.0.1 payloads should use the legacy protocol adapter."""
    adapter = detect_evok_protocol(legacy_inventory)

    assert isinstance(adapter, EVOKLegacyProtocolAdapter)


def test_legacy_metadata_normalization(legacy_metadata) -> None:
    """Legacy metadata should normalize to the current device model."""
    assert legacy_metadata.family == "Neuron"
    assert legacy_metadata.model == "M205"
    assert legacy_metadata.serial_number == "31"
    assert legacy_metadata.title == "Neuron M205 (SN 31)"
    assert legacy_metadata.unique_id("192.168.88.50", 8080) == "neuron-m205-31"


def test_legacy_entity_normalization_maps_aliases(legacy_inventory) -> None:
    """Legacy relay/input entities should normalize to current canonical device types."""
    relay_item = _normalize_item(next(item for item in legacy_inventory if item["dev"] == "relay"))
    input_item = _normalize_item(next(item for item in legacy_inventory if item["dev"] == "input"))
    ai_item = _normalize_item(next(item for item in legacy_inventory if item["dev"] == "ai"))

    assert relay_item is not None
    assert relay_item.dev == "ro"
    assert relay_item.key == "ro:2_11"

    assert input_item is not None
    assert input_item.dev == "di"
    assert input_item.key == "di:2_11"

    assert ai_item is not None
    assert ai_item.value_range == (0.0, 10.0)


def test_metadata_wrapper_normalizes_legacy_payload() -> None:
    """The public metadata helper should normalize legacy metadata records."""
    metadata = _metadata_from_raw({"dev": "neuron", "model": "M205", "sn": 31, "circuit": "1"})

    assert metadata.family == "Neuron"
    assert metadata.title == "Neuron M205 (SN 31)"