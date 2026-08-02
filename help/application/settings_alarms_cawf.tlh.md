# APRSBoxDaq CAWF warnings

CAWF, Common APRS Warning Format, country-neutral APRS group message envelope 'oH. Territorial public warningmey compact transmit. Helpvam supplied CAWF v1 draft rur 'ej APRSBox receiver behavior limits je Del.

CAWF transport format neH 'oH; authoritative national warning source, CAP, NWS-WARN je lIwbe'.

## Sourcevo' receiverDaq

- Territorial CAWF HUB authoritative source laD, event, severity, area codes je published country profileDaq map.
- APRS warning groupDaq message wa' pagh law' ngeH. Recommended pattern `CC-WARN`; example `PL-WARN`.
- APRSBox RF pagh automatic APRS-IS filtervo' group Hev, fragments ghommoH, thresholds lo', alert pol, area codes local GeoJSON geometryDaq rar.
- Warning group broadcast destination 'oH. APRSBox ACK ngeHbe'.

## CAWF v1 payload

```text
EXPIRY,EVENT_LEVEL,ALERT_ID,PART/TOTAL,AREA[,AREA...]{MESSAGE_ID
```

```text
012300z,TSTORM2,@3569,1/2,0609,1206,1409{A6474
```

Compliant payload field order choHbe', literal lowercase `z` neH qImHa'be' 'ej protocol tokens latlh uppercase ASCII lo', whitespace Hutlh, APRS message ID je 67 characters 'oS pagh puS.

## Fields

- `EXPIRY` = `DDHHMMz`, UTC day/hour/minute. APRSBox reception time Sum law' valid month/year wIv. Invalid value automatic expiry chenmoHbe'.
- `EVENT_LEVEL` event code + final one-digit level, `TSTORM2` rur.
- `ALERT_ID` = `@` + four uppercase hex. Logical alert fragments Hoch ID rap ghaj. Key = source callsign + warning group + alert ID; global unique 'oHbe'.
- `PART/TOTAL` `1/1`vo' tagh. `PART` ≤ `TOTAL`; partmey unique; total rap lo'nIS.
- `AREA` 1–8 uppercase letters, digits, hyphenmey. Leading zero potlh; geometry identifier exactly matchnIS.
- `MESSAGE_ID` = `{` + five uppercase hex. Fragment wa' identify, alert Hoch identifybe'. Exact repeat ID rap pol; changed fragment ID chu' nIS. Closing brace pagh.

InteroperabilityvaD APRSBox alphanumeric APRS message ID broader laj, 'ach publishers strict CAWF v1 lo'nIS.

## Severity event je

```text
1 = yellow
2 = orange
3 = red
```

Level `0` active warning 'oHbe' 'ej transmitbe'nIS. Level `4` reserved. Country profile authoritative scalevo' 1–3 mapping documentnIS.

```text
TSTORM WIND RAIN FLOOD FFLOOD SNOW ICE HEAT COLD FOG
COASTAL AVALANC FIRE DUST OTHER
```

APRSBox exact event code pol. Known prefix UI category/icon wIv; dedicated category Hutlhbogh code `Other / unknown`Daq ratlh 'ej thresholdvetlh lo'.

## Fragment assembly duplicates je

- Fragments order arbitrary HevlaH. APRSBox source callsign + group + `ALERT_ID` lo' ghommoH.
- Alert unique area codes union pol 'ej received/declared parts 'ang.
- Part 1–`TOTAL` Hoch HevDI' `complete`; qaSpa' `incomplete`.
- APRS message ID rap repeat existing alertDaq rar 'ej logical alert cha' chenmoHbe'.
- CAWF draft 15-minute incomplete assembly timeout recommend. APRSBox DaH normal expiry pagh operator delete qaSpa' incomplete record pol; completion status yI'ol.

## Lifecycle

- Fragment wa'DIch Alerts threshold juSchugh logical alert activate/create.
- Fragments latlh exact repeats je record rap update 'ej Traffic Monitor frame links pol.
- `ALERT_ID` rap reuse source/group record rap update. Publisher expiry pIq 48 hours qaSpa' reusebe'nIS.
- `EXPIRY` poH APRSBox alert deactivate, 'ach frames/history pol.
- CAWF v1 explicit cancellation standard Hutlh. Cancellation address custom token je existing APRSBox alert cancel 'e' yIpIHQo'.

## Country profile map geometry je

Profile group operator, authoritative source, publisher callsigns, event/severity mappings, area-code meaning, geometry version, validity/repetition policy, contact je publishnIS.

`CC-WARN` groupvaD APRSBox two-letter country directoryDaq local GeoJSON nej. Geometry WGS84 `Polygon` pagh `MultiPolygon` nIS; identifier transmitted `AREA` exactly matchnIS. `PL-WARN` Polish county dataset dedicated ghaj.

Unknown area code alertDaq pol 'ach mapDaq skip. Active alerts law' geometry rap Daq, highest known severity color wIv 'ej contributors Hoch list.

## Trust safety je

CAWF v1 cryptographic authentication Hutlh. Draft group HochvaD trusted publisher allowlist, HUB operator/source public documentation je recommend. APRSBox DaH allowlist enforcebe'; sender Hoch configured groupDaq ngeHlaH.

APRS secondary situational-awareness channel neH yIlo'. High-impact warning authoritative agencyDaq yI'ol, especially sender unexpected, alert incomplete, expiry invalid, geometry missing. APRS-IS reception transport neH prove; authenticity provebe'.

## Sources

- Supplied `CAWF.md` `CAWF-PL.md` je, CAWF v1 draft.
- [TAPR APRS Protocol Reference](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- [NWS CAP alert service documentation](https://www.weather.gov/documentation/services-web-alerts).

[APRS alarm settingsDaq chegh](settings_alarms.tlh.md)
