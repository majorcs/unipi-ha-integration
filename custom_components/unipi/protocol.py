"""Protocol compatibility layer for EVOK payload differences."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .const import DEFAULT_NUMBER_MAX, DEFAULT_NUMBER_MIN, DEVICE_TYPE_TO_PLATFORM, WRITABLE_DEVICE_TYPES
from .models import UniPiDeviceMetadata, UniPiEntityDescription

LEGACY_DEVICE_ALIASES: dict[str, str] = {
    "relay": "ro",
    "output": "do",
    "input": "di",
}

LEGACY_WRITE_ALIASES: dict[str, str] = {
    "ro": "relay",
    "do": "output",
    "di": "input",
}


@dataclass(slots=True)
class EVOKProtocolAdapter:
    """Normalize EVOK payloads for one protocol generation."""

    name: str
    metadata_dev: str
    device_aliases: dict[str, str]
    write_aliases: dict[str, str]

    def is_metadata_item(self, raw_item: dict[str, Any]) -> bool:
        """Return whether the raw EVOK item is the metadata record."""
        return _string_or_none(raw_item.get("dev")) == self.metadata_dev

    def canonical_dev(self, raw_dev: str | None) -> str | None:
        """Map one raw EVOK type to the canonical entity type."""
        if raw_dev is None:
            return None
        return self.device_aliases.get(raw_dev, raw_dev)

    def write_dev(self, canonical_dev: str) -> str:
        """Return the EVOK endpoint device name for writes."""
        return self.write_aliases.get(canonical_dev, canonical_dev)

    def extract_metadata(self, inventory: Iterable[dict[str, Any]]) -> UniPiDeviceMetadata | None:
        """Return normalized metadata from an EVOK inventory payload."""
        for raw_item in inventory:
            if self.is_metadata_item(raw_item):
                return self.normalize_metadata(raw_item)
        return None

    def normalize_metadata(self, raw_item: dict[str, Any]) -> UniPiDeviceMetadata:
        """Create normalized metadata from one raw EVOK item."""
        serial_number = raw_item.get("sn")
        return UniPiDeviceMetadata(
            family=_string_or_none(raw_item.get("family")),
            model=_string_or_none(raw_item.get("model")),
            serial_number=str(serial_number) if serial_number is not None else None,
            circuit=_string_or_none(raw_item.get("circuit")),
            board_count=int(raw_item["board_count"]) if raw_item.get("board_count") is not None else None,
        )

    def normalize_item(self, raw_item: dict[str, Any]) -> UniPiEntityDescription | None:
        """Normalize one supported EVOK item into the integration model."""
        raw_dev = _string_or_none(raw_item.get("dev"))
        circuit = _string_or_none(raw_item.get("circuit"))
        if raw_dev is None or circuit is None:
            return None

        dev = self.canonical_dev(raw_dev)
        if dev is None or dev == self.metadata_dev:
            return None

        platform = DEVICE_TYPE_TO_PLATFORM.get(dev)
        if platform is None:
            return None

        value_range = self._normalize_range(raw_item)
        if dev == "ao":
            value_range = (DEFAULT_NUMBER_MIN, DEFAULT_NUMBER_MAX)
            raw_item = {**raw_item, "unit": raw_item.get("unit") or "V"}

        return UniPiEntityDescription(
            key=f"{dev}:{circuit}",
            platform=platform,
            dev=dev,
            circuit=circuit,
            name=_build_entity_name(dev, circuit),
            value=raw_item.get("value"),
            unit=_string_or_none(raw_item.get("unit")),
            unit_of_measurement=_string_or_none(raw_item.get("unit")),
            suggested_unit_of_measurement=_string_or_none(raw_item.get("unit")),
            mode=_string_or_none(raw_item.get("mode")),
            modes=raw_item.get("modes"),
            value_range=value_range,
            writable=dev in WRITABLE_DEVICE_TYPES,
            raw=dict(raw_item),
        )

    def _normalize_range(self, raw_item: dict[str, Any]) -> tuple[float, float] | None:
        """Return a normalized value range if available."""
        item_range = raw_item.get("range")
        if isinstance(item_range, list) and len(item_range) == 2:
            return (float(item_range[0]), float(item_range[1]))
        return None


class EVOKV3ProtocolAdapter(EVOKProtocolAdapter):
    """Adapter for EVOK 3.0.1 and newer payloads."""

    def __init__(self) -> None:
        super().__init__(
            name="v3",
            metadata_dev="device_info",
            device_aliases={},
            write_aliases={},
        )


class EVOKLegacyProtocolAdapter(EVOKProtocolAdapter):
    """Adapter for EVOK versions before 3.0.1."""

    def __init__(self) -> None:
        super().__init__(
            name="legacy",
            metadata_dev="neuron",
            device_aliases=LEGACY_DEVICE_ALIASES,
            write_aliases=LEGACY_WRITE_ALIASES,
        )

    def normalize_metadata(self, raw_item: dict[str, Any]) -> UniPiDeviceMetadata:
        """Create normalized metadata from the legacy EVOK metadata record."""
        metadata = super().normalize_metadata(raw_item)
        if metadata.family is None and _string_or_none(raw_item.get("dev")) == "neuron":
            metadata.family = "Neuron"
        return metadata

    def _normalize_range(self, raw_item: dict[str, Any]) -> tuple[float, float] | None:
        """Return a normalized range from legacy EVOK payloads."""
        value_range = super()._normalize_range(raw_item)
        if value_range is not None:
            return value_range

        item_range = raw_item.get("range")
        if isinstance(item_range, (int, float)):
            return (0.0, float(item_range))
        if isinstance(item_range, str):
            try:
                return (0.0, float(item_range))
            except ValueError:
                return None
        return None


def detect_evok_protocol(
    inventory: Iterable[dict[str, Any]],
    fallback: EVOKProtocolAdapter | None = None,
) -> EVOKProtocolAdapter:
    """Detect the EVOK protocol generation used by one inventory payload."""
    items = tuple(inventory)
    devs = {_string_or_none(item.get("dev")) for item in items}

    if "device_info" in devs or {"ro", "do", "di"} & devs:
        return EVOKV3ProtocolAdapter()

    if "neuron" in devs or {"relay", "output", "input"} & devs:
        return EVOKLegacyProtocolAdapter()

    for item in items:
        raw_dev = _string_or_none(item.get("dev"))
        if raw_dev in {"ai", "ao"}:
            if isinstance(item.get("range"), str) or item.get("range_modes") is not None:
                return EVOKLegacyProtocolAdapter()
            if isinstance(item.get("modes"), dict):
                return EVOKV3ProtocolAdapter()

    return fallback or EVOKV3ProtocolAdapter()


def normalize_metadata_from_raw(raw_item: dict[str, Any]) -> UniPiDeviceMetadata:
    """Normalize one raw metadata payload without external protocol context."""
    return detect_evok_protocol([raw_item]).normalize_metadata(raw_item)


def normalize_item_from_raw(raw_item: dict[str, Any]) -> UniPiEntityDescription | None:
    """Normalize one raw EVOK payload without external protocol context."""
    return detect_evok_protocol([raw_item]).normalize_item(raw_item)


def _build_entity_name(dev: str, circuit: str) -> str:
    """Return a human readable entity name."""
    labels = {
        "ro": "Relay",
        "do": "Digital Output",
        "di": "Digital Input",
        "led": "LED",
        "ai": "Analog Input",
        "ao": "Analog Output",
    }
    return f"{labels.get(dev, dev.upper())} {circuit.replace('_', '.')}"


def _string_or_none(value: Any) -> str | None:
    """Return a stripped string or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None