# APRS-IS → RF mandatory safety rules

An `APRS-IS -> RF` flow forwards selected APRS-IS packets to a physical radio interface under strict control. Its target can only be an active TX-capable physical TNC. APRS-IS and RX-only interfaces cannot be selected as targets.

## Required order

`APRS-IS source -> APRS-IS Input Safety Rule -> APRS-IS Callsign and Radius Rule -> APRS-IS to RF TX Safety Rule -> TX RF`

All three rules are inserted automatically for `APRS-IS → RF`. They cannot be removed, disabled, bypassed, reordered, or added twice. No optional filter can be added to this restricted flow. The backend and runtime enforce the same protection even if stored data is modified manually.

## APRS-IS Callsign and Radius Rule

The filter contains only a source callsign list and a radius. Both conditions use `AND`: the packet source must exactly match one configured callsign and its decoded position must be within the radius measured from the coordinates configured in `My Station`.

Callsign matching is strict and includes SSID. `SQ9MDD` matches only `SQ9MDD`; `SQ9MDD-1` matches only `SQ9MDD-1`. Wildcards are not supported. Enter one callsign per line.

An empty configuration is valid `default deny`. Packets are also denied when they have no decoded position or when `My Station` has no valid coordinates.

## APRS-IS Input Safety Rule

The first guard applies APRS and q-construct validation, loop prevention, `NOGATE`/`RFONLY`/`TCPXX` blocking, and an initial normalized duplicate check across RF and APRS-IS. `TCPIP` alone is not blocked.

## APRS-IS to RF TX Safety Rule

The final guard is fixed immediately before `TX RF`. It owns the viscous delay, the duplicate recheck after that delay, per-flow and per-source token-bucket limits, target readiness, third-party encapsulation, and the AX.25 length limit. The inbound Internet path is removed before TX.

Defaults are `5 s` viscous delay, `6 packets/min` with burst `3` per flow, `2 packets/min` with burst `2` per source callsign, and a `30 s` duplicate window. Pending packets live only in memory. A matching local RF reception cancels pending TX, and restart does not recover it.

APRS-IS text is decoded as Unicode, but AX.25 APRS on RF uses 7-bit ASCII. Before encapsulation, common characters are transliterated (`°` to `deg`, `µ`/`μ` to `u`, typographic dashes and quotes to ASCII); unsupported characters become `?`. Packet-size validation and KISS encoding use exactly this sanitized payload.

The configured outbound RF path is used; an empty path means direct transmission. Accepted packets enter the existing RF/KISS queue. Separate APRS-IS-to-RF counters are used, so this traffic does not affect DIGI or physical TNC RX statistics.

## Navigation

[Back to Packet Flow](packet_routing_flow.en.md)
