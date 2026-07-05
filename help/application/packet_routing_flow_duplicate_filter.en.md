# Duplicate Filter (viscous-delay)

This block does not pass the frame immediately. The first frame with a given fingerprint is held until the listening window expires.

Actual behavior:

- the fingerprint is built from `source callsign + info field`,
- path is ignored for duplicate comparison,
- the first frame waits until the window ends,
- if another frame with the same fingerprint appears during the window, both frames are dropped,
- if no duplicate appears, the first frame continues only after the timer expires.

Practical consequences:

- two frames from the same source with the same payload but different path still count as duplicates,
- this is a true viscous-delay stage: it waits first and decides later,
- it can appear only once and should be the first filter in an RF retransmit flow.

Use it when:

- several digis may hear the same source station,
- you want to reduce unnecessary repeats without immediate TX.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
