# NWS-WARN warnings in APRSBox

`NWS-WARN` is the dedicated APRSBox receive profile for compact U.S. county warning messages addressed to the APRS group `NWS-WARN`. It is an APRS relay envelope, not a direct connection to the National Weather Service and not a full NWS CAP or VTEC product.

APRSBox does not download alerts from `api.weather.gov`. It only interprets APRS frames received through a configured RF or APRS-IS interface.

## Configuration

- Enable APRS alarms and add the exact group `NWS-WARN`.
- Set the Alerts threshold for the relevant event categories. Without it, received frames remain visible in the Traffic Monitor but do not create NWS-WARN records.
- Set Alert popup thresholds only for categories that should interrupt the operator.
- Verify the automatic APRS-IS filter includes `g/NWS-WARN` and that the required receive interface is active.

## APRSBox packet form

```text
SOURCE>APRS,...::NWS-WARN :DDHHMMz,EVENTLEVEL,SSCnnn[,SSCnnn...]{MSGID
```

Example:

```text
NWSWX>APRS,TCPIP*::NWS-WARN :010200z,TORNADO3,TNC037,TNC189{N1001
```

The nine-character APRS addressee field contains `NWS-WARN` padded with a space. Because this is a group bulletin, APRSBox never sends an ACK.

## Fields interpreted by APRSBox

- `DDHHMMz` is expiry day, hour, and minute in UTC. APRSBox chooses the closest valid month and year around reception. The lowercase or uppercase `z` is required by the receiver for automatic expiry.
- `EVENTLEVEL` is the event label. Historical APRS material defines the type as free text; APRSBox additionally reads final digits as severity. For predictable thresholds and map colors, use a normalized event code followed by `1`, `2`, or `3`, for example `TORNADO3`.
- `SSCnnn` is an NWS Universal Geographic Code in county form. Multiple comma-separated counties form one alert.
- `MSGID` is a 1–5 character alphanumeric APRS message identifier. It identifies the transported message for deduplication; it is reference data and does not request an ACK.

The historical APRS weather text also described name-based county labels and a maximum of five county fields. APRSBox's current mapped NWS-WARN profile instead expects machine-stable UGC county codes so they can be joined reliably to geometry.

## UGC county codes

The accepted map code has exactly six characters:

```text
SS C nnn
```

- `SS` is the two-letter U.S. state or territory identifier.
- `C` means county, parish, or independent city.
- `nnn` is the three-digit county portion of the FIPS identifier.
- `TNC037`, for example, identifies Davidson County, Tennessee in this form.

NWS also uses `Z` codes for public forecast zones and marine areas. APRSBox deliberately maps only county-form codes matching `[A-Z]{2}C[0-9]{3}`. A code such as `TNZ037` or `ANZ630` remains in the stored alert but is not drawn. A syntactically valid county code missing from the bundled geometry, such as an obsolete or unknown code, is also skipped on the map.

The NWS county boundary dataset changes over time. If an official county code does not draw, compare it with the installed APRSBox geometry version and the current NWS GIS dataset.

## Event severity and thresholds

APRSBox applies the shared alarm scale:

```text
1 = yellow
2 = orange
3 = red
```

This numeric suffix is an APRSBox/CAWF transport convention, not the full NWS CAP severity model and not a mapping defined by the historical APRS NWS bulletin syntax. The relay publisher is responsible for documenting how the official NWS product becomes level 1–3.

If the suffix is absent or outside 1–3, the severity is unknown. When the event category is enabled, APRSBox preserves the alert instead of silently dropping it; mapped geometry is gray. Event names are classified by known prefixes, while an unrecognized name uses `Other / unknown`.

## Lifecycle, repeats, and cancellation

- A valid accepted frame creates an alert containing all transmitted county codes and a link to the source Traffic Monitor frame.
- The same sender, group, and APRS message ID identify a repeat of the same warning message. Repeats update counters and last-seen time instead of creating a duplicate.
- A new message ID has no shared logical NWS event identifier in this envelope, so APRSBox treats it as a separate alert even if event and counties are identical.
- A resolved `DDHHMMz` deactivates the alert at expiry. Frames and history remain stored.
- The historical APRS family includes `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST`, and `NWS-CANCL`. APRSBox has dedicated U.S. county geometry only for `NWS-WARN` and does not interpret `NWS-CANCL` as a cancellation of an existing alert.
- A missing or invalid expiry can leave the alert active until manual deletion. Inspect the detail view when the source packet is malformed.

## What is lost compared with official NWS data

Official NWS alert services distribute CAP v1.2 watches, warnings, advisories, and similar products. Those records may include headline, description, instructions, urgency, severity, certainty, effective and expiry times, UGC zones, polygons, and VTEC event-state information.

The compact APRSBox NWS-WARN envelope carries only expiry, an event-and-level token, county codes, sender, and APRS message ID. It cannot reconstruct omitted instructions, polygons, certainty, VTEC actions, official identifiers, or update relationships. Always use the linked official NWS product for operational decisions when available.

## Trust and safe use

The `NWS-WARN` destination does not prove that the sender is the National Weather Service. APRS and APRS-IS do not cryptographically authenticate this envelope, and APRSBox currently has no per-group trusted-sender allowlist.

Treat the frame as secondary situational information. Verify high-impact warnings at an official NWS endpoint, especially when the source callsign is unfamiliar, severity mapping is undocumented, expiry is invalid, or county geometry is missing.

## Sources

- [TAPR APRS Protocol Reference — NWS bulletin address and no-ACK behavior](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- Bundled historical APRS weather reference `APRS-SPEC/WX.TXT`, which defines the `NWS-WARN`, `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST`, and `NWS-CANCL` family.
- [NOAA/NWS Universal Geographic Code directive](https://www.weather.gov/media/directives/010_pdfs_archived/pd01017002b.pdf).
- [NOAA/NWS U.S. Counties GIS dataset](https://www.weather.gov/gis/Counties).
- [NWS CAP alerts web service documentation](https://www.weather.gov/documentation/services-web-alerts).
- [NWS VTEC documentation](https://www.weather.gov/vtec/).

[Back to APRS alarm settings](settings_alarms.en.md)
