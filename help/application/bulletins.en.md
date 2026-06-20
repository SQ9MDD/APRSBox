# APRS bulletins and announcements

This screen is used to prepare short APRS broadcast messages in message format. Bulletins and announcements are not private messages to a single station.
They are intended for multiple recipients, for example local operators, event participants, a club group, or stations within radio range.

## 1. Theory

### What an APRS bulletin is

An APRS bulletin is a short text message sent to multiple recipients. It may contain a club, organizational, technical, weather, or other information useful during local radio activity.

A bulletin is not a text conversation and should not replace a long description, a website, or a private message to a specific person. Its purpose is to pass useful information quickly, when that information matters here and now.

Good uses for bulletins:

- information about a local net or meeting,
- a message for event participants,
- club information,
- a short notice about repeater, digi, iGate, or field station operation,
- a local technical message,
- a short weather or organizational notice.

Examples of good messages:

```text
NET 19:00 local repeater SR5XXX
HAMFEST parking on 145.550
WX alert: strong wind until 18 UTC
APRS test 12:00-14:00 local area
```

### What an APRS announcement is

An announcement is similar to a bulletin, but it is usually more informational or serves as a notice. In practice, it can be used to publish short notices about activities, events, or important local information.

For the user, the most important difference is simple:

```text
bulletin        short broadcast information, usually numbered with a digit
announcement    short information identified with a letter
```

### Bulletin versus a normal APRS message

A normal APRS message is addressed to a specific station callsign. A bulletin or announcement is addressed to a special recipient of the `BLN` type, so APRS clients can recognize it as a broadcast message.

A bulletin:

- is not a private message,
- is not typical chat,
- should not require a reply from a specific station,
- should be short and understandable without extra context.

## 2. APRS protocol compatibility

Bulletins and announcements are sent as APRS frames in message format. They differ from a normal message because the addressee field contains a special identifier starting with `BLN`.

Typical identifiers:

```text
BLN0       general bulletin number 0
BLN1       general bulletin number 1
BLNA       announcement marked with letter A
BLN0GRP    group bulletin, example with short group GRP
```

The APRS addressee field has limited length, so the code and group name must stay short. It is not worth creating long or non-standard identifiers,
because older radios and simple APRS clients may not display them as expected.

For compatibility and readability, it is best to use:

```text
0-9    for general and group bulletins
A-Z    for announcements
```

The message text should fit within the limits of a short APRS message. A safe practice is to stay within a maximum of 67 characters and use printable ASCII.
It is worth avoiding national characters, special symbols, and formatting, because some radios and older APRS clients may not display them correctly.

## 3. Rules of good use

APRS was designed as a system for current operator information. A good bulletin should answer the question: is this information useful to the stations that receive it here and now?

Best practices:

- write briefly and specifically,
- pass information that is locally or operationally useful,
- use simple language,
- avoid long descriptions,
- avoid repeating too often,
- do not use bulletins as advertising without value for local operators,
- do not send content that would be better placed on a website, in email, or in a messenger.

A good APRS bulletin is a short message with current value for local operators, not text sent to the network only because it is technically possible.

### Send interval

The interval should be chosen reasonably. A bulletin should remind users about useful information, but it should not keep occupying the radio channel.

For local RF transmissions, avoid very short gaps. If the message is not urgent, it is better to send it less often.
For events and field activities, a good approach is to define an activity window and use a moderate repeat interval.

### APRS path

For simple local transmissions, the safest choice is to leave the path blank or use settings consistent with local practice.
An overly wide path may unnecessarily load the radio channel and spread a local message farther than needed.

If the message is meant only for APRS-IS, the RF path usually does not matter.

### Groups

A group makes sense when the message is intended for a specific community, event, club, or local activity. The group name should be short, stable, and easy to recognize.

Good group names:

```text
CLUB
FIELD
ARES
EVENT
SP5
```

Weaker group names:

```text
very_long_group_name
club_meeting_2026
text with spaces and special characters
```

## 4. Form handling

### Type

The `Type` field selects the kind of entry.

Typical choices:

```text
General Bulletin
Group Bulletin
Announcement
```

The selected type determines how the APRS addressee is built and what the supporting fields mean.

### Code

The `Code` field marks a bulletin or announcement with a single character.

Recommended use:

```text
0-9    for bulletins
A-Z    for announcements
```

Examples:

```text
0    first bulletin
1    second bulletin
A    announcement A
B    announcement B
```

Do not change the code unnecessarily if the message is a continuation of the same information. A stable code makes it easier for recipients to recognize that they are seeing an update of the same bulletin or announcement.

### Group

The `Group` field is used mainly for group bulletins. It helps limit the meaning of the message to a specific audience or activity.

The group should be:

- short,
- readable,
- stable,
- written with simple ASCII characters.

Example:

```text
EVENT
CLUB
SP5
```

### Message Text

The `Message Text` field contains the actual APRS message.

The best message text is short, unambiguous, and understandable without extra context. Remember that the message may be read on a small radio screen, not only in a comfortable desktop application.

Recommendations:

- maximum 67 characters,
- printable ASCII,
- no national characters,
- no long sentences,
- no formatting,
- no unnecessary decorations.

Good example:

```text
NET 19:00 SR5XXX, check-ins welcome
```

Weaker example:

```text
Today's meeting of our group will take place this evening, details are on the website, please read the information there.
```

### Path

The `Path` field defines the APRS path used for RF transmission.

For simple local messages, it is best to leave it blank or use only the path accepted locally.
Do not set a wide path only to make the message travel as far as possible. A bulletin should reach the places where it has value for the recipients.

### Send Interval

The `Send Interval` field defines how often the message may be sent again while it is active.

This field does not decide by itself when the message is allowed to be transmitted. The interval works together with the activation mode and schedule.

Example:

```text
Send Interval: 30 minutes
Active from: 10:00 UTC
Active until: 14:00 UTC
```

This means the message may be sent every 30 minutes only within the window from 10:00 to 14:00 UTC.

### Activation

The `Activation` field defines when the entry is active.

Typical modes:

```text
Manual        the entry is turned on and off manually
Scheduled     the entry has one defined activity window
Recurring     the entry returns regularly according to a repeating plan
```

### Active from

The `Active from` field defines the moment when the entry becomes active in UTC.

In scheduled mode, this is the beginning of one transmission window. In recurring mode, this is the first start of the entire cycle.

### Active until

The `Active until` field defines the moment when the entry stops being active in UTC.

In scheduled mode, this is the end of one transmission window. In manual mode, it may serve as an additional validity limit.

### Active for

The `Active for` field defines how long a single cycle stays active in recurring mode.

Example:

```text
Active for: 3 hours
Repeat every: 7 days
```

This means that after each cycle start, the message will stay active for 3 hours.

### Repeat every

The `Repeat every` field defines the gap between consecutive cycle starts.

Example:

```text
Repeat every: 1
Repeat unit: week
```

This means a cycle repeated once per week.

### Repeat unit

The `Repeat unit` field defines the unit used by `Repeat every`.

Typical units:

```text
days
weeks
months
years
```

For months and years, remember that these are calendar units. Not every month has the same number of days.

## 5. Usage examples

### General bulletin

Use: a short message for all recipients.

```text
Type: General Bulletin
Code: 0
Message Text: NET 19:00 SR5XXX, check-ins welcome
Send Interval: 30 minutes
```

Example meaning:

```text
The local net starts at 19:00 on repeater SR5XXX.
```

### Group bulletin

Use: a message for a specific group, event, or activity.

```text
Type: Group Bulletin
Code: 1
Group: EVENT
Message Text: EVENT parking on 145.550 simplex
Send Interval: 20 minutes
```

Example meaning:

```text
Event participants will find information about the parking channel.
```

### Announcement

Use: a short notice or organizational information.

```text
Type: Announcement
Code: A
Message Text: HAMFEST gates open 08:00 UTC
Send Interval: 60 minutes
```

Example meaning:

```text
The announcement informs about the event opening time.
```

## 6. What to watch out for

Avoid:

- very long messages,
- national characters and special symbols,
- repeating too often,
- a wide path without a clear need,
- messages unrelated to the local operator situation,
- content that should be a normal message to a specific station,
- content that should go to a website, email, or messenger.

Remember that the APRS radio channel has limited capacity. Every transmitted bulletin should make sense for the recipients.

## 7. Quick reference

```text
APRS bulletin       short broadcast message
APRS announcement   short notice or information
BLN                 special address used for bulletins and announcements
0-9                 recommended bulletin codes
A-Z                 recommended announcement codes
Group               short identifier of recipients or activity
67 characters       safe limit for message text
ASCII               safest character set
Interval            how often to repeat an active message
Activation          when the message may be transmitted
```

## 8. Main rule

An APRS bulletin should be short, locally useful, and easy to read on simple equipment.
If a message requires a long explanation, many sentences, or linking to additional information, it is probably not suitable as an APRS bulletin.
