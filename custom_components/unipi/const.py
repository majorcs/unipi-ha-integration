"""Constants for the UniPi EVOK integration."""

from homeassistant.const import Platform

DOMAIN = "unipi"
DEFAULT_PORT = 8080
DEFAULT_NAME = "UniPi"
MANUFACTURER = "UniPi Technology"

CONF_DEVICE_UID = "device_uid"
CONF_MODEL = "model"
CONF_SERIAL_NUMBER = "serial_number"

SUPPORTED_PLATFORMS: tuple[Platform, ...] = (
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.NUMBER,
)

DEVICE_TYPE_TO_PLATFORM: dict[str, Platform] = {
    "ro": Platform.SWITCH,
    "do": Platform.SWITCH,
    "di": Platform.BINARY_SENSOR,
    "led": Platform.LIGHT,
    "ai": Platform.SENSOR,
    "ao": Platform.NUMBER,
    "temp": Platform.SENSOR,
}

WRITABLE_DEVICE_TYPES = {"ro", "do", "led", "ao"}

DEFAULT_NUMBER_MIN = 0.0
DEFAULT_NUMBER_MAX = 10.0
DEFAULT_NUMBER_STEP = 0.1
