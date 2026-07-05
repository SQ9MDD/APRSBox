# Local TX

Source for frames generated locally by APRSBox.

It includes:

- beacons,
- status packets,
- weather,
- objects,
- items,
- bulletins,
- messages.

It does not include:

- RF-received traffic,
- already digipeated traffic,
- ordinary TNC input traffic.

In practice:

- this is the internal application transmit stream,
- `Local TX` can lead only to `TX APRS-IS` or `Black Hole`.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
