"""EVOK client and runtime hub for UniPi."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession, WSMessage, WSMsgType
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DEFAULT_PORT,
    DOMAIN,
    MANUFACTURER,
)
from .models import UniPiDeviceMetadata, UniPiEntityDescription
from .protocol import (
    EVOKProtocolAdapter,
    EVOKV3ProtocolAdapter,
    detect_evok_protocol,
    normalize_item_from_raw,
    normalize_metadata_from_raw,
)

_LOGGER = logging.getLogger(__name__)


class UniPiConnectionError(HomeAssistantError):
    """Raised when EVOK cannot be reached."""


@dataclass
class UniPiProbeResult:
    """Result of probing an EVOK device."""

    metadata: UniPiDeviceMetadata
    inventory: list[dict[str, Any]]
    unique_id: str
    title: str


class UniPiHub:
    """Manage discovery, state cache, and websocket updates for one UniPi device."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        host: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.hass = hass
        self._session = session
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.websocket_url = f"ws://{host}:{port}/ws"
        self.web_ui_url = f"http://{host}"
        self.evok_version: str | None = None
        self._items: dict[str, UniPiEntityDescription] = {}
        self._metadata = UniPiDeviceMetadata()
        self._protocol: EVOKProtocolAdapter = EVOKV3ProtocolAdapter()
        self._listeners: dict[str, set[Callable[[], None]]] = defaultdict(set)
        self._ws_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()
        self._available = False

    @property
    def available(self) -> bool:
        """Return whether the websocket is currently connected."""
        return self._available

    @property
    def metadata(self) -> UniPiDeviceMetadata:
        """Return normalized device metadata."""
        return self._metadata

    @property
    def device_identifier(self) -> str:
        """Return the device identifier used for Home Assistant."""
        return self._metadata.unique_id(self.host, self.port)

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device metadata."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer=MANUFACTURER,
            model=self._metadata.model,
            name=self._metadata.title,
            serial_number=self._metadata.serial_number,
            configuration_url=self.web_ui_url,
            hw_version=self._metadata.family,
        )

    async def async_initialize(self) -> None:
        """Fetch inventory and establish the websocket connection."""
        inventory = await self.async_fetch_inventory()
        self._ingest_inventory(inventory, detect_protocol=True)
        await self.async_fetch_version()

        self._stop_event.clear()
        self._connected_event.clear()
        self._ws_task = asyncio.create_task(self._websocket_loop())

        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=10)
        except TimeoutError as err:
            await self.async_shutdown()
            raise UniPiConnectionError("cannot_connect") from err

    async def async_shutdown(self) -> None:
        """Stop background work and close the websocket loop."""
        self._stop_event.set()
        ws_task = self._ws_task
        self._ws_task = None

        if ws_task is not None:
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

        if self._available:
            self._available = False
            self._notify_all()

    async def async_fetch_inventory(self) -> list[dict[str, Any]]:
        """Fetch the full EVOK inventory from the device."""
        payload = await _async_request_json(self._session, "GET", f"{self.base_url}/rest/all")
        if not isinstance(payload, list):
            raise UniPiConnectionError("invalid_inventory")
        return payload

    async def async_fetch_version(self) -> None:
        """Best-effort fetch of the running EVOK software version.

        Some EVOK builds may not expose this endpoint, so failures are
        logged and swallowed instead of blocking setup.
        """
        try:
            async with self._session.get(f"{self.base_url}/version", raise_for_status=True) as response:
                text = await response.text()
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Unable to fetch EVOK version for %s: %s", self.host, err)
            return
        self.evok_version = text.strip() or None

    async def async_set_value(self, dev: str, circuit: str, value: Any) -> None:
        """Write a value to an EVOK endpoint and update local state from the response."""
        write_dev = self._protocol.write_dev(dev)
        url = f"{self.base_url}/rest/{write_dev}/{circuit}"
        payload = {"value": _serialize_value(value)}
        response = await _async_request_json(self._session, "POST", url, data=payload)

        if isinstance(response, dict) and isinstance(response.get("result"), dict):
            self._ingest_inventory([response["result"]])
            return

        refreshed = await _async_request_json(self._session, "GET", url)
        if isinstance(refreshed, dict):
            self._ingest_inventory([refreshed])

    def get_items_for_platform(self, platform: Platform) -> list[UniPiEntityDescription]:
        """Return all cached items for a platform."""
        return [item for item in self._items.values() if item.platform == platform]

    def get_item(self, key: str) -> UniPiEntityDescription | None:
        """Return one cached item by key."""
        return self._items.get(key)

    @callback
    def async_add_listener(self, key: str, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for one item key."""
        self._listeners[key].add(update_callback)

        @callback
        def _remove() -> None:
            listeners = self._listeners.get(key)
            if listeners is None:
                return
            listeners.discard(update_callback)
            if not listeners:
                self._listeners.pop(key, None)

        return _remove

    @callback
    def _ingest_inventory(
        self, payload: Iterable[dict[str, Any]], *, detect_protocol: bool = False
    ) -> None:
        """Normalize EVOK payloads into cached device and entity state.

        Protocol generation is only (re-)detected from a full inventory fetch
        (`detect_protocol=True`). Partial payloads, such as single-item
        websocket pushes or write-response refreshes, reuse the
        already-detected protocol instead of being reclassified item by item,
        so a single stray/legacy-looking key can't flip live protocol state.
        """
        payload_items = tuple(payload)
        if detect_protocol:
            self._protocol = detect_evok_protocol(payload_items, fallback=self._protocol)

        changed_keys: set[str] = set()

        for raw_item in payload_items:
            if self._protocol.is_metadata_item(raw_item):
                self._metadata = self._protocol.normalize_metadata(raw_item)
                continue

            item = self._protocol.normalize_item(raw_item)
            if item is None:
                continue

            self._items[item.key] = item
            changed_keys.add(item.key)

        for key in changed_keys:
            self._notify(key)

    async def _websocket_loop(self) -> None:
        """Keep a long-lived EVOK websocket connected."""
        reconnect_delay = 1

        while not self._stop_event.is_set():
            try:
                async with self._session.ws_connect(self.websocket_url, heartbeat=30) as websocket:
                    self._available = True
                    self._connected_event.set()
                    reconnect_delay = 1
                    self._notify_all()

                    async for message in websocket:
                        if self._stop_event.is_set():
                            return
                        await self._handle_websocket_message(message)
            except asyncio.CancelledError:
                raise
            except (ClientError, TimeoutError, OSError, ValueError) as err:
                _LOGGER.warning("EVOK websocket error for %s: %s", self.host, err)
            finally:
                if self._available:
                    self._available = False
                    self._notify_all()

            if self._stop_event.is_set():
                return

            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)

    async def _handle_websocket_message(self, message: WSMessage) -> None:
        """Handle one websocket message from EVOK."""
        if message.type is WSMsgType.TEXT:
            try:
                payload = json.loads(message.data)
            except json.JSONDecodeError:
                _LOGGER.debug("Ignoring non-JSON EVOK payload: %s", message.data)
                return

            if isinstance(payload, dict):
                self._ingest_inventory([payload])
            elif isinstance(payload, list):
                self._ingest_inventory([item for item in payload if isinstance(item, dict)])
        elif message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING):
            _LOGGER.debug("EVOK websocket closed for %s", self.host)
        elif message.type is WSMsgType.ERROR:
            _LOGGER.debug("EVOK websocket transport error for %s", self.host)

    @callback
    def _notify(self, key: str) -> None:
        """Notify all listeners for one item."""
        for listener in tuple(self._listeners.get(key, ())):
            listener()

    @callback
    def _notify_all(self) -> None:
        """Notify all registered listeners."""
        for listeners in tuple(self._listeners.values()):
            for listener in tuple(listeners):
                listener()


async def async_probe_unipi(
    session: ClientSession,
    host: str,
    port: int = DEFAULT_PORT,
) -> UniPiProbeResult:
    """Validate connectivity and read device metadata for config flow."""
    base_url = f"http://{host}:{port}"
    inventory = await _async_request_json(session, "GET", f"{base_url}/rest/all")

    if not isinstance(inventory, list):
        raise UniPiConnectionError("invalid_inventory")

    protocol = detect_evok_protocol(inventory)
    metadata = protocol.extract_metadata(inventory)
    if metadata is None:
        raise UniPiConnectionError("device_info_missing")

    return UniPiProbeResult(
        metadata=metadata,
        inventory=inventory,
        unique_id=metadata.unique_id(host, port),
        title=metadata.title,
    )


async def _async_request_json(
    session: ClientSession,
    method: str,
    url: str,
    *,
    data: dict[str, str] | None = None,
) -> Any:
    """Perform an HTTP request against EVOK and decode JSON."""
    try:
        async with session.request(method, url, data=data, raise_for_status=True) as response:
            return await response.json(content_type=None)
    except (ClientError, asyncio.TimeoutError, json.JSONDecodeError) as err:
        raise UniPiConnectionError(str(err)) from err


def _serialize_value(value: Any) -> str:
    """Convert a Python value into an EVOK form payload value."""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _metadata_from_raw(raw_item: dict[str, Any]) -> UniPiDeviceMetadata:
    """Create normalized device metadata from EVOK device_info."""
    return normalize_metadata_from_raw(raw_item)


def _normalize_item(raw_item: dict[str, Any]) -> UniPiEntityDescription | None:
    """Normalize a supported EVOK item into a Home Assistant entity description."""
    return normalize_item_from_raw(raw_item)
