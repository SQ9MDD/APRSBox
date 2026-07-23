# APRS-IS Callsign and Radius Rule

This mandatory system rule is the explicit allow list in the restricted `APRS-IS → RF` flow. It uses default deny: a packet continues only when both its exact source callsign and its decoded position match the configuration.

## Conditions

The conditions use `AND`:

1. The packet source exactly matches one callsign entered in the list.
2. The packet position is within the configured radius measured from the coordinates in `My Station`.

A callsign match without a position match is rejected. A position match from a callsign not on the list is also rejected.

## Source callsigns

- Enter one callsign per line.
- Matching is case-insensitive but otherwise strict and includes SSID.
- `SQ9MDD` matches only `SQ9MDD`.
- `SQ9MDD-1` matches only `SQ9MDD-1`.
- Wildcards are not supported.
- A callsign must be a valid AX.25 address: 1–6 letters or digits with an optional SSID from `0` to `15`.
- Up to 50 callsigns may be configured.

## Radius

The GUI accepts a radius from `0.1` to `1000 km` in `0.1 km` steps. Distance is calculated from the station coordinates configured in `My Station`, not from the receiving modem or another packet.

The packet is rejected when:

- its APRS position cannot be decoded,
- `My Station` has no valid coordinates,
- its position is outside the radius.

## Empty and incomplete configuration

Both the callsign list and radius must be filled, or both must be empty. A partially filled configuration cannot be saved.

Leaving both fields empty is valid and intentionally denies every packet. This makes an unconfigured rule safe by default.

## Placement

The rule is inserted and managed automatically between `APRS-IS Input Safety Rule` and `APRS-IS to RF TX Safety Rule`. It cannot be removed, disabled, duplicated, or moved, and no optional filters can be added to this flow.

## Navigation

[APRS-IS → RF mandatory safety rules](packet_routing_flow_rf_guard.en.md)

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
