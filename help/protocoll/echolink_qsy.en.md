# EchoLink objects in APRS

This document is a help file for a user creating APRS frequency objects.

The purpose of such objects is to show local radio resources in a way that is readable to mobile operators and as compatible as possible with APRS Frequency Objects practice. The object should help answer simple questions:

- where the resource is located,
- on what frequency it operates,
- what access parameters it requires,
- what its status or short description is.

Objects of this type should have local meaning. They should not be transmitted far beyond the area where the resource is actually useful.

## 1. When to use such an object

An EchoLink object is used to describe a local EchoLink node and the frequency on which it can be used. For a mobile operator, the most important things are usually:

- the EchoLink node number,
- the operating frequency,
- the CTCSS or DCS tone, if required,
- the node status,
- the callsign or a short description.

## 2. Example object frame

Schematic example:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
```

In practice, coordinates and description should be replaced with your own data.

The frame consists of several parts:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- callsign or short description
|        | |      |        | |        | |          |    +------- node status
|        | |      |        | |        | |          +------------ tone / access
|        | |      |        | |        +----------------------- symbol
|        | |      |        | +-------------------------------- longitude
|        | |      |        +---------------------------------- EchoLink symbol table
|        | |      +------------------------------------------- latitude
|        | +-------------------------------------------------- timestamp
|        +---------------------------------------------------- object name
+------------------------------------------------------------- frame type: object
```

## 3. Object name

For EchoLink objects, the following name is recommended:

```text
EL-123456
```

where `123456` is the EchoLink node number.

This is important because a mobile operator often needs the node number itself, not only the station callsign. Putting the number in the object name makes it visible in the station or object list on an APRS radio.

Examples:

```text
EL-123456
EL-045678
EL-987654
```

## 4. Alive/dead flag and time

For an active object, use:

```text
*
```

For a fixed object, the following timestamp is often used:

```text
111111z
```

Example:

```text
;EL-123456*111111z
```

## 5. Coordinates and symbol

In the EchoLink format, the `E` symbol table and symbol `0` are used:

```text
5215.00NE02055.00E0
```

Breakdown:

```text
5215.00N   latitude
E          EchoLink symbol table
02055.00E  longitude
0          symbol
```

Some examples use intentionally reduced position precision. If you do not want to show the exact node location, use an approximate position that is still meaningful to a local user.

## 6. Frequency

The frequency is given in the comment:

```text
438.700MHz
```

Recommended format:

```text
xxx.xxxMHz
```

Examples:

```text
145.550MHz
438.700MHz
439.000MHz
```

## 7. Tone, DCS, and access

After the frequency, you may provide CTCSS tone, DCS, or information that no tone is used.

Examples:

```text
T103    CTCSS tone 103 Hz
C127    CTCSS 127 Hz, tone access and tone transmit
D023    DCS 023
Toff    no tone
```

## 8. Node status

EchoLink objects may include a short status. It should be very short, ideally 4 characters.

Examples:

```text
IDLE    idle
BUSY    busy
CONF    conference
OFF_    unavailable
```

If the status is unknown, it is better to use a short description or omit this field instead of writing a long text.

## 9. Recommended field order

For readability, it is worth keeping the order:

```text
frequency tone/DCS status callsign-or-description
```

Example:

```text
438.700MHz T103 IDLE SR5ABC
```

Other examples:

```text
145.550MHz T088 IDLE SR9XYZ
439.000MHz D023 BUSY EchoLink
438.700MHz Toff OFF_ SR5ABC
```

## 10. Good practices

- Put the node number in the object name as `EL-xxxxxx`.
- In the comment, provide the frequency in `xxx.xxxMHz` format.
- Add tone or DCS if required for access.
- The status should be short, ideally 4 characters.
- Do not describe the full EchoLink configuration in the comment. The frame should remain readable on a radio.
- The object should be transmitted locally, where the node is actually useful.

## 11. Quick reference

```text
;             start of object
EL-123456     object name with EchoLink node number
*             active object
111111z       fixed timestamp
E             EchoLink symbol table
0             EchoLink symbol
438.700MHz    frequency
T103          CTCSS tone 103 Hz
D023          DCS 023
IDLE          example status
SR5ABC        callsign or short description
```
