"""Tests for the UniPi config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unipi.const import CONF_DEVICE_UID, CONF_MODEL, DEFAULT_PORT, DOMAIN
from custom_components.unipi.hub import UniPiConnectionError, UniPiProbeResult


@pytest.mark.asyncio
async def test_user_flow_creates_entry(hass, sample_inventory, sample_metadata) -> None:
    """A valid EVOK device should create a config entry."""
    probe_result = UniPiProbeResult(
        metadata=sample_metadata,
        inventory=sample_inventory,
        unique_id=sample_metadata.unique_id("192.168.1.10", DEFAULT_PORT),
        title=sample_metadata.title,
    )

    with (
        patch("custom_components.unipi.config_flow.async_probe_unipi", return_value=probe_result),
        patch("custom_components.unipi.async_setup_entry", new=AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_HOST: "192.168.1.10", CONF_PORT: DEFAULT_PORT},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Neuron L203 (SN 167)"
    assert result["data"] == {
        CONF_HOST: "192.168.1.10",
        CONF_PORT: DEFAULT_PORT,
        CONF_DEVICE_UID: "neuron-l203-167",
        CONF_MODEL: "L203",
    }


@pytest.mark.asyncio
async def test_user_flow_handles_connection_error(hass) -> None:
    """Connection failures should be surfaced to the user."""
    with (
        patch(
            "custom_components.unipi.config_flow.async_probe_unipi",
            side_effect=UniPiConnectionError("cannot_connect"),
        ),
        patch("custom_components.unipi.async_setup_entry", new=AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_HOST: "192.168.1.10", CONF_PORT: DEFAULT_PORT},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_user_flow_aborts_for_duplicate_device(hass, sample_inventory, sample_metadata) -> None:
    """The same physical UniPi should not be configured twice."""
    existing_entry = MockConfigEntry(domain=DOMAIN, unique_id="neuron-l203-167")
    existing_entry.add_to_hass(hass)

    probe_result = UniPiProbeResult(
        metadata=sample_metadata,
        inventory=sample_inventory,
        unique_id="neuron-l203-167",
        title=sample_metadata.title,
    )

    with (
        patch("custom_components.unipi.config_flow.async_probe_unipi", return_value=probe_result),
        patch("custom_components.unipi.async_setup_entry", new=AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_HOST: "192.168.1.10", CONF_PORT: DEFAULT_PORT},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
