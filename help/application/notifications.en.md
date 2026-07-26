# Notifications

This tab configures external notifications sent by APRSBox. Notifications work in two steps: first define a transport, then enable the event types that should be sent.

## Transports

A transport defines where APRSBox sends an event.

- `Webhook` sends the event as an HTTP `POST` with a JSON body to the configured URL.
- `Telegram` sends a message through a Telegram bot to the configured `Chat ID`.
- During normal event dispatch, only transports marked `Enabled` are used.
- The test button sends an `APRSBox notification test` event and stores the transport test result.

For webhooks, you can configure `Secret header name` and `Secret token`. If both fields are filled, APRSBox adds that HTTP header to the request.

`Timeout` is counted in seconds. The allowed range is `1` to `60`, and the default is `5`.

When editing an existing transport, leaving a secret field empty keeps the existing secret unchanged.

## Notification settings

- `Enable APRS message notifications` enables notifications for incoming APRS messages.
- `Include message content` controls whether the APRS message text is included in the notification.
- `Enable radar notifications` enables station radar rules.
- `Ignored radar patterns` excludes stations from radar processing. Patterns can be separated with commas or line breaks. The `*` wildcard is supported.

Disabling radar notifications clears the remembered repeat-block state and the radar event log.

## Radar rules

A radar rule detects stations matching a callsign pattern and an optional distance limit from `My Station`.

- `Radar rule` is a callsign or callsign pattern, such as `SQ6ODL-*`, `SR*`, or `*`.
- `Distance (m)` is the maximum distance from the local station coordinates.
- A value of `0` means no distance limit.
- If the distance is greater than `0`, a station without known coordinates will not match the rule.

Radar sends a notification only when a station enters the rule range. As long as the station stays in range, repeat notifications are blocked. The block is removed only after the station leaves the range or its position expires from visible data.

The local station and the active APRSBox weather station are ignored automatically.

## Radar event log

The log shows recent radar state changes: notification sent, repeat block created, and block removed after the station leaves the range.
