# Device compatibility notes: pre-v3 firmware

Date: 2026-04-18

Purpose: record the observed differences between a working UniPi device on the newer EVOK schema and a UniPi device running pre-v3 firmware.

## Summary

The device with pre-v3 firmware is reachable and exposes EVOK-compatible HTTP and WebSocket endpoints, but it uses an older payload schema than the one currently supported by the original implementation.

Current integration behavior before the compatibility update:
- onboarding/probing fails against the device with pre-v3 firmware
- main reason: metadata is not exposed as `device_info`
- secondary reason: important entity types use older EVOK names not currently mapped by the integration

## Connectivity results

Observed working endpoint shapes on the device with pre-v3 firmware:
- `http://<host>:8080/rest/all`
- `http://<host>:8080/json/all`
- `http://<host>/rest/all`
- `http://<host>/json/all`
- `ws://<host>:8080/ws`

Observed behavior:
- `http://<host>:8080/` returns `404`
- `http://<host>/` serves the UniPi web UI
- WebSocket connection succeeds and delivers JSON messages

Conclusion:
- this is not a network connectivity problem
- this is a schema / compatibility problem

## Original probe failure

Running the integration probe logic against the device with pre-v3 firmware originally returned:
- `UniPiConnectionError("device_info_missing")`

Reason:
- the original code expected a metadata object with `dev == "device_info"`
- the older device exposes metadata as `dev == "neuron"`

## EVOK schema differences

### Metadata object

Newer EVOK device:
- `dev: "device_info"`
- sample fields:
  - `family: "Neuron"`
  - `model: "L203"`
  - `sn: 167`
  - `circuit: "L203"`

Device with pre-v3 firmware:
- `dev: "neuron"`
- sample fields:
  - `model: "M205"`
  - `sn: 31`
  - `circuit: "1"`
  - `board_count: 2`
  - no `family` field observed

Implication:
- the original metadata extraction did not recognize this device
- title generation needed a legacy fallback, ideally something like:
  - `Neuron M205 (SN 31)`

### Digital inputs

Newer EVOK device:
- `dev: "di"`

Device with pre-v3 firmware:
- `dev: "input"`

Implication:
- the original integration ignored these entities because only `di` was mapped

### Relay outputs

Newer EVOK device:
- `dev: "ro"`

Device with pre-v3 firmware:
- `dev: "relay"`

Implication:
- the original integration ignored these entities because only `ro` was mapped

### LEDs

Both schemas:
- `dev: "led"`

Implication:
- already compatible

### Analog inputs

Both schemas expose:
- `dev: "ai"`

Difference:
- newer schema uses `range` as a two-item list, for example `[0, 10]`
- older schema uses `range` as a string, for example `"10.0"`
- newer schema exposes `modes` as a dict with metadata
- older schema exposes `modes` as a list of strings

Implication:
- entity may still partially work, but range/mode normalization was not aligned with the legacy payload shape

### Analog outputs

Both schemas expose:
- `dev: "ao"`

Difference:
- newer schema exposes `modes` as a dict with detailed metadata
- older schema exposes `modes` as a list of strings

Implication:
- basic value handling may work
- richer capability normalization is legacy-incompatible without adaptation

## Device type inventory comparison

### Newer EVOK schema
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

### Pre-v3 firmware schema
- `neuron`
- `input`
- `relay`
- `ai`
- `ao`
- `led`
- `wd`
- `uart`
- `owbus`

## Original integration assumptions that did not hold for the pre-v3 firmware device

1. Metadata is exposed as `device_info`
2. digital inputs are named `di`
3. relay outputs are named `ro`
4. analog `range` is a two-item list
5. analog `modes` is a dict for richer normalization
6. device naming can rely on the newer metadata fields

## Minimal compatibility work identified

Potential compatibility layer:

1. accept metadata from `dev == "neuron"` as a fallback to `device_info`
2. map legacy EVOK types:
   - `relay` -> `switch`
   - `input` -> `binary_sensor`
3. add legacy title fallback for devices missing `family`
4. tolerate `range` as string for legacy analog payloads
5. tolerate list-based `modes` for legacy analog payloads

## Recommendation

If support for older UniPi firmware is desired, the first step should be a targeted compatibility layer for:
- legacy metadata discovery
- `relay` / `input` type aliases

That is likely enough to get onboarding and the core entity set working before addressing the smaller analog normalization differences.