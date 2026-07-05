# Path rule and DIGI guard

This is the key block for flows ending in `TX RF`. It performs DIGI protection first and path rewriting second.

The guard part rejects:

- third-party frames,
- APRS messages addressed to local `My station`,
- APRS queries addressed to local `My station`,
- APRS messages addressed to local `WX station`,
- APRS queries addressed to local `WX station`,
- frames where the local station already appears as a consumed path hop such as `MYCALL-SSID*`.

Only after that does it inspect path routing:

- if the path is empty, the frame is rejected,
- if all hops are already consumed, the frame is rejected,
- only the first unconsumed hop is checked,
- later hops are ignored until that first hop is handled.

Configuration fields:

- `Paths (TRACE / traced)`:
  If the first unconsumed hop matches this list, APRSBox consumes it and inserts the local digi callsign from `My settings`.
- `Paths (NO TRACE / not traced)`:
  If the first unconsumed hop matches this list, APRSBox reduces that hop in place without inserting the local digi callsign.

What you can enter:

- put each entry on its own line,
- `TRACE`: a full hop such as `WIDE1-1`, `WIDE2-1`, `WIDE2-2`, or a family alias such as `WIDE`,
- `NO TRACE`: a full hop such as `SP1-1`, `SP2-1`, `SP2-2`, a family alias such as `SP`, or your own `CALLSIGN-SSID`.
- `WIDE2-2` matches only `WIDE2-2`; it does not handle `WIDE2-1` or `WIDE1-1`,
- `SP2-2` matches only `SP2-2`; it does not handle `SP2-1` or `SP1-1`,
- if you do not use a family alias such as `WIDE` or `SP`, add every supported path on a separate line.

Typical rewrites:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `SP1-1` -> `SP1*`,
- NO TRACE `SP2-1` -> `SP2*`,
- NO TRACE `SP2-2` -> `SP2-1`,
- if the hop is not in `N-N` form, NO TRACE simply adds `*`.

Typical starter entries:

`TRACE`:

- `WIDE` - one line covering the `WIDE` family,
- `WIDE1-1` - only path `WIDE1-1`,
- `WIDE2-1` - only path `WIDE2-1`,
- `WIDE2-2` - only path `WIDE2-2`.

`NO TRACE`:

- `SP` - one line covering the `SP` family,
- `SP1-1` - only path `SP1-1`,
- `SP2-1` - only path `SP2-1`,
- `SP2-2` - only path `SP2-2`,
- `CALLSIGN-SSID` - your own explicit hop that should be reduced without TRACE.

Why your own callsign is often added to `NO TRACE`:

- to consume packets addressed directly to your callsign without inserting it into path again,
- to handle explicit local hops that should be non-traced,
- to reduce local `SP` family hops without inserting your own callsign into path.

Important notes:

- if TRACE matches but the local callsign is not configured, the frame is rejected,
- if the first unconsumed hop matches neither TRACE nor NO TRACE, the frame is rejected.

Typical layout:

```text
Receiver RF -> Duplicate Filter (viscous-delay) -> Path rule and DIGI guard -> TX RF
```

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
