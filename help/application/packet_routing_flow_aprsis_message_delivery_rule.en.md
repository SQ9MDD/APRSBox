# APRS-IS Message Delivery Rule

This mandatory system rule provides the standard bidirectional IGate message path in the restricted `APRS-IS → RF` flow. It is evaluated after input safety checks and before the callsign-and-radius rule.

## What it forwards

The rule can authorize:

- messages, acknowledgements (`ack`) and rejections (`rej`) addressed to one exact local callsign-SSID,
- directed queries addressed to one exact local callsign-SSID,
- the next position packet from a sender whose message was successfully queued to RF.

Bulletins, group messages, telemetry definitions and generic queries are not mandatory message traffic.

## Local recipient checks

The recipient must have been heard recently through one of the configured local RF sources. Matching includes the SSID: `SQ9MDD` and `SQ9MDD-1` are different stations.

The rule rejects a message when the recipient was not heard within the configured time, required too many consumed DIGI hops, was recently seen as an Internet-origin station, or when the sender was recently heard on the same local RF coverage.

## Configuration

- **Local RF listening sources**: one interface name per line. An empty list uses the target RF interface.
- **Local heard validity**: from 5 to 60 minutes; default 60.
- **Maximum consumed DIGI hops**: from 0 to 2; default 0 means direct reception only.

Use the smallest coverage that reliably reaches the intended local stations.

## Interaction with other rules

An authorized message bypasses `APRS-IS Callsign and Radius Rule`, but it still passes through the final TX safety rule, duplicate suppression, rate limits, third-party encapsulation and AX.25 size checks.

[APRS-IS Callsign and Radius Rule](packet_routing_flow_aprsis_callsign_radius_rule.en.md)

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
