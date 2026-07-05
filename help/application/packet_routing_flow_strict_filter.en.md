# Strict Filter

This is the system safety block for rules ending in `TX APRS-IS`.

For frames coming from `Receiver RF` it:

- checks the full outer path,
- rejects the frame if the path contains `TCPIP`, `TCPXX`, `NOGATE`, or `RFONLY`,
- validates third-party encapsulation,
- for valid third-party frames, checks the inner path for the same blocked tokens.

For `Local TX` it is even stricter:

- the frame must be marked in metadata as locally generated APRSBox traffic,
- third-party encapsulation is rejected,
- any `q..` construct in path is rejected,
- `TCPIP`, `TCPXX`, `NOGATE`, and `RFONLY` are still blocked.

Important notes:

- with `TX APRS-IS` this filter is mandatory,
- it is not a replacement for RF digi path logic,
- if TNC2 parsing fails, the frame is rejected.

Typical use cases:

- `Receiver RF -> Strict Filter -> TX APRS-IS`,
- `Local TX -> Strict Filter -> TX APRS-IS`.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
