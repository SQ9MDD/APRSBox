# Bulletins and announcements

This document describes the basic use of the `Bulletins / Announcements` tab in APRSBox.

This screen is used to prepare APRS message-format frames for bulletins and announcements.

## Use cases

Bulletins and announcements are useful for short text information such as:

- club and operator notices,
- short organizational messages,
- event reminders,
- local technical or weather notices.

## Basic fields

- `Type` selects the kind of entry, for example a general bulletin, group bulletin, or announcement. This affects how the APRS addressee is built and which supporting fields are relevant.
- `Code` identifies the bulletin or announcement with a single character. Bulletins usually use digits `0-9`, while announcements use letters `A-Z`, which makes the message type easier to recognize on the receiving side.
- `Group` assigns the entry to a short group name, mainly for group bulletins. This value should stay short, readable, and stable because it becomes part of the identifier visible to the receiver.
- `Message` contains the actual text sent to the APRS network. It is best to keep it short and unambiguous so it can be read easily on a radio or simple APRS client without scrolling or guessing the context.
- `Path` defines the APRS path if one should be used for RF transmission. For simple local messages, leaving this field blank is usually safest unless local operating practice requires a specific path.
- `Send interval` defines how often the entry may be retransmitted, while `Activation` defines when the entry is allowed to be active. In practice, these fields work together: one controls the spacing between transmissions and the other controls the time window in which sending is allowed at all.

## Short practical rules

- Use codes `0-9` for general and group bulletins.
- Use codes `A-Z` for announcements.
- Keep the group field short and readable.
- Keep the message text concise and specific.
- The text should fit within 67 characters and use printable ASCII.
- For simple local transmissions, leaving the path blank is usually the safest option unless local practice requires something else.

## Notes

APRS bulletins are not a good place for long descriptions. Short, clear messages are easier to read on radios and simple APRS clients.
