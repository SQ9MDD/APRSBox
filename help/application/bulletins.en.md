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

- `Type` selects the kind of entry.
- `Code` identifies the bulletin or announcement.
- `Group` assigns the entry to a short group name.
- `Message` contains the actual text.
- `Path` defines the APRS path, if needed.
- `Send interval` and `Activation` control how often and when the frame may be sent.

## Short practical rules

- Use codes `0-9` for general and group bulletins.
- Use codes `A-Z` for announcements.
- Keep the group field short and readable.
- Keep the message text concise and specific.
- The text should fit within 67 characters and use printable ASCII.
- For simple local transmissions, leaving the path blank is usually the safest option unless local practice requires something else.

## Notes

APRS bulletins are not a good place for long descriptions. Short, clear messages are easier to read on radios and simple APRS clients.
