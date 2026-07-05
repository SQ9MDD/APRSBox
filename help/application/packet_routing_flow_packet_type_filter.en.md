# Packet Type Filter

This filter works on whatever APRSBox decoder recognized as APRS packet group or packet type.

Most common selectors:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Practical meaning:

- `message` also covers ACK/REJ, bulletin, and announcement,
- `weather` means weather-only frames,
- a position with weather data still counts as `position`,
- for backward compatibility, legacy selectors such as `M`, `S`, `O`, and `W` still work, as do raw type codes returned by parser.

How it works:

- in `allow` mode the frame passes only when decoded group or type matches the list,
- in `deny` mode the frame is dropped only when decoded group or type matches the list,
- if decoder cannot determine group/type, `allow` rejects and `deny` passes.

Use it when:

- positions, objects, messages, or weather should be routed differently,
- one rule should be limited to one traffic class.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
