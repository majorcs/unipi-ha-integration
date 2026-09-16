# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Home Assistant custom integration (`custom_components/unipi/`) that connects to UniPi controllers via the EVOK REST/WebSocket API. Distributed via HACS. See `ARCHITECTURE.md` for the full design record (layers, protocol compatibility strategy, lifecycle, data model) and `DEVICE_COMPATIBILITY_PRE_V3_FIRMWARE.md` for pre-v3 EVOK firmware quirks.

## Commands

Unit tests (uses `.venv`):

```bash
.venv/bin/pytest
```

- `pytest.ini` sets `testpaths = tests`, `asyncio_mode = auto`, and enforces `--cov-fail-under=90` against `custom_components.unipi`. A full run must stay above 90% coverage.
- Run a single test: `.venv/bin/pytest tests/test_hub.py::test_name`
- Test deps are in `requirements_test.txt`; install into `.venv` with `.venv/bin/pip install -r requirements_test.txt` if missing.

Local end-to-end validation against a real/dedicated Home Assistant instance:

```bash
./start_e2e_homeassistant.sh
```

- Creates/uses `.venv-e2e-ha` (separate from the test venv), symlinks `custom_components/unipi` into `.e2e-homeassistant/custom_components/`, and runs `hass -c .e2e-homeassistant`.
- A bootstrap helper (`.e2e-homeassistant/custom_components/unipi_e2e_bootstrap/`) auto-creates a `unipi` config entry from `.e2e-homeassistant/configuration.yaml` after HA finishes starting.
- The script prompts to kill an already-running instance for the same config dir; it refuses to do so non-interactively.

No CI workflow or linter config exists yet in this repo — don't assume a `lint` command is available.

## Architecture

Read `ARCHITECTURE.md` before making non-trivial changes — it is kept as the authoritative design record and should be updated when architecture changes. Key points to know before touching code:

- **One `UniPiHub` per config entry** (`hub.py`). Each hub owns its own HTTP base URL, permanent WebSocket connection (`ws://{host}:{port}/ws`), protocol adapter, in-memory entity cache, reconnect loop, and listener registry. Multi-device support is entry isolation, not multiplexing.
- **Protocol compatibility layer** (`protocol.py`) auto-detects EVOK `3.0.1+` vs. pre-`3.0.1` payload schemas (both during config-flow probing and during hub inventory ingestion) and normalizes both into one canonical internal model (`ro`, `do`, `di`, `led`, `ai`, `ao`). This isolates firmware-generation differences from all entity/platform code — never special-case legacy naming (`relay`/`output`/`input`) outside of `protocol.py`.
- **Push-first state model**: entities never poll. Startup does `GET /rest/all` for discovery, then the WebSocket takes over. Writes (`hub.async_set_value()`) POST to EVOK, ingest the response if it contains a `result` object, else fall back to a `GET` refresh — then update the same cache and notify listeners that WebSocket pushes use. Keep this single cache-update path when adding write logic.
- **Entity platforms are thin.** `switch.py`, `binary_sensor.py`, `light.py`, `sensor.py`, `number.py` all subclass the shared base in `entity.py` (device info, availability, listener registration) and just read from the hub cache / call `hub.async_set_value()`. Put shared behavior in `entity.py`, not duplicated per platform.
- **Unique IDs matter for stability**: device unique ID prefers `family-model-serial_number` (fallback `host:port`); entity unique ID is `{device_identifier}-{dev}-{circuit}`. Don't change ID composition without considering entity-registry migration impact.
- **Numeric policy for `ao` (analog output)** is an explicit project decision, not an EVOK default: min forced to `0.0`, max to `10.0`, step `0.1`, unit defaults to `V`. This is enforced in both `models.py`/`number.py` and tests — keep them in sync if it changes.
- Unsupported EVOK types (`wd`, `modbus_slave`, `owpower`, `owbus`, `uart`, etc.) are intentionally ignored rather than failing setup; malformed WebSocket JSON is logged and dropped, not raised.

## Testing conventions

- Tests are hardware-independent: EVOK responses are mocked (aiohttp responses, websocket message objects, fake hub objects for entity tests) using fixtures in `tests/conftest.py`, which includes both current-schema and legacy-schema sample inventories.
- When adding EVOK-facing behavior, add fixtures/cases for **both** current (`3.0.1+`) and pre-v3 payload shapes — this is the main thing that differentiates this codebase's tests from a typical HA integration.
