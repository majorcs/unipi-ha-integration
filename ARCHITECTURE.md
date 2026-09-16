# UniPi EVOK Home Assistant Integration Architecture

## 1. Purpose

This document captures the implemented technical architecture of the `unipi` Home Assistant custom integration as it exists in the repository today.

It serves as the design and implementation record for the current codebase. It describes:

- design goals and constraints
- runtime architecture
- EVOK protocol usage
- automatic protocol compatibility strategy
- Home Assistant integration structure
- entity modeling and platform mapping
- write/control flow
- reconnect and lifecycle behavior
- testing architecture
- end-to-end validation environment
- current limitations and future evolution points

---

## 2. Design goals

The implementation was built around these concrete goals:

1. Integrate UniPi controllers via the EVOK API.
2. Use Home Assistant config entries rather than YAML configuration.
3. Support more than one UniPi device, with one config entry per device.
4. Ask for host/IP during onboarding.
5. Autodetect device metadata and available EVOK objects.
6. Keep a permanent WebSocket connection for realtime updates.
7. Map supported EVOK device classes into native Home Assistant entity platforms.
8. Package the repository in a HACS-compatible structure.
9. Maintain high automated test coverage.
10. Provide a working local end-to-end Home Assistant environment for manual validation.
11. Automatically support both EVOK `3.0.1+` and pre-`3.0.1` payload schemas.

---

## 3. External references used during implementation

Primary references:

- Home Assistant integration docs: https://developers.home-assistant.io/docs/creating_component_index/
- EVOK WebSocket docs: https://evok.readthedocs.io/en/stable/apis/websocket/
- EVOK API reference: https://unipitechnology.stoplight.io/docs/evok/qwveyanfg1gys-evok
- EVOK releases / changelog: https://github.com/UniPiTechnology/evok/releases
- HACS publishing docs: https://www.hacs.xyz/docs/publish/integration/
- Home Assistant brand image docs: https://developers.home-assistant.io/docs/core/integration/brand_images

Relevant changelog information:

- EVOK `3.0.1` introduced breaking API changes.
- Relays moved to `ro` while alternate access via `relay` remained available.
- Digital outputs moved to `do` while alternate access via `output` remained available.
- Digital inputs moved to `di` while alternate access via `input` remained available.

These API changes are the basis for the implemented compatibility layer.

---

## 4. Repository architecture

### 4.1 Core integration files

The runtime integration is implemented under `custom_components/unipi/`:

- `__init__.py` — config entry setup and unload
- `config_flow.py` — host/port onboarding and validation
- `const.py` — constants, platform map, numeric defaults
- `protocol.py` — EVOK schema detection and compatibility normalization
- `hub.py` — EVOK client/hub, discovery, state cache, websocket loop, writes
- `models.py` — normalized device and entity data models
- `entity.py` — shared base entity class
- `switch.py` — relays and digital outputs
- `binary_sensor.py` — digital inputs
- `light.py` — LEDs
- `sensor.py` — analog inputs
- `number.py` — analog outputs
- `manifest.json` — Home Assistant integration metadata
- `strings.json` and `translations/en.json` — config flow UI strings
- `brand/` — local brand assets for Home Assistant custom integration branding

### 4.2 Packaging and project files

At repository root:

- `README.md` — user-facing project summary
- `hacs.json` — HACS metadata
- `pytest.ini` — coverage and test configuration
- `requirements_test.txt` — test dependencies
- `ARCHITECTURE.md` — this document
- `DEVICE_COMPATIBILITY_PRE_V3_FIRMWARE.md` — local compatibility notes for legacy EVOK schema devices

### 4.3 E2E validation files

Local Home Assistant end-to-end environment:

- `.e2e-homeassistant/configuration.yaml`
- `.e2e-homeassistant/custom_components/unipi_e2e_bootstrap/`
- `start_e2e_homeassistant.sh`
- `.venv-e2e-ha/` — separate Home Assistant runtime environment

---

## 5. Runtime architecture overview

The runtime architecture is centered around one in-memory runtime hub per config entry.

### 5.1 Architectural layers

The integration is divided into five layers:

1. **Home Assistant entry layer**
   - creates and stores one runtime hub per config entry
   - forwards setup to platforms
   - unloads platforms and shuts down the hub

2. **Config flow layer**
   - collects host and port
   - probes EVOK using HTTP
   - auto-detects current vs legacy EVOK schema
   - extracts stable metadata
   - blocks duplicate devices by unique ID

3. **Protocol compatibility layer**
   - detects whether the device uses EVOK `3.0.1+` or pre-`3.0.1` payloads
   - normalizes legacy metadata and entity names into canonical internal names
   - maps canonical writes back to the correct EVOK endpoint names
   - isolates protocol differences from Home Assistant entity code

4. **EVOK runtime hub layer**
   - fetches full inventory from `/rest/all`
   - normalizes raw EVOK payloads into internal descriptions
   - opens and maintains `ws://host:port/ws`
   - distributes updates to registered entity listeners
   - exposes write methods using EVOK REST `POST`

5. **Entity/platform layer**
   - dynamically creates entities from discovered inventory
   - uses cached state from the hub
   - writes changes back through the hub
   - updates state from hub callbacks instead of polling

### 5.2 Per-device isolation model

Each UniPi config entry gets its own:

- `UniPiHub`
- EVOK HTTP base URL
- EVOK WebSocket connection
- active protocol adapter
- in-memory entity cache
- reconnect loop
- listener registry

This means multi-device support is implemented by entry isolation rather than by multiplexing multiple devices through a single client instance.

---

## 6. Home Assistant integration lifecycle

### 6.1 Integration startup

Implemented in `custom_components/unipi/__init__.py`.

Flow:

1. Home Assistant loads the config entry.
2. `async_setup_entry()` reads `host` and `port` from entry data.
3. A `UniPiHub` is created using the shared HA aiohttp client session.
4. `hub.async_initialize()` is awaited.
5. If initialization succeeds:
   - `entry.runtime_data = hub`
   - the hub is also stored in `hass.data[DOMAIN][entry_id]`
   - platform setup is forwarded to all supported platforms
6. If initialization fails, `ConfigEntryNotReady` is raised.

### 6.2 Integration unload

1. HA unloads the forwarded platforms.
2. `hub.async_shutdown()` is awaited.
3. The hub is removed from `hass.data[DOMAIN]`.

This keeps teardown explicit and predictable.

---

## 7. Config flow design

Implemented in `custom_components/unipi/config_flow.py`.

### 7.1 User inputs

The flow asks for:

- `host`
- `port` (default `8080`)

### 7.2 Validation process

The config flow calls `async_probe_unipi()` from `hub.py`.

The probe logic:

1. Performs `GET http://{host}:{port}/rest/all`
2. Verifies the response is a JSON list
3. Detects whether the payload matches EVOK `3.0.1+` or pre-`3.0.1`
4. Extracts metadata from either:
   - `device_info` on EVOK `3.0.1+`
   - `neuron` on pre-`3.0.1`
5. Converts that metadata into normalized `UniPiDeviceMetadata`
6. Builds a stable unique ID
7. Returns a `UniPiProbeResult`

### 7.3 Unique ID strategy

Preferred unique ID:

- `family-model-serial_number`

Fallback unique ID:

- `host:port`

Examples:

- `neuron-l203-167`
- `neuron-m205-31`

### 7.4 Config entry data stored

The config flow currently stores:

- `host`
- `port`
- `device_uid`
- `model`

The entry title is the EVOK-discovered device title, based on family plus model when available, with fallback to circuit or model.

When a serial number is available, it is appended to the default title to avoid collisions between same-model devices.

Examples:

- `Neuron L203 (SN 167)`
- `Neuron M205 (SN 31)`

---

## 8. Protocol compatibility architecture

Implemented in `custom_components/unipi/protocol.py`.

### 8.1 Motivation

EVOK `3.0.1` introduced breaking API changes and new canonical endpoint names. Older firmware still uses pre-v3 naming.

Without an explicit compatibility layer, the integration would either:

- fail during probe due to missing `device_info`, or
- ignore legacy entities due to unmatched EVOK type names

### 8.2 Detection strategy

The integration auto-detects protocol generation from inventory payload contents.

Current-schema indicators:

- `device_info`
- `ro`
- `do`
- `di`
- dict-based analog `modes`

Legacy-schema indicators:

- `neuron`
- `relay`
- `output`
- `input`
- string-based analog `range`
- `range_modes`

Detection runs:

- during config flow probe
- during hub inventory ingestion

### 8.3 Canonical internal model

Both EVOK generations are normalized into one canonical internal model.

Canonical internal device types remain:

- `ro`
- `do`
- `di`
- `led`
- `ai`
- `ao`

This keeps Home Assistant entity code independent of device firmware generation.

### 8.4 Legacy alias mapping

Pre-v3 firmware payloads are normalized as follows:

| Legacy EVOK type | Canonical internal type |
|---|---|
| `neuron` | metadata record |
| `relay` | `ro` |
| `output` | `do` |
| `input` | `di` |

### 8.5 Legacy write mapping

When a legacy device is detected, canonical writes are mapped back to the correct legacy endpoint names:

| Canonical write type | Legacy EVOK endpoint |
|---|---|
| `ro` | `relay` |
| `do` | `output` |
| `di` | `input` |

### 8.6 Legacy analog normalization

The compatibility layer also tolerates older analog schema differences:

- `range` may be a string such as `"10.0"` instead of a two-item list
- `modes` may be a list of strings instead of a dict with metadata

This is sufficient for current entity creation and basic range handling.

---

## 9. EVOK protocol architecture

### 9.1 HTTP usage

The implementation currently uses EVOK REST for:

#### Discovery

- `GET /rest/all`

This endpoint is treated as the authoritative discovery source during startup.

#### Writes

- `POST /rest/{dev}/{circuit}` with form field `value`

Example write patterns used by the integration:

- relay / digital output / LED: `0` or `1`
- analog output: float value serialized into string form

For legacy devices, canonical writes are translated automatically to legacy endpoint names before the POST is performed.

#### Post-write refresh behavior

`UniPiHub.async_set_value()` uses this logic:

1. POST to EVOK
2. If the response contains `{"result": {...}}`, ingest that object directly
3. Otherwise, fallback to `GET /rest/{dev}/{circuit}` and ingest the refreshed object

This design allows support for both richer and simpler EVOK responses.

#### Version

- `GET /version`

Fetched once, best-effort, during `async_initialize()` via `UniPiHub.async_fetch_version()`. The response is plain text (the EVOK version string), not JSON. Failures are logged at debug level and swallowed rather than blocking setup, since not every EVOK build is guaranteed to expose this route. The result is surfaced as the `EVOK Version` diagnostic sensor (see §12.5).

#### Device web UI link

`device_info["configuration_url"]` (the device page's "Visit" button) intentionally does **not** reuse `UniPiHub.base_url` (which includes the EVOK API port, e.g. `8080`). UniPi devices serve their own browsable web UI on the default HTTP port, while the EVOK port 404s at its root (see `DEVICE_COMPATIBILITY_PRE_V3_FIRMWARE.md`). `UniPiHub.web_ui_url` (`http://{host}`, no port) is used instead, so "Visit" opens the actual device UI rather than a 404.

### 9.2 WebSocket usage

The implementation uses:

- `ws://{host}:{port}/ws`

#### WebSocket assumptions currently encoded

- EVOK pushes state changes to connected clients
- messages may be a JSON object or a JSON array of objects
- only dict payloads are ingested
- malformed JSON is ignored and logged at debug level
- legacy websocket payloads are normalized through the same compatibility layer as HTTP inventory payloads

#### Reconnect behavior

The websocket loop uses a bounded exponential backoff:

- initial delay: `1s`
- doubled on failure
- capped at `30s`
- reset to `1s` after successful connection

#### Connection readiness behavior

`async_initialize()` waits until the WebSocket loop marks the connection ready using `_connected_event`.

If readiness is not achieved within `10s`, initialization fails with `UniPiConnectionError("cannot_connect")`.

---

## 10. Data model design

Implemented in `custom_components/unipi/models.py`.

### 10.1 `UniPiDeviceMetadata`

Represents normalized EVOK metadata.

Fields:

- `family`
- `model`
- `serial_number`
- `circuit`
- `board_count`

Responsibilities:

- derive display title via `title`
- derive stable unique ID via `unique_id(host, port)`

### 10.2 `UniPiEntityDescription`

Represents one supported EVOK item normalized for Home Assistant use.

Core fields:

- `key`
- `platform`
- `dev`
- `circuit`
- `name`
- `value`
- `unit`
- `mode`
- `modes`
- `value_range`
- `writable`
- `raw`

Home Assistant compatibility fields include:

- `unit_of_measurement`
- `suggested_unit_of_measurement`
- `device_class`
- `state_class`
- `last_reset`
- `options`
- `entity_category`
- `entity_registry_enabled_default`
- `entity_registry_visible_default`
- `force_update`
- `icon`
- `translation_key`
- `suggested_display_precision`

### 10.3 Numeric range policy

For analog outputs (`ao`):

- minimum is forced to `0.0`
- maximum is forced to `10.0`
- default step is `0.1`
- default unit is `V` if EVOK does not provide one

This is an explicit project decision reflected in both runtime code and tests.

---

## 11. Entity discovery and normalization

Implemented through the protocol compatibility layer and consumed by `UniPiHub`.

### 11.1 Supported EVOK device types

Current mapping from canonical EVOK type to Home Assistant platform:

| Canonical type | Meaning | HA platform |
|---|---|---|
| `ro` | relay output | `switch` |
| `do` | digital output | `switch` |
| `di` | digital input | `binary_sensor` |
| `led` | LED | `light` |
| `ai` | analog input | `sensor` |
| `ao` | analog output | `number` |

Legacy EVOK aliases are also accepted automatically:

| Legacy EVOK `dev` | Canonical type | HA platform |
|---|---|---|
| `relay` | `ro` | `switch` |
| `output` | `do` | `switch` |
| `input` | `di` | `binary_sensor` |

### 11.2 Ignored EVOK types

The normalization layer ignores types not present in the canonical mapping.

Observed unsupported EVOK types include:

- `wd`
- `modbus_slave`
- `owpower`
- `owbus`
- `uart`
- metadata records (`device_info` and `neuron`) which are handled separately

### 11.3 Naming strategy

Human-readable entity names are generated from canonical EVOK type plus circuit.

Examples:

- `Relay 2.01`
- `Digital Input 3.04`
- `LED 1.03`
- `Analog Output 1.01`

### 11.4 Unique entity ID strategy

Entity unique IDs are composed as:

- `{device_identifier}-{dev}-{circuit}`

Example:

- `neuron-l203-167-ao-1_01`

This keeps entity IDs stable across Home Assistant restarts as long as the device serial remains stable.

---

## 12. Platform-specific design

### 12.1 Shared base entity

Implemented in `custom_components/unipi/entity.py`.

Responsibilities:

- store hub reference
- store item cache key
- expose `device_info`
- expose `available`
- expose EVOK metadata in `extra_state_attributes`
- register a listener so hub updates call `async_write_ha_state()`

Availability rule:

- entity is available only if the hub websocket is available and the item still exists in cache

### 12.2 Switch platform

Implemented in `custom_components/unipi/switch.py`.

Used for:

- `ro`
- `do`

Behavior:

- `is_on` from truthiness of EVOK value
- `async_turn_on()` writes `1`
- `async_turn_off()` writes `0`

### 12.3 Binary sensor platform

Implemented in `custom_components/unipi/binary_sensor.py`.

Used for:

- `di`

Behavior:

- read-only
- `is_on` from truthiness of EVOK value

### 12.4 Light platform

Implemented in `custom_components/unipi/light.py`.

Used for:

- `led`

Behavior:

- on/off only
- supported color mode set to `ONOFF`
- `async_turn_on()` writes `1`
- `async_turn_off()` writes `0`

### 12.5 Sensor platform

Implemented in `custom_components/unipi/sensor.py`.

Used for:

- `ai`

Behavior:

- `native_value` is the current EVOK value
- `native_unit_of_measurement` comes from EVOK `unit`

Additionally, the sensor platform creates three static, device-level diagnostic sensors that are not backed by any EVOK circuit item (`UniPiDiagnosticSensorEntity` and its subclasses):

- `IP Address` — the configured EVOK host, always available
- `EVOK Version` — the EVOK software version, fetched best-effort from `GET /version` during `async_initialize()` (`UniPiHub.async_fetch_version()`); unavailable if the endpoint is missing or the request fails, since some EVOK builds may not expose it
- `Board Count` — the extension board count parsed from the metadata record; unavailable if EVOK never reported one

These use `EntityCategory.DIAGNOSTIC` and are linked to the device via `hub.device_info`, same as every other entity.

### 12.6 Number platform

Implemented in `custom_components/unipi/number.py`.

Used for:

- `ao`

Behavior:

- `NumberMode.BOX`
- min/max/step derived from normalized description
- write values are clamped to `[0.0, 10.0]`
- unit is forwarded from EVOK, typically `V`

---

## 13. Event propagation model

The state propagation model is push-first.

### 13.1 Startup path

1. Inventory is fetched from `/rest/all`
2. Protocol generation is detected
3. Entities are created from normalized cached items
4. WebSocket starts and later updates cached values

### 13.2 Realtime path

1. EVOK sends WebSocket message
2. `UniPiHub._handle_websocket_message()` parses JSON
3. `_ingest_inventory()` auto-detects protocol generation, normalizes items, and updates cache
4. changed keys are collected
5. registered entity listeners are called
6. entities write new Home Assistant state

### 13.3 Write path

1. User acts on entity in HA
2. entity method calls `hub.async_set_value()`
3. hub maps canonical device type to the active protocol's write endpoint and sends EVOK REST POST
4. response or fallback GET is ingested
5. state cache updates
6. listeners are notified

This means writes flow through the same cache update mechanism as push events.

---

## 14. Error handling strategy

### 14.1 Connection-level errors

`UniPiConnectionError` is used as the integration-specific error type.

It is raised on:

- HTTP client errors
- HTTP timeout errors
- JSON decode errors
- invalid discovery payload structure
- missing compatible metadata record (`device_info` or `neuron`)
- websocket readiness timeout

### 14.2 Setup retry strategy

`async_setup_entry()` converts connection errors into `ConfigEntryNotReady` so Home Assistant can retry later.

### 14.3 WebSocket robustness

The websocket loop:

- logs connection failures
- clears availability when disconnected
- retries until unload
- respects task cancellation on shutdown

### 14.4 Unsupported payload strategy

Unsupported EVOK types are ignored rather than causing startup failure.

Malformed WebSocket JSON payloads are ignored rather than breaking the loop.

---

## 15. HACS and branding architecture

### 15.1 HACS compatibility

Current HACS metadata:

- repository root contains `hacs.json`
- integration root contains `manifest.json`
- only one integration is present under `custom_components/unipi/`

### 15.2 Local brand images

The integration uses local custom-integration brand assets in:

- `custom_components/unipi/brand/icon.png`
- `custom_components/unipi/brand/logo.png`

---

## 16. Testing architecture

### 16.1 Tooling

Test tooling is defined by:

- `pytest`
- `pytest-asyncio`
- `pytest-cov`
- `pytest-homeassistant-custom-component`

### 16.2 Coverage policy

`pytest.ini` enforces:

- tests under `tests/`
- automatic asyncio mode
- coverage target `>= 90%`

Current achieved coverage is above the target.

### 16.3 Test categories

The suite currently covers:

- model helper behavior
- protocol detection and normalization for EVOK `3.0.1+` and pre-`3.0.1`
- hub probing, writes, listeners, websocket processing, and reconnect logic
- config flow creation, duplicate prevention, and error handling
- integration setup and unload behavior
- entity classes and platform setup functions
- translation and manifest smoke checks

### 16.4 Test strategy

The runtime design is tested primarily by:

- EVOK payload fixtures
- separate current-schema and legacy-schema fixtures
- mocked aiohttp HTTP responses
- mocked websocket message objects
- fake hub objects for entity tests

This keeps tests deterministic and hardware-independent.

---

## 17. End-to-end architecture

A separate local E2E Home Assistant environment was created to validate real UniPi devices.

### 17.1 E2E runtime composition

- separate venv: `.venv-e2e-ha`
- dedicated HA config dir: `.e2e-homeassistant`
- integration symlinked into that config’s `custom_components/`
- bootstrap helper auto-creates a `unipi` config entry after HA startup

### 17.2 Bootstrap design

The helper integration `unipi_e2e_bootstrap`:

1. reads configured host/port from YAML
2. waits until HA startup finishes
3. delays 5 seconds
4. checks if a matching `unipi` entry already exists
5. starts the UniPi config flow programmatically if needed

### 17.3 Live validation outcome

Live validation has confirmed:

- successful creation of the current-schema device entry
- successful probing of a pre-v3 firmware device
- successful automatic detection of both protocol generations

---

## 18. Current supported inventory shapes

### 18.1 EVOK `3.0.1+`

Observed current-schema EVOK types include:

- `device_info`
- `di`
- `ro`
- `do`
- `ai`
- `ao`
- `led`
- `wd`
- `modbus_slave`
- `owpower`
- `owbus`

### 18.2 Pre-v3 firmware

Observed legacy-schema EVOK types include:

- `neuron`
- `input`
- `relay`
- `ai`
- `ao`
- `led`
- `wd`
- `uart`
- `owbus`

### 18.3 Exposed entity subset

The integration currently exposes the canonical subset:

- `di`
- `ro`
- `do`
- `ai`
- `ao`
- `led`

Equivalent pre-v3 aliases are supported automatically:

- `input` -> `di`
- `relay` -> `ro`
- `output` -> `do`

---

## 19. Known design tradeoffs and limitations

1. **No options flow yet**
   - host/port can be configured only at entry creation time

2. **No HTTPS support implemented yet**
   - runtime URLs are currently `http://` and `ws://`

3. **No advanced EVOK type coverage yet**
   - watchdogs, Modbus-related objects, 1-Wire objects, and `uart` are ignored

4. **Legacy support is intentionally scoped**
   - pre-v3 firmware support currently focuses on metadata, relay/input/output aliases, and legacy analog normalization

5. **No device class inference yet**
   - digital inputs, sensors, and numbers are intentionally conservative

6. **No entity filtering policy yet**
   - all supported discovered entities are enabled

7. **No websocket filter command used yet**
   - the implementation currently consumes the full EVOK stream

8. **No dedicated coordinator abstraction**
   - the hub itself acts as connection manager, discovery cache, and event broker

9. **Description model is generic, not typed per platform**
   - convenient for rapid implementation, but less explicit than dedicated platform description types

10. **The test suite still emits one non-failing warning**
   - coverage and correctness pass, but one async warning remains to be cleaned up

---

## 20. Recommended future architecture evolution

If the integration continues to grow, these are the logical next design steps:

1. Introduce explicit typed descriptions per platform
2. Add options flow for host/port/name behavior
3. Add HTTPS and secure WebSocket support if EVOK supports it reliably
4. Support more EVOK object classes such as watchdog or service actions
5. Add device class/state class inference where semantics are clear
6. Add diagnostics support for easier troubleshooting
7. Add selective websocket filtering if it reduces traffic safely
8. Split hub responsibilities further if complexity grows:
   - transport client
   - discovery mapper
   - runtime cache / broker
9. Add CI workflow for tests and linting
10. Add release assets and full HACS publication polish

---

## 21. File-to-responsibility map

| File | Responsibility |
|---|---|
| `custom_components/unipi/__init__.py` | config entry lifecycle |
| `custom_components/unipi/config_flow.py` | onboarding and duplicate prevention |
| `custom_components/unipi/const.py` | constants and EVOK-to-platform map |
| `custom_components/unipi/protocol.py` | EVOK schema detection and compatibility normalization |
| `custom_components/unipi/models.py` | normalized metadata and entity descriptions |
| `custom_components/unipi/hub.py` | EVOK discovery, websocket, writes, cache, event dispatch |
| `custom_components/unipi/entity.py` | shared entity behavior |
| `custom_components/unipi/switch.py` | relays and digital outputs |
| `custom_components/unipi/binary_sensor.py` | digital inputs |
| `custom_components/unipi/light.py` | LEDs |
| `custom_components/unipi/sensor.py` | analog inputs |
| `custom_components/unipi/number.py` | analog outputs |
| `custom_components/unipi/manifest.json` | integration metadata |
| `custom_components/unipi/brand/` | local integration branding |
| `tests/` | automated verification |
| `DEVICE_COMPATIBILITY_PRE_V3_FIRMWARE.md` | local compatibility notes for pre-v3 firmware |
| `.e2e-homeassistant/` | manual/runtime validation environment |
| `start_e2e_homeassistant.sh` | local HA runtime bootstrap |

---

## 22. Summary

The current implementation is a config-entry-based, multi-device-capable, push-oriented Home Assistant custom integration for UniPi controllers over EVOK.

Its core design choices are:

- one hub per config entry
- REST bootstrap via `/rest/all`
- permanent WebSocket at `/ws`
- dynamic entity creation from discovered EVOK inventory
- conservative canonical type mapping
- automatic compatibility normalization for pre-`3.0.1` EVOK devices
- local push semantics in Home Assistant
- HACS-compatible repository structure
- strong automated test coverage
- working live validation against both current and legacy EVOK schema devices

This document represents the architectural baseline for the repository going forward.
