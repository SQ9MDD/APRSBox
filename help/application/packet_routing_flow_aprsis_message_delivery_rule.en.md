# APRS-IS Message Delivery Rule

This mandatory system rule provides the standard bidirectional IGate message path in the restricted `APRS-IS → RF` flow. It is evaluated after input safety checks and before the callsign-and-radius rule.

## What it forwards

The rule can authorize:

- messages, acknowledgements (`ack`) and rejections (`rej`) addressed to one exact local callsign-SSID,
- directed queries addressed to one exact local callsign-SSID,
- the next position packet from a sender whose message was successfully queued to RF.

Bulletins, group messages, telemetry definitions and generic queries are not mandatory message traffic.

## Local recipient checks

The recipient must have been heard direct within the last 60 minutes through any active TNC interface on which RF transmission is allowed. Matching includes the SSID: `SQ9MDD` and `SQ9MDD-1` are different stations.

The rule rejects a message when the recipient was not heard direct within that time, the interface is disabled or has RF transmission blocked, the recipient was recently seen as an Internet-origin station, or the sender was recently heard in the same local RF coverage.

## Configuration

This system rule has no settings. APRSBox automatically uses all active TX-capable TNC interfaces on which RF transmission is not blocked. Disabled, receive-only and TX-blocked interfaces do not qualify.

## Interaction with other rules

An authorized message bypasses `APRS-IS Callsign and Radius Rule`, but it still passes through the final TX safety rule, duplicate suppression, rate limits, third-party encapsulation and AX.25 size checks.

[APRS-IS Callsign and Radius Rule](packet_routing_flow_aprsis_callsign_radius_rule.en.md)

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
