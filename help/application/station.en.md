# My Station

This tab configures the main APRSBox station: callsign, position beacon, separate APRS Status, map symbol, and manual local frame sending.

## Position Beacon

The position beacon is an APRS frame with the local station position. It is used by maps, other stations, and `Local TX` routing rules.

- `Callsign` is the main station callsign without SSID.
- `SSID` selects the callsign suffix, for example `SQ9XYZ-4`.
- `Interface` selects the transmitting TNC, all active interfaces, or `Internal TX`.
- `Beacon Comment` is included in the position frame and has a short printable ASCII limit.
- `Beacon at every` sets the automatic beacon interval or `Proportional Path` mode.
- `Beacon Path` sets the RF path, for example an empty field for local transmission or `WIDE2-1`.
- `Get location` sets coordinates from the map.
- `Symbol Table`, `Symbol Code`, and `Overlay` select the APRS symbol shown on maps.
- `Enable automatic beacon transmission every selected interval` enables periodic beacon transmission.

`Send beacon` saves the current form and immediately queues one beacon frame.

## Path and channel load

APRSBox shows a warning when the selected path and interval may create too much RF channel load.

- Empty path, `DIRECT`, or no wide path means local transmission.
- A one-hop path should usually use a longer interval.
- A two-hop path, such as `WIDE2-2`, needs extra care.
- `Proportional Path` sends frequent local frames and less frequent full-path frames to reduce channel traffic.

If the application asks for save confirmation, the setting may significantly increase RF traffic.

## PHG Generator

The calculator icon next to `Beacon Comment` creates a `PHG` code from power, antenna height, gain, and antenna direction. The generated code is inserted at the beginning of the beacon comment.

PHG is mostly useful for fixed stations, repeaters, gateways, and digipeaters. A regular mobile station usually does not need it.

## APRS Status

`APRS Status` is a separate frame with data type identifier `>`. It does not replace the position beacon comment.

- `Status Text` is the status text and has its own length limit.
- `APRS Status at every` sets the periodic status interval.
- `Enable periodic APRS Status transmission` enables automatic status sending.

`Send status` saves the current form and queues one status frame. If status is enabled, status text cannot be empty.

## Internal TX

`Internal TX` does not transmit directly through a physical TNC. Frames are generated locally and can then be handled by `Packet Routing` rules, for example `Local TX -> TX APRS-IS`.

If there is no active `Local TX -> TX APRS-IS` rule, Internal TX behaves like a local black hole: the frame is created inside APRSBox but does not leave the system.

## Station TX Log

The log shows recent beacon and status jobs: time, type, status, interface, attempts, error, and TNC2 frame preview. A struck-through row means the job was recorded but transmission was skipped, for example because the TNC was disabled or TX-blocked.
