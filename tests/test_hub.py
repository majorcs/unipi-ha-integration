"""Tests for the UniPi EVOK runtime hub."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import WSMsgType
from aiohttp.client_exceptions import ClientError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import Platform

from custom_components.unipi.hub import (
    UniPiConnectionError,
    UniPiHub,
    _async_request_json,
    _build_entity_name,
    _string_or_none,
    async_probe_unipi,
)


@pytest.mark.asyncio
async def test_async_probe_unipi_reads_device_info(hass, aioclient_mock, sample_inventory) -> None:
    """Config flow probing should discover metadata from /rest/all."""
    aioclient_mock.get("http://192.168.1.10:8080/rest/all", json=sample_inventory)

    result = await async_probe_unipi(async_get_clientsession(hass), "192.168.1.10", 8080)

    assert result.title == "Neuron L203 (SN 167)"
    assert result.unique_id == "neuron-l203-167"
    assert result.metadata.model == "L203"
    assert result.metadata.serial_number == "167"


@pytest.mark.asyncio
async def test_async_probe_unipi_rejects_invalid_inventory(hass, aioclient_mock) -> None:
    """Probing should fail if EVOK returns an invalid payload."""
    aioclient_mock.get("http://192.168.1.11:8080/rest/all", json={"unexpected": True})

    with pytest.raises(UniPiConnectionError):
        await async_probe_unipi(async_get_clientsession(hass), "192.168.1.11", 8080)


@pytest.mark.asyncio
async def test_async_set_value_updates_cached_item(hass, aioclient_mock, sample_inventory) -> None:
    """POST writes should refresh the cached entity state."""
    session = async_get_clientsession(hass)
    hub = UniPiHub(hass, session, "192.168.1.10", 8080)
    hub._ingest_inventory(sample_inventory)

    aioclient_mock.post(
        "http://192.168.1.10:8080/rest/ao/1_01",
        json={
            "success": True,
            "result": {
                "dev": "ao",
                "circuit": "1_01",
                "value": 5.4,
                "unit": "V",
                "mode": "Voltage",
            },
        },
    )

    await hub.async_set_value("ao", "1_01", 5.4)

    assert hub.get_item("ao:1_01").value == 5.4


@pytest.mark.asyncio
async def test_websocket_message_updates_cache_and_notifies(hass) -> None:
    """Incoming websocket events should update cache and notify listeners."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)
    hub._ingest_inventory(
        [
            {"dev": "device_info", "family": "Neuron", "model": "L203", "sn": 167, "circuit": "L203"},
            {"dev": "led", "circuit": "1_01", "value": 0},
        ]
    )

    callback = Mock()
    hub.async_add_listener("led:1_01", callback)

    await hub._handle_websocket_message(
        SimpleNamespace(type=WSMsgType.TEXT, data=json.dumps([{"dev": "led", "circuit": "1_01", "value": 1}]))
    )

    assert hub.get_item("led:1_01").value == 1
    callback.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_non_json_payload_is_ignored(hass) -> None:
    """Malformed websocket messages should not crash the hub."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)

    await hub._handle_websocket_message(SimpleNamespace(type=WSMsgType.TEXT, data="not-json"))

    assert hub.get_item("led:1_01") is None


def test_get_items_for_platform_filters_expected_entities(hass, sample_inventory) -> None:
    """Platform filtering should return only matching cached entities."""
    session = Mock()
    hub = UniPiHub(hass, session, "192.168.1.10", 8080)
    hub._ingest_inventory(sample_inventory)

    switch_items = hub.get_items_for_platform(hub.get_item("ro:1_01").platform)

    assert {item.key for item in switch_items} == {"ro:1_01", "do:1_02"}


@pytest.mark.asyncio
async def test_async_initialize_and_shutdown_manage_websocket_task(hass, sample_inventory) -> None:
    """Initialization should cache inventory and start a managed websocket task."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)

    async def fake_loop() -> None:
        hub._available = True
        hub._connected_event.set()
        await hub._stop_event.wait()

    hub.async_fetch_inventory = AsyncMock(return_value=sample_inventory)
    hub._websocket_loop = fake_loop

    await hub.async_initialize()

    assert hub.available is True
    assert hub.metadata.model == "L203"
    assert hub.device_identifier == "neuron-l203-167"
    assert hub.device_info["configuration_url"] == "http://192.168.1.10:8080"
    assert {item.key for item in hub.get_items_for_platform(Platform.LIGHT)} == {"led:1_01"}

    await hub.async_shutdown()

    assert hub.available is False
    assert hub._ws_task is None


@pytest.mark.asyncio
async def test_async_initialize_times_out_without_websocket_ready(hass, sample_inventory) -> None:
    """Initialization should fail if the websocket never signals readiness."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)
    hub.async_fetch_inventory = AsyncMock(return_value=sample_inventory)
    hub.async_shutdown = AsyncMock()

    async def never_ready() -> None:
        await asyncio.sleep(3600)

    hub._websocket_loop = never_ready

    async def fake_wait_for(*args, **kwargs):
        raise TimeoutError

    with patch("custom_components.unipi.hub.asyncio.wait_for", side_effect=fake_wait_for):
        with pytest.raises(UniPiConnectionError):
            await hub.async_initialize()

    hub.async_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_fetch_inventory_rejects_non_list(hass) -> None:
    """Inventory fetch should fail on invalid EVOK responses."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)

    with patch("custom_components.unipi.hub._async_request_json", AsyncMock(return_value={"bad": True})):
        with pytest.raises(UniPiConnectionError):
            await hub.async_fetch_inventory()


@pytest.mark.asyncio
async def test_async_set_value_falls_back_to_followup_get(hass, sample_inventory) -> None:
    """Writes should refresh state with GET if POST does not return a result payload."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)
    hub._ingest_inventory(sample_inventory)

    with patch(
        "custom_components.unipi.hub._async_request_json",
        AsyncMock(side_effect=[{"success": True}, {"dev": "ro", "circuit": "1_01", "value": 1}]),
    ) as request_mock:
        await hub.async_set_value("ro", "1_01", 1)

    assert request_mock.await_count == 2
    assert hub.get_item("ro:1_01").value == 1


def test_async_add_listener_remove_is_idempotent(hass, sample_inventory) -> None:
    """Listener removal should be safe even if called more than once."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)
    hub._ingest_inventory(sample_inventory)
    callback = Mock()

    remove = hub.async_add_listener("ro:1_01", callback)
    remove()
    remove()

    hub._notify("ro:1_01")
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_loop_processes_message_and_disconnects_cleanly(hass) -> None:
    """The websocket loop should process messages and clear availability on exit."""

    class FakeWebSocket:
        def __init__(self, hub: UniPiHub) -> None:
            self._hub = hub
            self._messages = [SimpleNamespace(type=WSMsgType.TEXT, data=json.dumps({"dev": "led", "circuit": "1_01", "value": 1}))]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            self._iter = iter(self._messages)
            return self

        async def __anext__(self):
            try:
                value = next(self._iter)
            except StopIteration:
                self._hub._stop_event.set()
                raise StopAsyncIteration
            return value

    session = Mock()
    hub = UniPiHub(hass, session, "192.168.1.10", 8080)
    hub._ingest_inventory(
        [
            {"dev": "device_info", "family": "Neuron", "model": "L203", "sn": 167, "circuit": "L203"},
            {"dev": "led", "circuit": "1_01", "value": 0},
        ]
    )
    session.ws_connect.return_value = FakeWebSocket(hub)

    await hub._websocket_loop()

    assert hub.get_item("led:1_01").value == 1
    assert hub.available is False


@pytest.mark.asyncio
async def test_websocket_loop_logs_connection_errors(hass) -> None:
    """Connection errors should not escape the reconnect loop."""
    session = Mock()
    session.ws_connect.side_effect = ClientError("boom")
    hub = UniPiHub(hass, session, "192.168.1.10", 8080)

    async def fake_sleep(delay: int) -> None:
        hub._stop_event.set()

    with patch("custom_components.unipi.hub.asyncio.sleep", side_effect=fake_sleep):
        await hub._websocket_loop()

    assert hub.available is False


@pytest.mark.asyncio
async def test_handle_websocket_close_and_error_messages(hass) -> None:
    """Close and error message types should be ignored gracefully."""
    hub = UniPiHub(hass, Mock(), "192.168.1.10", 8080)

    await hub._handle_websocket_message(SimpleNamespace(type=WSMsgType.CLOSE, data=""))
    await hub._handle_websocket_message(SimpleNamespace(type=WSMsgType.ERROR, data=""))

    assert hub.get_item("led:1_01") is None


@pytest.mark.asyncio
async def test_async_request_json_wraps_errors() -> None:
    """HTTP request helper should convert client errors into integration errors."""

    class BadSession:
        def request(self, *args, **kwargs):
            raise ClientError("boom")

    with pytest.raises(UniPiConnectionError):
        await _async_request_json(BadSession(), "GET", "http://example.test")


def test_build_helpers_cover_fallbacks() -> None:
    """String and naming helpers should handle empty values and defaults."""
    assert _build_entity_name("unknown", "1_02") == "UNKNOWN 1.02"
    assert _string_or_none(None) is None
    assert _string_or_none("   ") is None
    assert _string_or_none(" value ") == "value"
