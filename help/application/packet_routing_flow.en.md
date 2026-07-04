# Detailed routing block reference

This document describes the blocks available in the single-rule routing editor. Each rule has one source, zero or more filters in the middle, and one target.

## How a rule is evaluated

Packets move through the rule from top to bottom.

1. The packet enters from the source.
2. It passes through each filter or rule block in order.
3. If any block rejects the packet, later steps are not executed.
4. If the packet passes every step, it reaches the target.

## Source blocks

### `Receiver RF`

Input for packets received by a specific radio modem.

Use it when the rule should handle traffic coming from RF.

### `Local TX`

Input for frames generated locally by APRSBox.

It includes:

- beacons,
- status packets,
- weather,
- objects,
- items,
- bulletins,
- messages.

It does not include RF-received or already digipeated traffic.

## Filter and rule blocks

### `Strict Filter`

This is the system safety filter for APRS-IS uplink rules.

It:

- rejects packets containing `TCPIP` or `TCPXX`,
- rejects packets marked `NOGATE` or `RFONLY`,
- validates third-party frames,
- blocks malformed outer or inner paths.

Use it:

- as the mandatory guard for `TX APRS-IS`,
- to keep APRS-IS forwarding compliant and safe.

### `Path rule and DIGI guard`

This is the core block for `RF -> RF` rules.

It:

- analyzes the digi path,
- decides whether the local station should still repeat the packet,
- blocks locally addressed messages and queries,
- blocks third-party traffic that should not be repeated,
- blocks frames already repeated by this station.

Use it:

- in any RF retransmission rule,
- as the essential digi behavior and path control block.

### `Duplicate Filter (viscous-delay)`

This block opens a short listening window and checks whether another digi already repeated the same frame.

If yes:

- the packet is dropped.

If not:

- the packet continues after the window expires.

Use it:

- in RF digi paths where duplicate reduction matters,
- as the first filter in a typical RF rule.

### `Direct Only`

Passes only packets heard directly, without any consumed digi hop.

Use it:

- when the rule should react only to stations heard locally,
- when already-repeated traffic must be ignored.

### `DIGI Filter`

Checks which digipeaters already appear in the consumed path.

Modes:

- `allow` passes only matching packets,
- `deny` rejects matching packets.

Use it:

- to accept traffic only from selected digi chains,
- to block packets that already passed through specific digis.

### `Callsign Filter`

Matches the packet source callsign.

Modes:

- `allow` passes only matching callsigns,
- `deny` rejects matching callsigns.

Use it:

- for allowlists and blocklists,
- for separating club, service or test traffic.

### `Packet Type Filter`

Works on the main APRS packet groups.

Supported groups:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Use it:

- to route positions, messages, weather or objects differently,
- to limit a rule to one traffic class.

### `Icon Filter`

Matches the APRS symbol.

Use it:

- to pass or block selected icon types,
- to build separate paths for mobile, weather or special object traffic.

### `Distance Filter`

Passes a packet only when its decoded position is inside at least one configured zone.

Properties:

- 1 to 3 zones may be configured,
- each zone has a center and radius,
- packets without a decodable position are not automatically rejected by this filter.

Use it:

- to limit traffic to a selected geographic area,
- to build local digi or gate zones.

### `Rate Limit Filter`

Limits how often packets from a callsign or callsign pattern may continue.

It:

- tracks the time since the last passed packet for each matching rule,
- blocks the next packet if it arrives before the configured limit expires.

Use it:

- to calm down very active stations,
- to protect RF from repeated bursts,
- to reduce traffic without fully blocking a source.

## Target blocks

### `TX RF`

Sends the packet through the selected radio modem.

Use it for:

- local digi paths,
- cross-band forwarding,
- RF port-to-port forwarding.

### `TX APRS-IS`

Sends the packet to APRS-IS.

Use it for:

- iGate uplink,
- forwarding locally generated application traffic to APRS-IS.

This target is system-restricted to the mandatory `Strict Filter`.

### `Black Hole`

Logs the execution without forwarding the packet further.

Use it for:

- diagnostics,
- testing,
- observing filter behavior.

## Editor constraints

- A rule always has one source and one target.
- `Local TX` can lead only to `TX APRS-IS` or `Black Hole`.
- `TX APRS-IS` always keeps the mandatory `Strict Filter`.
- `TX RF` requires an enabled `Path rule and DIGI guard`.
- `Duplicate Filter` may appear only once.
- `Distance Filter` may appear only once.
- `Rate Limit Filter` is intended for flows ending with `TX RF`.

## Good practice

- Choose source and target first, then add filters.
- For `RF -> RF`, think about channel protection before range.
- For `RF -> APRS-IS`, make sure only appropriate traffic reaches the Internet side.
- Start testing with `Black Hole` when you want to verify logic without transmitting.
- After saving, use the flow execution log to see exactly where a packet passed or was rejected.
