"""Data models for the UniPi EVOK integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from .const import DEFAULT_NUMBER_MAX, DEFAULT_NUMBER_MIN, DEFAULT_NUMBER_STEP


@dataclass
class UniPiDeviceMetadata:
    """Normalized EVOK device metadata."""

    family: str | None = None
    model: str | None = None
    serial_number: str | None = None
    circuit: str | None = None
    board_count: int | None = None

    @property
    def title(self) -> str:
        """Return the preferred device title."""
        if self.family:
            detail = self.model or self.circuit
            base_name = self.family if not detail else f"{self.family} {detail}"
        elif self.circuit:
            base_name = self.circuit
        elif self.model:
            base_name = self.model
        else:
            base_name = "UniPi"

        if self.serial_number and self.serial_number not in base_name:
            return f"{base_name} (SN {self.serial_number})"

        return base_name

    def unique_id(self, host: str, port: int) -> str:
        """Return a stable unique id for the physical device."""
        if self.serial_number:
            family = (self.family or "unipi").lower()
            model = (self.model or "device").lower()
            return f"{family}-{model}-{self.serial_number}"
        return f"{host}:{port}"


@dataclass
class UniPiEntityDescription:
    """Normalized representation of an EVOK item."""

    key: str
    platform: Platform
    dev: str
    circuit: str
    name: str
    value: Any = None
    unit: str | None = None
    unit_of_measurement: str | None = None
    suggested_unit_of_measurement: str | None = None
    mode: str | None = None
    modes: Any = None
    icon: str | None = None
    translation_key: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    last_reset: str | None = None
    suggested_display_precision: int | None = None
    options: list[str] | None = None
    entity_category: EntityCategory | None = None
    entity_registry_enabled_default: bool = True
    entity_registry_visible_default: bool = True
    force_update: bool = False
    value_range: tuple[float, float] | None = None
    writable: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def min_value(self) -> float:
        """Return the minimum writable value."""
        if self.dev == "ao":
            return DEFAULT_NUMBER_MIN
        if self.value_range is not None:
            return float(self.value_range[0])
        return DEFAULT_NUMBER_MIN

    @property
    def max_value(self) -> float:
        """Return the maximum writable value."""
        if self.dev == "ao":
            return DEFAULT_NUMBER_MAX
        if self.value_range is not None:
            return float(self.value_range[1])
        return DEFAULT_NUMBER_MAX

    @property
    def step(self) -> float:
        """Return the writable step."""
        return DEFAULT_NUMBER_STEP
