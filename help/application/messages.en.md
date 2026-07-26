# APRS messages

This tab is used for APRS conversations stored locally in the SQLite database. The list on the left shows correspondents, and the panel on the right shows the selected thread and send form.

## Conversations

- `Start new conversation` accepts an APRS callsign in `CALL` or `CALL-SSID` form.
- The base callsign can have up to 6 characters, with an optional SSID `0-15`, for example `SP9XYZ-7`.
- Selected APRS service destinations are also allowed, such as `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU`, or `CQ`.
- Opening a conversation marks incoming messages in that thread as read.
- The sidebar `Messages` icon changes when unread messages exist.

The conversation row also shows whether the station was heard recently. A green state means fresh traffic, a warning state means older recent traffic, and no entry means there is no recent frame in the local traffic history.

## Message settings

The `Message settings` block is located below the conversations panel:

- `Default path` is used for new conversations, group messages, and automatic APRS responses.
- `Receive messages for any SSID of my callsign` allows messages addressed to other SSIDs of the same base callsign to be displayed. Only the exact configured `CALL-SSID` receives an `ACK` or an automatic response.
- `Target groups` defines the shared message addresses that APRSBox receives.

On first use, when no group setting has been saved yet, the list contains `ALL`, `QST`, and `CQ`. If the user removes these values and saves an empty field, the list remains empty.

Groups are entered in one field and separated by commas, for example `CQ, QST, ALL, WAW, BEM`. Spaces around names are removed, letters are converted to uppercase, and duplicates are discarded. Each name must contain between `1` and `9` characters from `A-Z` or `0-9`. Empty entries, special characters, internal spaces, and addresses beginning with `BLN` are rejected.

## Group conversations

- A group conversation is created only for an addressee present in the saved `Target groups` list.
- A message to an undefined group, such as `BEM`, is ignored: it creates no conversation, history entry, unread state, notification, or `ACK`.
- The conversation key is the group address, for example `WAW`, rather than the sender callsign. Messages from multiple stations appear in the same chronological `WAW` thread.
- The actual sender, for example `SQ5WLA-9`, is shown above every group-message bubble. An outbound message is labelled `You · CALL-SSID`.
- A message sent by APRSBox to a group is transmitted once, without a message number, without waiting for an `ACK`, and without automatic retries.
- APRSBox never acknowledges a group message, even if the sending device included a message number.
- Removing a group from settings stops new messages to that group from being received, but does not delete the existing conversation history.

A group is not a station, so its thread does not show a “heard recently” state. `BLN...` bulletin addresses are handled separately and cannot be added as ordinary message groups.

## Sending

- APRS message text is limited to `67` printable ASCII characters.
- National characters and control characters are blocked because the classic APRS message format is a short ASCII field.
- The `Path` field sets the RF path for transmission. If it is left empty, the `Default path` from message settings is used.
- The path is remembered per conversation and can also be used by automatic ACKs.

A normal message in a direct conversation receives an APRS message number and waits for `ACK` or `REJ` from the remote station. Group messages follow the no-ACK and no-retry rules described above.

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

Incoming numbered messages and queries are acknowledged automatically with an `ack` frame only when addressed exactly to the configured local `CALL-SSID`. Group messages and messages addressed to another SSID of the local callsign are neither acknowledged nor handled by automatic responses.
