# APRS messages

This tab is used for APRS conversations stored locally in the SQLite database. The list on the left shows correspondents, and the panel on the right shows the selected thread and send form.

## Conversations

- `Start new conversation` accepts an APRS callsign in `CALL` or `CALL-SSID` form.
- The base callsign can have up to 6 characters, with an optional SSID `0-15`, for example `SP9XYZ-7`.
- Selected APRS service destinations are also allowed, such as `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU`, or `CQ`.
- Opening a conversation marks incoming messages in that thread as read.
- The sidebar `Messages` icon changes when unread messages exist.

The conversation row also shows whether the station was heard recently. A green state means fresh traffic, a warning state means older recent traffic, and no entry means there is no recent frame in the local traffic history.

## Sending

- APRS message text is limited to `67` printable ASCII characters.
- National characters and control characters are blocked because the classic APRS message format is a short ASCII field.
- The `Path` field sets the RF path for transmission. If it is left empty, the default station path from beacon settings is used.
- The path is remembered per conversation and can also be used by automatic ACKs.

A normal message receives an APRS message number and waits for `ACK` or `REJ` from the remote station.

## Statuses

- `Queued` means the message is waiting in the outbound queue.
- `Sent` means the frame has been transmitted.
- `Sent X/Y` shows the attempt number and attempt limit for a numbered message.
- `ACK` means the remote station acknowledged the message.
- `Rejected (REJ)` means the remote station rejected it.
- `No ACK` means no acknowledgement was received after the retry window.

For normal messages, APRSBox schedules automatic retries across later attempts. After the attempts are exhausted, a failed message can be sent again manually with the `No ACK` button.

## APRS queries

If the text starts with `?`, the message is treated as an APRS query. Such frames are sent without a message number and do not use the same automatic ACK/retry window as normal messages.

APRSBox recognizes and automatically answers incoming queries:

- `?APRS`,
- `?APRSP`,
- `?APRSS`,
- `?APRSD`,
- `?DX`,
- `?APRSV`,
- `?VER`.

Incoming numbered messages and queries are acknowledged automatically with an `ack` frame.
