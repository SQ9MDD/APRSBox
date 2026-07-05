# iGate settings

This screen configures the APRSBox connection to APRS-IS and shows the uplink runtime state. It is not a separate iGate enable switch. Traffic is sent to APRS-IS by active `Packet Routing` flows that end with the `TX APRS-IS` target.

## When to use it

- `Receiver RF -> TX APRS-IS` creates the classic iGate uplink from radio to APRS-IS.
- `Local TX -> TX APRS-IS` sends locally generated APRSBox frames to APRS-IS, such as beacon, status, weather, objects, items, bulletins, and messages.

Detailed guidance for building these paths is available here:

[Packet Routing](packet_routing.en.md)

## Configuration fields

- `Server` is the APRS-IS host. The default is `rotate.aprs2.net`.
- `Port` is the APRS-IS server port. A common value is `14580`.
- `Login callsign / callsign-SSID` can be left empty. The application then uses the local station callsign.
- `Passcode` can be left empty. The application then derives the standard APRS-IS passcode for the login callsign.

The APRS-IS passcode is not an account password. It is the standard code derived from a callsign and required by APRS-IS servers for sending frames.

## Diagnostics

The status panel shows the current connection, login, active APRSIS flows, last error, and counters for frames sent or dropped before APRS-IS TX.

The `TX APRS-IS` target uses a system safety filter. It rejects, among other things, frames with `TCPIP` / `TCPXX` tokens, frames with `NOGATE` / `RFONLY`, and malformed third-party encapsulation.
