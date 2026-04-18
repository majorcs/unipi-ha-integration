# UniPi EVOK Home Assistant Integration Architecture

## 1. Purpose

This document captures the implemented technical architecture of the `unipi` Home Assistant custom integration as it exists in the repository today.

It is intended to serve as the missing design record that would normally be produced before implementation. It describes:

- design goals and constraints
- runtime architecture
- EVOK protocol usage
- Home Assistant integration structure
- entity modeling and platform mapping
- write/control flow
- reconnect and lifecycle behavior
- test architecture
- end-to-end validation environment
- current limitations and next-step design opportunities

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

---

## 3. External references used during implementation

Primary references:

- Home Assistant integration docs: https://developers.home-assistant.io/docs/creating_component_index/
- EVOK WebSocket docs: https://evok.readthedocs.io/en/stable/apis/websocket/
- EVOK API reference: https://unipitechnology.stoplight.io/docs/evok/qwveyanfg1gys-evok
- HACS publishing docs: https://www.hacs.xyz/docs/publish/integration/
- Home Assistant brand image docs: https://developers.home-assistant.io/docs/core/integration/brand_images

Live verification target used during implementation:

- `http://192.168.88.59:8080`

---

## 4. Repository architecture

### 4.1 Core integration files

The runtime integration is implemented under `custom_components/unipi/`:

- `__init__.py` — config entry setup and unload
- `config_flow.py` — host/port onboarding and validation
- `const.py` — constants, platform map, numeric defaults
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
- `brand/` — local brand assets for Home Assistant 2026.3+

### 4.2 Packaging and project files

At repository root:

- `README.md` — user-facing project summary
- `hacs.json` — HACS metadata
- `pytest.ini` — coverage and test configuration
- `requirements_test.txt` — test dependencies
- `ARCHITECTURE.md` — this document

### 4.3 E2E validation files

Local Home Assistant end-to-end environment:

- `.e2e-homeassistant/configuration.yaml`
- `.e2e-homeassistant/custom_components/unipi_e2e_bootstrap/`
- `start_e2e_homeassistant.sh`
- `.venv-e2e-ha/` — separate Home Assistant runtime environment

---

## 5. Runtime architecture overview

The implemented runtime architecture is intentionally simple and centered around one in-memory runtime object per config entry.

### 5.1 Architectural layers

The integration is divided into four layers:

1. **Home Assistant entry layer**
   - creates and stores one runtime hub per config entry
   - forwards setup to platforms
   - unloads platforms and shuts down the hub

2. **Config flow layer**
   - collects host and port
   - probes EVOK using HTTP
   - extracts stable metadata
   - blocks duplicate devices by unique ID

3. **EVOK runtime hub layer**
   - fetches full inventory from `/rest/all`
   - normalizes raw EVOK payloads into internal descriptions
   - opens and maintains `ws://host:port/ws`
   - distributes updates to registered entity listeners
   - exposes write methods using EVOK REST `POST`

4. **Entity/platform layer**
   - dynamically creates entities from discovered inventory
   - uses cached state from the hub
   - writes changes back through the hub
   - updates state from hub callbacks instead of polling

### 5.2 Per-device isolation model

Each UniPi config entry gets its own:

- `UniPiHub`
- EVOK HTTP base URL
- EVOK WebSocket connection
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

The current flow asks for:

- `host`
- `port` (default `8080`)

### 7.2 Validation process

The config flow calls `async_probe_unipi()` from `hub.py`.

The probe logic:

1. Performs `GET http://{host}:{port}/rest/all`
2. Verifies the response is a JSON list
3. Extracts the `device_info` object
4. Converts `device_info` into normalized `UniPiDeviceMetadata`
5. Builds a stable unique ID
6. Returns a `UniPiProbeResult`

### 7.3 Unique ID strategy

Preferred unique ID:

- `family-model-serial_number`

Fallback unique ID:

- `host:port`

For the validated live device, the current unique ID pattern becomes:

- `neuron-l203-167`

### 7.4 Config entry data stored

The config flow currently stores:

- `host`
- `port`
- `device_uid`
- `model`

The entry title is the EVOK-discovered device title, currently based on the `device_info` family plus model when available, with fallback to circuit or model.
When a serial number is available, it is appended to the default title to avoid collisions between same-model devices, for example `Neuron L203 (SN 167)`.

---

## 8. EVOK protocol architecture

## 8.1 HTTP usage

The implementation currently uses EVOK REST for:

### Discovery

- `GET /rest/all`

This endpoint is treated as the authoritative discovery source during startup.

### Writes

- `POST /rest/{dev}/{circuit}` with form field `value`

Example write patterns used by the integration:

- relay / digital output / LED: `0` or `1`
- analog output: float value serialized into string form

### Post-write refresh behavior

`UniPiHub.async_set_value()` uses this logic:

1. POST to EVOK
2. If the response contains `{"result": {...}}`, ingest that object directly
3. Otherwise, fallback to `GET /rest/{dev}/{circuit}` and ingest the refreshed object

This design allows support for both richer and simpler EVOK responses.

## 8.2 WebSocket usage

The implementation uses:

- `ws://{host}:{port}/ws`

### WebSocket assumptions currently encoded

- EVOK pushes state changes to connected clients
- messages may be a JSON object or a JSON array of objects
- only dict payloads are ingested
- malformed JSON is ignored and logged at debug level

### Reconnect behavior

The websocket loop uses a bounded exponential backoff:

- initial delay: `1s`
- doubled on failure
- capped at `30s`
- reset to `1s` after successful connection

### Connection readiness behavior

`async_initialize()` waits until the WebSocket loop marks the connection ready using `_connected_event`.

If readiness is not achieved within `10s`, initialization fails with `UniPiConnectionError("cannot_connect")`.

---

## 9. Data model design

Implemented in `custom_components/unipi/models.py`.

### 9.1 `UniPiDeviceMetadata`

Represents normalized EVOK `device_info` data.

Fields:

- `family`
- `model`
- `serial_number`
- `circuit`
- `board_count`

Responsibilities:

- derive display title via `title`
- derive stable unique ID via `unique_id(host, port)`

### 9.2 `UniPiEntityDescription`

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

Home Assistant compatibility fields added during runtime hardening:

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

These fields were added because Home Assistant entity platforms access description attributes generically during registration.

### 9.3 Numeric range policy

For analog outputs (`ao`):

- minimum is forced to `0.0`
- maximum is forced to `10.0`
- default step is `0.1`
- default unit is `V` if EVOK does not provide one

This is an explicit project decision reflected in both runtime code and tests.

---

## 10. Entity discovery and normalization

Implemented mainly in `_normalize_item()` inside `custom_components/unipi/hub.py`.

### 10.1 Supported EVOK device types

Current mapping from EVOK `dev` to Home Assistant platform:

| EVOK `dev` | Meaning | HA platform |
|---|---|---|
| `ro` | relay output | `switch` |
| `do` | digital output | `switch` |
| `di` | digital input | `binary_sensor` |
| `led` | LED | `light` |
| `ai` | analog input | `sensor` |
| `ao` | analog output | `number` |

### 10.2 Ignored EVOK types

The normalization layer ignores types not present in `DEVICE_TYPE_TO_PLATFORM`.

Observed unsupported live-device EVOK types included:

- `wd`
- `modbus_slave`
- `owpower`
- `owbus`
- `device_info` (handled separately as metadata)

### 10.3 Naming strategy

Human-readable names are generated from EVOK type plus circuit.

Examples:

- `Relay 2.01`
- `Digital Input 3.04`
- `LED 1.03`
- `Analog Output 1.01`

Home Assistant then derives entity IDs such as:

- `switch.l203_relay_2_01`
- `binary_sensor.l203_digital_input_2_01`
- `light.l203_led_1_01`
- `sensor.l203_analog_input_1_01`
- `number.l203_analog_output_1_01`

### 10.4 Unique entity ID strategy

Entity unique IDs are composed as:

- `{device_identifier}-{dev}-{circuit}`

Example:

- `neuron-l203-167-ao-1_01`

This keeps entity IDs stable across Home Assistant restarts as long as the device serial remains stable.

---

## 11. Platform-specific design

## 11.1 Shared base entity

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

## 11.2 Switch platform

Implemented in `custom_components/unipi/switch.py`.

Used for:

- `ro`
- `do`

Behavior:

- `is_on` from truthiness of EVOK value
- `async_turn_on()` writes `1`
- `async_turn_off()` writes `0`

## 11.3 Binary sensor platform

Implemented in `custom_components/unipi/binary_sensor.py`.

Used for:

- `di`

Behavior:

- read-only
- `is_on` from truthiness of EVOK value

No device classes are currently inferred.

## 11.4 Light platform

Implemented in `custom_components/unipi/light.py`.

Used for:

- `led`

Behavior:

- on/off only
- supported color mode set to `ONOFF`
- `async_turn_on()` writes `1`
- `async_turn_off()` writes `0`

## 11.5 Sensor platform

Implemented in `custom_components/unipi/sensor.py`.

Used for:

- `ai`

Behavior:

- `native_value` is the current EVOK value
- `native_unit_of_measurement` comes from EVOK `unit`

No explicit state class or device class mapping is currently applied.

## 11.6 Number platform

Implemented in `custom_components/unipi/number.py`.

Used for:

- `ao`

Behavior:

- `NumberMode.BOX`
- min/max/step derived from normalized description
- write values are clamped to `[0.0, 10.0]`
- unit is forwarded from EVOK, typically `V`

---

## 12. Event propagation model

The state propagation model is push-first.

### 12.1 Startup path

1. Inventory is fetched from `/rest/all`
2. Entities are created from normalized cached items
3. WebSocket starts and later updates cached values

### 12.2 Realtime path

1. EVOK sends WebSocket message
2. `UniPiHub._handle_websocket_message()` parses JSON
3. `_ingest_inventory()` normalizes items and updates cache
4. keys that changed are collected
5. registered entity listeners are called
6. entities write new Home Assistant state

### 12.3 Write path

1. User acts on entity in HA
2. entity method calls `hub.async_set_value()`
3. hub sends EVOK REST POST
4. response or fallback GET is ingested
5. state cache updates
6. listeners are notified

This means writes flow through the same cache update mechanism as push events.

---

## 13. Error handling strategy

### 13.1 Connection-level errors

`UniPiConnectionError` is used as the integration-specific error type.

It is raised on:

- HTTP client errors
- HTTP timeout errors
- JSON decode errors
- invalid discovery payload structure
- missing `device_info`
- websocket readiness timeout

### 13.2 Setup retry strategy

`async_setup_entry()` converts connection errors into `ConfigEntryNotReady` so Home Assistant can retry later.

### 13.3 WebSocket robustness

The websocket loop:

- logs connection failures
- clears availability when disconnected
- retries until unload
- respects task cancellation on shutdown

### 13.4 Unsupported payload strategy

Unsupported EVOK types are ignored rather than causing startup failure.

Malformed WebSocket JSON payloads are ignored rather than breaking the loop.

---

## 14. HACS and branding architecture

### 14.1 HACS compatibility

Current HACS metadata:

- repository root contains `hacs.json`
- integration root contains `manifest.json`
- only one integration is present under `custom_components/unipi/`

### 14.2 Local brand images

The integration now uses local custom-integration brand assets in:

- `custom_components/unipi/brand/icon.png`
- `custom_components/unipi/brand/logo.png`

The source image was derived from the live UniPi device favicon.

This follows Home Assistant’s custom integration branding approach for 2026.3+.

---

## 15. Testing architecture

### 15.1 Tooling

Test tooling is defined by:

- `pytest`
- `pytest-asyncio`
- `pytest-cov`
- `pytest-homeassistant-custom-component`

### 15.2 Coverage policy

`pytest.ini` enforces:

- tests under `tests/`
- automatic asyncio mode
- coverage target `>= 90%`

Current achieved coverage is above the target.

### 15.3 Test categories

The suite currently covers:

- model helper behavior
- hub probing, writes, listeners, websocket processing, and reconnect logic
- config flow creation, duplicate prevention, and error handling
- integration setup and unload behavior
- entity classes and platform setup functions
- translation and manifest smoke checks

### 15.4 Test strategy

The runtime design is tested primarily by:

- EVOK payload fixtures
- mocked aiohttp HTTP responses
- mocked websocket message objects
- fake hub objects for entity tests

This keeps tests deterministic and hardware-independent.

---

## 16. End-to-end architecture

A separate local E2E Home Assistant environment was created to validate the real UniPi device.

### 16.1 E2E runtime composition

- separate venv: `.venv-e2e-ha`
- dedicated HA config dir: `.e2e-homeassistant`
- integration symlinked into that config’s `custom_components/`
- bootstrap helper auto-creates a `unipi` config entry after HA startup

### 16.2 Bootstrap design

The helper integration `unipi_e2e_bootstrap`:

1. reads configured host/port from YAML
2. waits until HA startup finishes
3. delays 5 seconds
4. checks if a matching `unipi` entry already exists
5. starts the UniPi config flow programmatically if needed

This allowed repeatable manual validation against the live device.

### 16.3 Live validation outcome

The live L203 validation currently results in:

- 1 registered UniPi device
- 74 registered UniPi entities
- successful creation of binary sensors, switches, lights, sensors, and number entities

---

## 17. Current supported live-device inventory shape

From the verified live device, the observed EVOK inventory included these types:

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

The current integration only exposes:

- `di`
- `ro`
- `do`
- `ai`
- `ao`
- `led`

This is a deliberate conservative subset.

---

## 18. Known design tradeoffs and limitations

1. **No options flow yet**
   - host/port can be configured only at entry creation time

2. **No HTTPS support implemented yet**
   - architecture leaves room for it, but runtime URLs are currently `http://` and `ws://`

3. **No advanced EVOK type coverage yet**
   - watchdogs, Modbus-related objects, and 1-Wire objects are ignored

4. **No device class inference yet**
   - digital inputs, sensors, and numbers are intentionally conservative

5. **No entity filtering policy yet**
   - all supported discovered entities are enabled

6. **No websocket filter command used yet**
   - the implementation currently consumes the full EVOK stream

7. **No dedicated coordinator abstraction**
   - the hub itself acts as connection manager, discovery cache, and event broker

8. **Description model is generic, not typed per platform**
   - convenient for rapid implementation, but less explicit than dedicated platform description types

9. **The test suite still emits one non-failing warning**
   - coverage and correctness pass, but one async warning remains to be cleaned up

---

## 19. Recommended future architecture evolution

If the integration continues to grow, these are the logical next design steps:

1. Introduce explicit typed descriptions per platform
2. Add options flow for host/port/name behavior
3. Add HTTPS and secure WebSocket support if EVOK supports it reliably
4. Support more EVOK object classes such as watchdog or service actions
5. Add device class/state class inference where semantics are clear
6. Add diagnostics support for easier troubleshooting
7. Add selective websocket filtering if it reduces traffic safely
8. Split hub responsibilities if complexity grows:
   - transport client
   - discovery mapper
   - runtime cache / broker
9. Add CI workflow for tests and linting
10. Add release assets and full HACS publication polish

---

## 20. File-to-responsibility map

| File | Responsibility |
|---|---|
| `custom_components/unipi/__init__.py` | config entry lifecycle |
| `custom_components/unipi/config_flow.py` | onboarding and duplicate prevention |
| `custom_components/unipi/const.py` | constants and EVOK-to-platform map |
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
| `.e2e-homeassistant/` | manual/runtime validation environment |
| `start_e2e_homeassistant.sh` | local HA runtime bootstrap |

---

## 21. Summary

The current implementation is a config-entry-based, multi-device-capable, push-oriented Home Assistant custom integration for UniPi controllers over EVOK.

Its core design choices are:

- one hub per config entry
- REST bootstrap via `/rest/all`
- permanent WebSocket at `/ws`
- dynamic entity creation from discovered EVOK inventory
- conservative type mapping
- local push semantics in Home Assistant
- HACS-compatible repository structure
- strong automated test coverage
- working live end-to-end validation against a real device

This document represents the architectural baseline for the repository going forward.
