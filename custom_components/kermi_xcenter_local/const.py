"""Constants for the Kermi x-center integration."""

from datetime import timedelta

DOMAIN = "kermi_xcenter_local"
MANUFACTURER = "Kermi"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
MIN_SCAN_INTERVAL = timedelta(seconds=10)

DESTINATION_ID = "00000000-0000-0000-0000-000000000000"

DEVICE_TYPE_IFM = 0
DEVICE_TYPE_BUFFER = 95
DEVICE_TYPE_HEAT_PUMP = 97
DEVICE_TYPE_FRESH_WATER = 104

CONF_SCAN_INTERVAL = "scan_interval"

# WizardAnswer.PowermoduleFunctionType on BufferSystem devices
BUFFER_FUNCTION_HEATING = 1
BUFFER_FUNCTION_DHW = 2

HP_STATUS_STANDBY = "standby"
HP_STATUS_HEATING = "heating"
HP_STATUS_DHW = "dhw"
HP_STATUS_COOLING = "cooling"
HP_STATUS_DEFROST = "defrost"

ENERGY_MODE_MAP = {
    0: "off",
    1: "eco",
    2: "normal",
    3: "comfort",
    4: "custom",
}

SMART_GRID_MAP = {
    0: "blocking",
    1: "normal",
    2: "normal",
    3: "boost",
    4: "max_boost",
}

HP_STATE_MAP = {
    0: "standby",
    1: "heating",
    2: "dhw",
    3: "cooling",
    4: "defrost",
}
