# CAWF warnings in APRSBox

CAWF, the Common APRS Warning Format, is a compact country-neutral envelope for distributing territorially scoped public warnings as APRS group messages. This guide describes CAWF v1 from the supplied draft and then identifies the behavior and limits of the APRSBox receiver.

CAWF is a transport format. It does not replace the authoritative national warning source, CAP, or the NWS-WARN profile.

## End-to-end model

- A territorial CAWF HUB reads an authoritative source and maps its event, severity, and areas to a published country profile.
- It transmits one or more APRS messages to a warning group. The recommended group pattern is `CC-WARN`, for example `PL-WARN`.
- APRSBox receives the group through RF or the automatically extended APRS-IS filter, assembles fragments, applies thresholds, stores the alert, and joins area codes to local GeoJSON geometry.
- Warning groups are broadcast-style destinations. APRSBox does not send an ACK.

## CAWF v1 payload

```text
EXPIRY,EVENT_LEVEL,ALERT_ID,PART/TOTAL,AREA[,AREA...]{MESSAGE_ID
```

APRSBox also accepts and generates the optional comment extension:

```text
EXPIRY,EVENT_LEVEL,ALERT_ID,PART/TOTAL,AREA[,AREA...]|COMMENT{MESSAGE_ID
```

Example:

```text
012300z,TSTORM2,@3569,1/2,0609,1206,1409{A6474
```

A compliant CAWF v1 payload uses fixed field order and uppercase ASCII protocol tokens except for the literal lowercase `z`. APRSBox's optional comment extension starts after `|`, may contain spaces, and is transliterated to APRS-safe ASCII. The complete payload has at most 67 characters including the APRS message identifier.

## Fields

- `EXPIRY` is `DDHHMMz`: day, hour, and minute in UTC. APRSBox resolves month and year to the closest valid occurrence around reception time. An impossible or malformed value cannot expire the alert automatically.
- `EVENT_LEVEL` combines an event code and the final one-digit level, for example `TSTORM2`.
- `ALERT_ID` is `@` followed by four uppercase hexadecimal characters. All fragments of one logical alert share it. Its receiver scope is source callsign plus warning group plus alert ID; it is not globally unique.
- `PART/TOTAL` starts at `1/1`. Part numbers are unique, `PART` cannot exceed `TOTAL`, and every fragment should declare the same total.
- `AREA` contains 1–8 uppercase letters, digits, or hyphens. Leading zeros are significant and the code must exactly match the profile geometry identifier.
- `COMMENT` is optional human-readable APRS-safe ASCII text after `|`. APRSBox calculates its capacity from the complete generated payload and splits it with the normal CAWF multipart mechanism.
- `MESSAGE_ID` is five uppercase hexadecimal characters after `{`. It identifies one fragment, not the complete alert. An exact retransmission should keep the ID; a changed fragment needs a new one. There is no closing brace.

APRSBox accepts a somewhat broader alphanumeric APRS message identifier for interoperability, but publishers should use the stricter CAWF v1 form.

## Severity and event registry

CAWF v1 defines active levels:

```text
1 = yellow
2 = orange
3 = red
```

Level `0` means no active warning and must not be transmitted as active CAWF. Level `4` is reserved. The country profile must document how the authoritative source is mapped to levels 1–3.

The initial CAWF event registry is:

```text
TSTORM WIND RAIN FLOOD FFLOOD SNOW ICE HEAT COLD FOG
COASTAL AVALANC FIRE DUST OTHER
```

APRSBox keeps the exact event code and uses known prefixes to select its UI category and icon. Codes without a dedicated category remain visible under `Other / unknown`; thresholds for that category apply.

## Fragment assembly and duplicates

- Fragments may arrive out of order. APRSBox groups them by source callsign, destination group, and `ALERT_ID`.
- The Alerts record contains the union of unique received area codes and reports received versus declared parts.
- It becomes `complete` after every part from 1 through `TOTAL` has been received; before that it is `incomplete`.
- A repeated fragment with the same APRS message ID is related to the existing alert and counted without creating another logical alert.
- The CAWF draft recommends abandoning an incomplete assembly after 15 minutes. APRSBox currently preserves the incomplete record until normal expiry or operator deletion, so use the completion status when assessing it.

## Lifecycle

- The first fragment activates or creates the logical alert if the Alerts threshold permits it.
- Further fragments and exact repeats update the same record and retain links to their Traffic Monitor frames.
- Reusing the same `ALERT_ID` updates the same source-and-group-scoped record. A publisher should avoid reuse for at least 48 hours after expiry.
- At `EXPIRY`, APRSBox deactivates the alert but preserves its stored frames and history.
- APRSBox cancellation uses the same envelope with `EVENT_LEVEL` set to `CANCEL`, the same source callsign, warning group, `ALERT_ID`, expiry and area code. The receiver scopes cancellation by source, group and alert ID, so another station cannot cancel a sender's alert by reusing its short ID.

## Country profiles and map geometry

A profile must publish the warning-group operator, authoritative data source, publisher callsigns, event and severity mappings, area-code meaning, geometry version, validity policy, repetition policy, and contact route.

For a group matching `CC-WARN`, APRSBox looks for local GeoJSON under the corresponding two-letter country directory. Geometry must be a WGS84 `Polygon` or `MultiPolygon`, and its identifier must match the transmitted `AREA` exactly. `PL-WARN` has a dedicated Polish county dataset.

An unknown area code is retained in the alert but is skipped on the map. If several active alerts affect the same geometry, the highest known severity determines its color and the map lists all contributing alerts.

## Trust and operational safety

CAWF v1 has no cryptographic authentication. The draft recommends a trusted publisher allowlist for each group and public documentation of the HUB operator and source. APRSBox does not currently enforce such an allowlist, so any sender can address a configured group.

Treat APRS as a secondary situational-awareness channel. Verify high-impact warnings with the authoritative agency, especially when the sender is unexpected, the alert is incomplete, the expiry is invalid, or an area has no geometry. Receipt through APRS-IS proves transport only, not authenticity.

## Sources

- Supplied `CAWF.md` and `CAWF-PL.md`, CAWF v1 draft.
- [TAPR APRS Protocol Reference, National Weather Service bulletin and message rules](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- [NWS CAP alert service documentation](https://www.weather.gov/documentation/services-web-alerts), used to distinguish an authoritative rich alert from its compact APRS transport.

[Back to APRS alarm settings](settings_alarms.en.md)
