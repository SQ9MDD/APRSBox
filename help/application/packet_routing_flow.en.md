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
- `APRS-IS source -> APRS-IS Input Safety Rule -> APRS-IS Callsign and Radius Rule -> APRS-IS to RF TX Safety Rule -> TX RF` - safely forwards explicitly allowed network packets to a physical TNC.
- `... -> Black Hole` - diagnostics, dry runs, and rule testing without forwarding.

## How to build a rule

1. Choose the source.
2. Choose the target.
3. Add only the blocks required for that path.
4. Save the rule and inspect the execution log.

The APRS-IS source and target appear only when an APRSIS interface is defined in `Interfaces`. Its `Enable APRS-IS connection` switch must be active before flows can actually receive or transmit data.

## Source blocks

- [Receiver RF](packet_routing_flow_receiver_rf.en.md)
- [Local TX](packet_routing_flow_local_tx.en.md)
- [APRS-IS → RF mandatory safety rules](packet_routing_flow_rf_guard.en.md)

## Filter and rule blocks

- [APRS-IS Uplink Safety Rule](packet_routing_flow_strict_filter.en.md)
- [APRS-IS Message Delivery Rule](packet_routing_flow_aprsis_message_delivery_rule.en.md)
- [APRS-IS Callsign and Radius Rule](packet_routing_flow_aprsis_callsign_radius_rule.en.md)
- [RF Digipeating Path Rule](packet_routing_flow_path_rule_and_digi_guard.en.md)
- [RF Duplicate Delay Filter](packet_routing_flow_duplicate_filter.en.md)
- [Direct RF Reception Filter](packet_routing_flow_direct_only.en.md)
- [DIGI Filter](packet_routing_flow_digi_filter.en.md)
- [Source Callsign Filter](packet_routing_flow_callsign_filter.en.md)
- [APRS Packet Type Filter](packet_routing_flow_packet_type_filter.en.md)
- [APRS Symbol Filter](packet_routing_flow_icon_filter.en.md)
- [Position Zone Filter](packet_routing_flow_distance_filter.en.md)
- [Transmission Rate Filter](packet_routing_flow_rate_limit_filter.en.md)

## Target blocks

- [TX RF](packet_routing_flow_tx_rf.en.md)
- [TX APRS-IS](packet_routing_flow_tx_aprsis.en.md)
- [Black Hole](packet_routing_flow_black_hole.en.md)

## Quick notes

- `TX APRS-IS` requires the `APRS-IS Uplink Safety Rule`.
- RF-to-RF transmission requires the `RF Digipeating Path Rule`.
- `Local TX` can end only in `TX APRS-IS` or `Black Hole`.
- An `APRS-IS → RF` flow contains exactly four mandatory system rules. Optional filters cannot be added. Directed traffic to a recently heard local RF station can be admitted by the message-delivery rule; other traffic requires callsign **and** radius, and an empty configuration forwards no other packets.
