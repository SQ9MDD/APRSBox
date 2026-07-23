# Packet Flow rule reference

This help page is a short guide to what the `Packet Flow` editor is for and when the typical paths are used. Detailed behavior of each block is linked further below.

## What this screen does

A routing rule tells APRSBox what to do with a packet after it is received or generated locally.

Each rule has one source, zero or more middle blocks, and one final target.

Packets always move from top to bottom. If any block rejects a packet, the rest of the rule is not executed.

## When to use Packet Flow

- `Receiver RF -> TX APRS-IS` - classic iGate uplink from RF to APRS-IS.
- `Receiver RF -> TX RF` - classic digipeater path on radio.
- `Local TX -> TX APRS-IS` - locally generated frames such as beacons, weather, objects, items, bulletins, and messages.
- `APRS-IS -> Input Guard -> default deny -> RF TX Guard -> TX RF` - safely forwards explicitly allowed network packets to a physical TNC.
- `... -> Black Hole` - diagnostics, dry runs, and rule testing without forwarding.

## How to build a rule

1. Choose the source.
2. Choose the target.
3. Add only the blocks required for that path.
4. Save the rule and inspect the execution log.

## Source blocks

- [Receiver RF](packet_routing_flow_receiver_rf.en.md)
- [Local TX](packet_routing_flow_local_tx.en.md)
- [APRS-IS source and RF Guard](packet_routing_flow_rf_guard.en.md)

## Filter and rule blocks

- [Strict Filter](packet_routing_flow_strict_filter.en.md)
- [Path rule and DIGI guard](packet_routing_flow_path_rule_and_digi_guard.en.md)
- [Duplicate Filter (viscous-delay)](packet_routing_flow_duplicate_filter.en.md)
- [Direct Only](packet_routing_flow_direct_only.en.md)
- [DIGI Filter](packet_routing_flow_digi_filter.en.md)
- [Callsign Filter](packet_routing_flow_callsign_filter.en.md)
- [Packet Type Filter](packet_routing_flow_packet_type_filter.en.md)
- [Icon Filter](packet_routing_flow_icon_filter.en.md)
- [Distance Filter](packet_routing_flow_distance_filter.en.md)
- [Rate Limit Filter](packet_routing_flow_rate_limit_filter.en.md)

## Target blocks

- [TX RF](packet_routing_flow_tx_rf.en.md)
- [TX APRS-IS](packet_routing_flow_tx_aprsis.en.md)
- [Black Hole](packet_routing_flow_black_hole.en.md)

## Quick notes

- `TX APRS-IS` requires the `Strict Filter` block.
- `TX RF` requires the `Path rule and DIGI guard` block.
- `Local TX` can end only in `TX APRS-IS` or `Black Hole`.
- An `APRS-IS -> RF` flow automatically receives mandatory input and RF TX guards around the strict callsign-and-radius default-deny filter. Callsign and radius use `AND`; an empty configuration forwards no packets.
