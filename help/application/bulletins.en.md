# Bulletins and announcements

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
- `Send interval` defines how often the entry may be retransmitted. This setting does not decide when sending is allowed, only the spacing between repeated transmissions while the entry is active.
- `Activation` selects the activation mode for the entry. `Manual` means manual enablement without a schedule, `Scheduled` defines one continuous time window, and `Recurring` is used for a repeating activity plan.
- `Active from` defines when the entry becomes active in UTC. In `Scheduled` mode, this is the start of a single activity window, while in `Recurring` mode it is the first start time of the whole cycle.
- `Active until` defines when the entry stops being active in UTC. In `Scheduled` mode, it usually marks the end of the transmission window, while in manual mode it may still be used as an additional validity limit.
- `Active for` defines how long a single active cycle lasts in `Recurring` mode. In other words, it sets the length of one transmission window after each cycle start.
- `Repeat every` defines how often the cycle repeats in `Recurring` mode. Together with the repeat unit, it sets the gap between successive starts of the active window.
- `Repeat unit` defines the unit used by `Repeat every`, for example days, weeks, months, or years. This decides whether the schedule repeats in simple daily or weekly steps or in longer calendar-based intervals.

## Short practical rules

- Use codes `0-9` for general and group bulletins.
- Use codes `A-Z` for announcements.
- Keep the group field short and readable.
- Keep the message text concise and specific.
- The text should fit within 67 characters and use printable ASCII.
- For simple local transmissions, leaving the path blank is usually the safest option unless local practice requires something else.
- With scheduled entries, remember that `Send interval` and `Activation` work together: the schedule defines when sending is allowed, and the interval defines how often the entry is sent within that allowed window.

## Notes

APRS bulletins are not a good place for long descriptions. Short, clear messages are easier to read on radios and simple APRS clients.
