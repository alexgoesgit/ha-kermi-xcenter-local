# Kermi x-center for Home Assistant

Unofficial community integration. Not supported by Kermi.

Local Home Assistant integration for Kermi heat pumps with an **x-center interface module**.
It reads live values through the same HTTP API as the web interface (IP + password) — no Modbus and no cloud.

Tested with:

- x-center firmware 1.6.5
- x-change dynamic pro (Rubin, DeviceType 97)
- Buffer system heating / domestic hot water (DeviceType 95)
- Fresh water station Turmalin (DeviceType 104)

## Installation

The integration is not in the HACS default catalog. Add it as a **custom repository** of type Integration.

### Via HACS

1. Open HACS → menu (three dots) → **Custom repositories**.
2. Repository: `https://github.com/alexgoesgit/ha-kermi-xcenter-local`
3. Category: **Integration** → **Add**.
4. Search for **Kermi x-center** and **Download**.
5. Restart Home Assistant.
6. **Settings → Devices & services → Add integration → Kermi x-center**.
7. Enter the IP address (or hostname) and password of the x-center web interface. The port is usually `80`.

### Manual

1. Copy the folder `custom_components/kermi_xcenter_local` to `/config/custom_components/kermi_xcenter_local` on your Home Assistant instance.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Kermi x-center**.
4. Enter the IP address (or hostname) and password of the x-center web interface. The port is usually `80`.

The password is the same as for the local login in the browser, often the last four digits of the serial number.

![Setup dialog](docs/images/kermi_setup.png)

## Devices and entities

The integration creates one device per x-center module:

![Integration devices](docs/images/kermi_integration.png)

| Device | Examples |
| --- | --- |
| Heat pump | Status, supply/return, electrical/thermal power, COP, flow, defrost |
| Heating | Outdoor temperature, buffer temperature, setpoint, energy mode |
| Domestic hot water | Actual/setpoint TWE temperature, one-time charge |
| Fresh water station | Tap temperature, flow, heat quantity |
| x-center | SmartGrid, utility lock (EVU) |

COP values are `unknown` while the compressor is off (the controller then returns `NaN`). Invalid sensor values such as `-3276.7 °C` are hidden.

Some diagnostic sensors (pressures, EQ temperatures, operating hours) are disabled by default and can be enabled in the entity list.

### Every datapoint

Beyond the curated entities above, the integration creates one entity for **every** datapoint the x-center returns — roughly 200 on a heat pump with two heating circuits. The client already fetched them all; this just exposes them. They are classified from the metadata the API ships with each datapoint:

| `DatapointType` | Becomes |
| --- | --- |
| Boolean | `binary_sensor` (device class `problem` when the name mentions Störung/Alarm/Fehler/Warnung) |
| Int with `PossibleValues` | `sensor` with device class `enum`, states are the controller's own labels; the numeric code stays in the `raw_value` attribute |
| Int / Float | `sensor` with device class, unit and state class derived from `Unit` — counters (`h`, `kWh`, "Betriebsstunden", "Anzahl …") become `total_increasing` |
| String | plain `sensor` |

These entities use the controller's German display names, land in the **Diagnostic** category, and are recorded like any other entity. Each carries `datapoint_config_id`, `well_known_name` and — where the datapoint lives in a device register rather than in the x-center itself — `modbus_address` as attributes, so an entity can be mapped back onto the Modbus register map.

This makes the heat pump's full diagnostic layer available: `Status Wärmepumpe` including the `Blockiert` state, the compressor start inhibits (registers 1100/1128) and the 13 operating-limit flags for heating (registers 1101/1102), plus `Status ext. WEZ Heizen` and the external-heat-generator relays.

**Settings are read-only here.** Datapoints the x-center hides behind an installer user level are not returned by the API and therefore cannot appear, whatever this integration does.

### Diagnostics

**Download diagnostics** on the config entry writes every datapoint with its value, unit, category, config ID, Modbus address and possible values to a JSON file.

## Options

Under **Configure**:

| Option | Default | Effect |
| --- | --- | --- |
| Update interval | 60 s | Polling interval, minimum 10 s |
| Create an entity for every datapoint | on | Turns the automatic discovery above on or off |
| Include settings | on | Also expose Category 1 datapoints (heating curve thresholds, operating modes, offsets) |

![Integration devices](docs/images/kermi_options.png)

## Notes

- Home Assistant and the heat pump must be reachable on the same network.
- The integration polls `Menu/GetBundlesByCategory` — this is the endpoint that returns real measured values on Rubin firmware.
- Writing setpoints (operating mode, one-time charge, etc.) is not included in this version yet.

## Credits

The starting point for this custom integration was [kermi-ha-bridge](https://github.com/m-zenker/kermi-ha-bridge) by [Martin Zenker](https://github.com/m-zenker) (MIT license) - an AppDaemon bridge to the local x-center HTTP API.

## Maintainer

[@alexgoesgit](https://github.com/alexgoesgit) — Issues: https://github.com/alexgoesgit/ha-kermi-xcenter-local/issues

## License

Apache License 2.0. Copyright 2026 alexgoesgit. See [LICENSE](LICENSE).

Parts of the API knowledge come from kermi-ha-bridge, Copyright 2026 Martin Zenker, MIT. See [NOTICE](NOTICE).

Kermi and x-center are trademarks of their respective owners. This license does not grant any trademark rights.
