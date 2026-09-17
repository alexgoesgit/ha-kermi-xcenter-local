# Kermi x-center für Home Assistant

Inoffizielle Community-Integration. Nicht von Kermi unterstützt.

Lokale Home-Assistant-Integration für Kermi-Wärmepumpen mit **x-center Interfacemodul**.
Sie liest Live-Werte über die gleiche HTTP-API wie die Weboberfläche (IP + Passwort) - ohne Modbus und ohne Cloud.

Getestet mit:

- x-center Firmware 1.6.5
- x-change dynamic pro (Rubin, DeviceType 97)
- Puffersystem Heizen / Trinkwasser (DeviceType 95)
- Frischwasserstation Turmalin (DeviceType 104)

## Installation

1. Den Ordner `custom_components/kermi_xcenter_local` nach `/config/custom_components/kermi_xcenter_local` auf deiner Home-Assistant-Instanz kopieren.
2. Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Kermi x-center**.
4. IP-Adresse (oder Hostname) und Passwort der x-center-Weboberfläche eintragen. Port ist in der Regel `80`.

Das Passwort ist dasselbe wie beim lokalen Login im Browser, oft die letzten vier Stellen der Seriennummer.

## Geräte und Entitäten

Die Integration legt ein Gerät pro x-center-Modul an:

| Gerät | Beispiele |
| --- | --- |
| Wärmepumpe | Status, Vor-/Rücklauf, elektrische/thermische Leistung, COP, Durchfluss, Abtauen |
| Heizen | Außentemperatur, Puffertemperatur, Sollwert, Energiemodus |
| Trinkwasser | Ist-/Solltemperatur TWE, Einmalladung |
| Frischwasserstation | Zapftemperatur, Durchfluss, Wärmemenge |
| x-center | SmartGrid, EVU |

COP-Werte sind `unbekannt`, solange der Verdichter steht (die Steuerung liefert dann `NaN`). Ungültige Fühlerwerte wie `-3276.7 °C` werden ausgeblendet.

Einige Diagnose-Sensoren (Drücke, EQ-Temperaturen, Betriebsstunden) sind standardmäßig deaktiviert und können in der Entitätsliste eingeschaltet werden.

## Optionen

Unter **Konfigurieren** lässt sich das Abfrageintervall setzen (Standard 60 s, Minimum 10 s).

## Hinweise

- Home Assistant und die Wärmepumpe müssen im selben Netz erreichbar sein.
- Die Integration pollt `Menu/GetBundlesByCategory` — das ist der Endpunkt, der auf Rubin-Firmware echte Messwerte liefert.
- Schreiben von Sollwerten (Betriebsart, Einmalladung usw.) ist in dieser Version noch nicht enthalten.

## Maintainer

[@alexgoesgit](https://github.com/alexgoesgit) — Issues: https://github.com/alexgoesgit/ha-kermi-xcenter-local/issues
