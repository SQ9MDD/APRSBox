# TNC

The TNC tab configures radio interfaces used by APRSBox for KISS/TNC2 receive, outbound frame transmission, and optional LAN KISS port sharing.

## TNC list

The table shows configured interfaces. Click a row to edit it.

- `Status` shows configuration and runtime state, such as connected, error, or disabled.
- `TX Block` shows whether transmission through the interface is blocked.
- `LAN` shows whether APRSBox exposes a KISS/TNC proxy for LAN clients.

Disabling a TNC stops the traffic monitor and outbound service from using it. Beacon, WX, object, bulletin, and message settings can still reference that interface, but transmission will be skipped or fail depending on context.

## Interface types

- `TCP` connects to a TNC or software that exposes KISS over TCP. `Path / Adress` usually has the `host:port` format, for example `127.0.0.1:8001`.
- `SERIALL` uses a local serial port, for example `/dev/ttyUSB0` or `/dev/ttyACM0`, and requires a valid `Baud Rate`.
- `OpenWebRX MQTT (RX only)` receives packets from OpenWebRX MQTT. This type is receive-only: TX is blocked and LAN proxy is disabled.

For OpenWebRX MQTT, the address field should be an `mqtt://` or `mqtts://` URL with the topic in the path, for example `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

## Configuration fields

- `Name` is displayed in logs, interface lists, and TX selectors.
- `Band` describes the interface band.
- `Enabled` activates the interface in the APRSBox runtime.
- `Block TX on this interface` allows receiving traffic but blocks outbound transmission.
- `TX Min Gap (s)` sets the minimum pause between transmissions on this TNC. The allowed range is `0.2` to `1.2` seconds.
- `RX Silence Reconnect Timeout (s)` applies to serial interfaces. After RX silence longer than this value, the serial broker can force a reconnect. `0` disables this watchdog.

`Baud Rate` is used only for `SERIALL`. It is ignored for `TCP` and `OpenWebRX MQTT`.

## Expose Port

`Expose Port` exposes the TNC connection through APRSBox as a TCP port for LAN clients. APRSBox relays frames between the physical TNC and clients.

- `Allow TX from remote clients` allows LAN clients to send frames to the TNC. When disabled, clients can only receive.
- `Bind Address` defines the listen address. `0.0.0.0` means all network interfaces.
- `Port` is the TCP port exposed by APRSBox. Up to 3 simultaneous clients are supported.
- `Whitelist` restricts access to IPv4 addresses or CIDR networks. Enter one item per line; commas are also accepted.

Do not enable remote TX on an untrusted network. If you expose the port beyond the local machine, configure a whitelist.

## When to use multiple TNCs

Multiple active TNCs can run in parallel. Received traffic is handled per interface, while transmission depends on the selector used in each tab, such as `My Station`, `WX`, objects, bulletins, messages, or `Packet Routing` rules.

If you only need input from OpenWebRX, use `OpenWebRX MQTT (RX only)`. If you need full radio RX/TX, use `TCP` or `SERIALL`.
