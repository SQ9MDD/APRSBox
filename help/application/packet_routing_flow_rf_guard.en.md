# APRS-IS source and RF Guard

An `APRS-IS -> RF` flow forwards selected APRS-IS packets to a physical radio interface under strict control. Its target can only be an active TX-capable physical TNC. APRS-IS and RX-only interfaces cannot be selected as targets.

## Required order

`APRS-IS source -> RF Guard -> explicit allow rules -> TX RF`

`RF Guard` is inserted automatically when an APRS-IS source is selected. It cannot be removed, disabled, bypassed, or added twice. The backend and runtime enforce the same protection even if stored data is modified manually.

## Explicit allow rules

All rules are inclusive. Conditions inside one rule use `AND`; separate rules use `OR`. Conditions reuse data decoded by the existing parser and filters: packet type, source callsign, destination, message addressee, object name, symbol, and a distance area.

No rules is a valid `default deny` configuration: the flow can be saved and enabled, but it forwards no packets.

## RF protection

The guard always applies APRS and q-construct validation, loop prevention, `NOGATE`/`RFONLY`/`TCPXX` blocking, duplicate normalization across RF and APRS-IS, viscous delay, a second duplicate check, rate limits, third-party encapsulation, and the AX.25 length limit. `TCPIP` alone is not blocked; the inbound Internet path is removed before TX.

Defaults are `5 s` viscous delay, `6 packets/min` with burst `3` per flow, `2 packets/min` with burst `2` per source callsign, and a `30 s` duplicate window. Pending packets live only in memory. A matching local RF reception cancels pending TX, and restart does not recover it.

The original payload is preserved. The configured outbound RF path is used; an empty path means direct transmission. Accepted packets enter the existing RF/KISS queue. Separate APRS-IS-to-RF counters are used, so this traffic does not affect DIGI or physical TNC RX statistics.

## Navigation

[Back to Packet Flow](packet_routing_flow.en.md)
