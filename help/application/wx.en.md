# WX

The WX tab configures the local APRSBox weather station. Data is read from HTTP sources, normalized into APRS complete WX format, and transmitted as a local weather frame.

## Setup order

- Set the station callsign in `My Settings`.
- Choose a separate `WX SSID` for the weather station.
- Add a source in `WX data sources`.
- Test the source or run `Discover source`.
- Assign sources and identifiers in `WX data mapping`.
- Run test reads for the required parameters.
- Enable `Enable WX`, save the configuration, and check `WX TX Log`.

## Global WX configuration

- `Callsign` is read from `My Settings` and is not edited on this tab.
- `WX SSID` creates the weather station callsign, for example `SQ9XYZ-13`. The SSID used by the main station is not available for WX.
- `Interface` selects the TNC used for the WX frame, or the option that sends through all active interfaces.
- `Path` sets the APRS path for the WX frame. An empty field or `RFONLY` is treated as direct transmission without digipeaters.
- Empty path and `RFONLY` allow shorter intervals. A routed path, such as `WIDE2-2`, limits the interval list to longer values.
- `Latitude` and `Longitude` define the weather station position. `Get location` lets you pick the point on the map.
- `Refresh / TX interval` controls the data refresh and WX transmit scheduling cycle.
- `Allow cached values on failure` lets APRSBox reuse the last good value when a source is temporarily unavailable.
- `Default max cache age (s)` defines how long a cached value can still be considered usable.

`Refresh now` reads the configured mappings and refreshes the cache. `Send now` saves the form configuration, performs a manual refresh, and only then queues the WX frame for transmission.

## WX data mapping

Mapping connects an APRS WX parameter with a source and an identifier inside that source.

The required parameters for the basic WX frame are:

- `Wind direction` in degrees,
- `Wind speed` in mph,
- `Temperature` in Fahrenheit.

Optional parameters include wind gust, rain in the last hour, rain in 24 hours, rain since midnight, humidity, pressure, snow, luminosity, raw rain counter, water height, battery voltage, and radiation.

`Raw value` and `Normalized` show the value read from the source and the value converted into the APRS unit. `LIVE` means a fresh read, `CACHED` means the last good value was used, and `MISSING`, `STALE`, or `ERROR` mean the source, identifier, or unit needs attention.

## WX data sources

- `Home Assistant` uses the Home Assistant API and requires `Bearer token`.
- `Domoticz` uses the Domoticz API and supports no authentication or `Basic auth`.
- `Base URL` should point to the main system URL, for example `http://127.0.0.1:8123`.
- `Timeout (s)` limits how long APRSBox waits for the source response.
- `Verify TLS certificate` should stay enabled for valid HTTPS certificates.
- `Enable source` controls whether the source can be used for reads.

The test icon checks the source connection. The discovery icon loads detected entities or devices, which helps you enter the correct `Identifier` in the mapping.

## WX TX Log

The log shows recent WX jobs: time, type, status, interface, attempts, error, and TNC2 frame preview. If a frame is not transmitted, first check required mappings, position, enabled WX state, active TNC, and the error message in the log.
