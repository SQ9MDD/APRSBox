# APRSBoxDaq NWS-WARN warnings

`NWS-WARN` APRSBox receive profile dedicated 'oH. U.S. county warning compact message `NWS-WARN` APRS groupDaq Hev. APRS relay envelope 'oH; National Weather Service direct connection pagh full NWS CAP/VTEC product 'oHbe'.

APRSBox `api.weather.gov`vo' alerts downloadbe'. Configured RF pagh APRS-IS interfacevo' APRS frames neH parse.

## Configuration

- APRS alarms yIchu' 'ej exact `NWS-WARN` group yIchel.
- Relevant event categoriesvaD Alerts threshold yIwIv. Offchugh frame Traffic MonitorDaq ratlh 'ach NWS-WARN alert record chenbe'.
- Operator interruptnISbogh categories neH popup threshold yIchu'.
- Automatic APRS-IS filterDaq `g/NWS-WARN` tu'lu' 'ej receive interface active 'e' yI'ol.

## Packet form

```text
SOURCE>APRS,...::NWS-WARN :DDHHMMz,EVENTLEVEL,SSCnnn[,SSCnnn...]{MSGID
```

```text
NWSWX>APRS,TCPIP*::NWS-WARN :010200z,TORNADO3,TNC037,TNC189{N1001
```

Nine-character APRS addressee fieldDaq `NWS-WARN` space padding ghaj. Group bulletinmo' APRSBox ACK ngeHbe'.

## Fields

- `DDHHMMz` UTC expiry day/hour/minute. APRSBox reception Sum law' valid month/year wIv. Automatic expiryvaD `z` pagh `Z` nIS.
- `EVENTLEVEL` event label. Historical APRS type free text 'oH; APRSBox final digits severity mojmoH. Predictable threshold/colorvaD normalized event + `1`, `2`, pagh `3` yIlo', `TORNADO3` rur.
- `SSCnnn` NWS Universal Geographic Code county form 'oH. Comma lo' counties law' alert wa' chenmoH.
- `MSGID` 1–5 alphanumeric APRS message identifier. DeduplicationvaD lo'; reference neH, ACK requestbe'.

Historical APRS WX document name-based county labels 'ej five county fields maximum Del. APRSBox current map profile machine-stable UGC county codes lo', geometry reliably matchmeH.

## UGC county codes

```text
SS C nnn
```

- `SS` U.S. state/territory two-letter identifier.
- `C` county, parish, independent city je 'oS.
- `nnn` three-digit county part of FIPS identifier.
- `TNC037` Davidson County, Tennessee 'oS.

NWS `Z` codes public forecast zones marine areas je lo'. APRSBox `[A-Z]{2}C[0-9]{3}` county codes neH map. `TNZ037` pagh `ANZ630` alertDaq pol 'ach mapDaq drawbe'. Valid code bundled geometryDaq missing/obsoletechugh mapDaq skip.

NWS county boundary dataset choHlaH. Official code drawbe'chugh installed APRSBox geometry version current NWS GIS dataset je yIcompare.

## Severity thresholds je

```text
1 = yellow
2 = orange
3 = red
```

Numeric suffix APRSBox/CAWF transport convention 'oH; full NWS CAP severity model pagh historical APRS NWS mapping 'oHbe'. Relay publisher official NWS productvo' 1–3 mapping documentnIS.

Suffix Hutlh pagh 1–3 HurDaq boSchugh severity unknown. Category enabledchugh APRSBox alert pol 'ej geometry gray 'ang. Known prefixes category wIv; unknown event `Other / unknown` lo'.

## Lifecycle repeats cancellation je

- Accepted frame counties Hoch, source Traffic Monitor link je ghajbogh alert chenmoH.
- Sender/group/APRS message ID rap repeat 'oS. Counters last-seen je update; duplicate alert chenbe'.
- Message ID chu'Daq shared logical NWS event ID Hutlh; event/counties rap 'ach APRSBox separate alert mojmoH.
- Resolved `DDHHMMz` poH alert deactivate; frames/history pol.
- Historical familyDaq `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST`, `NWS-CANCL` je tu'lu'. APRSBox `NWS-WARN` neH dedicated U.S. county geometry ghaj 'ej `NWS-CANCL` existing alert cancelbe'.
- Missing/invalid expiry alert manual delete qaSpa' active pollaH. Malformed frame detail yI'ol.

## Official NWS datavo' missing

Official NWS CAP v1.2 alerts headline, description, instructions, urgency, severity, certainty, effective/expiry times, UGC zones, polygons, VTEC event state je ghajlaH.

Compact APRSBox envelope expiry, event-level token, county codes, sender, APRS message ID neH qeng. Omitted instructions, polygons, certainty, VTEC actions, official IDs, update relationships je reconstructlaHbe'. Operational decisionvaD official NWS product yIlo'.

## Trust safe use je

`NWS-WARN` destination sender National Weather Service 'oH 'e' provebe'. APRS/APRS-IS cryptographic authentication Hutlh; APRSBox per-group trusted-sender allowlist Hutlh.

Frame secondary situational information neH yIlo'. High-impact warning official NWS endpointDaq yI'ol, especially source callsign unfamiliar, level mapping undocumented, expiry invalid, geometry missing.

## Sources

- [TAPR APRS Protocol Reference](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- Bundled historical `APRS-SPEC/WX.TXT`.
- [NOAA/NWS Universal Geographic Code directive](https://www.weather.gov/media/directives/010_pdfs_archived/pd01017002b.pdf).
- [NOAA/NWS U.S. Counties GIS](https://www.weather.gov/gis/Counties).
- [NWS CAP alert service](https://www.weather.gov/documentation/services-web-alerts).
- [NWS VTEC](https://www.weather.gov/vtec/).

[APRS alarm settingsDaq chegh](settings_alarms.tlh.md)
