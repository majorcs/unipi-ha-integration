# UniPi EVOK Home Assistant Integration

Custom Home Assistant integration for UniPi controllers exposed through the EVOK API.

## Installation via HACS

This repository is ready to be added as a custom HACS repository.

1. Open HACS in Home Assistant.
2. Go to the custom repositories dialog.
3. Add `https://github.com/majorcs/unipi-ha-integration`.
4. Select repository type `Integration`.
5. Install `UniPi EVOK` from HACS.
6. Restart Home Assistant.
7. Add the integration from the Home Assistant integrations UI.

## Releases

Releases use a calendar version with an intra-day sequence number:

- `YYYY.M.D.N`
- example: `2026.4.18.1`

This allows multiple releases on the same day while keeping versions chronological.

## Current status

This repository contains the initial implementation of a config-entry based integration with:

- EVOK HTTP bootstrap discovery
- permanent EVOK WebSocket connection handling
- multi-device support through Home Assistant config entries
- dynamic entities for relays / digital outputs, digital inputs, LEDs, analog inputs, and analog outputs
- HACS-compatible repository layout

## Supported entity mapping

- `ro`, `do` -> `switch`
- `di` -> `binary_sensor`
- `led` -> `light`
- `ai`, `temp` (1-Wire DS18B20/DS18S20) -> `sensor`
- `ao` -> `number`

## Configuration

Add the integration in Home Assistant and provide:

- host / IP address
- optional EVOK port, default `8080`

The integration reads `device_info` from EVOK during setup and uses it to name and identify the device.

## Development notes

The implementation uses:

- `GET /rest/all` for initial discovery
- `POST /rest/{dev}/{circuit}` for writable entities
- `ws://{host}:{port}/ws` for realtime updates

More documentation, tests, and release assets should be added as the integration matures.

## License

Licensed under the [MIT License](LICENSE).
