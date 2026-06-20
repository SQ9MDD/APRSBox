# IRLP objects in APRS

This document is a help file for a user creating APRS frequency objects.

The purpose of such objects is to show local radio resources in a way that is readable to mobile operators and as compatible as possible with APRS Frequency Objects practice. The object should help answer simple questions:

- where the resource is located,
- on what frequency it operates,
- what access parameters it requires,
- what its status or short description is.

Objects of this type should have local meaning. They should not be transmitted far beyond the area where the resource is actually useful.

## 1. When to use such an object

An IRLP object is used to describe a local IRLP node and the frequency on which an operator can use it. For a mobile user, the most important things are:

- the IRLP node number,
- the operating frequency,
- the CTCSS tone, DCS, or other access information,
- the node status,
- the callsign or a short description.

## 2. Example object frame

Schematic example:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
```

The frame consists of several parts:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- callsign or description
|        | |      |        | |        | |          |    |    +------- status
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- tone / access
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- longitude
|        | |      |        +--------------------------------------- IRLP symbol table
|        | |      +------------------------------------------------ latitude
|        | +------------------------------------------------------- timestamp
|        +--------------------------------------------------------- object name
+------------------------------------------------------------------ frame type: object
```

## 3. Object name

For IRLP objects, the following names are recommended:

```text
IRLP-1234
IRLP12345
```

The first form is typical for four-digit node numbers. The second may be used if the number has five digits.

Examples:

```text
IRLP-1234
IRLP-5678
IRLP12345
```

The node number should be visible in the object name, because a mobile operator needs it to use the link.

## 4. Alive/dead flag and time

For an active object, use:

```text
*
```

For a fixed object, the following is often used:

```text
111111z
```

Example:

```text
;IRLP-1234*111111z
```

## 5. Coordinates and symbol

In the IRLP format, the `I` symbol table and symbol `0` are used:

```text
5215.00NI02055.00E0
```

Breakdown:

```text
5215.00N   latitude
I          IRLP symbol table
02055.00E  longitude
0          symbol
```

If the exact location should not be published, an approximate position may be used, as long as it still matches the node's local service area.

## 6. Frequency

The frequency is given in the comment:

```text
438.700MHz
```

Recommended format:

```text
xxx.xxxMHz
```

## 7. Tone, DCS, and shift

After the frequency, tone, DCS, and shift may be provided.

Examples:

```text
T103       CTCSS tone 103 Hz
C127       CTCSS 127 Hz, tone access and tone transmit
D023       DCS 023
-760       shift -7.6 MHz
-060       shift -600 kHz
+760       shift +7.6 MHz
```

## 8. Node status

The status should be short and readable.

Examples:

```text
IDLE    idle
BUSY    busy
OFF_    unavailable
```

## 9. Recommended field order

For readability, it is worth keeping the order:

```text
frequency tone/DCS shift status callsign-or-description
```

Example:

```text
438.700MHz T103 -760 IDLE SR5ABC
```

Other examples:

```text
145.575MHz T088 -060 IDLE IRLP
439.000MHz D023 -760 BUSY SR9XYZ
438.700MHz Toff -760 OFF_ Local
```

## 10. Good practices

- Put the IRLP node number in the object name.
- In the comment, provide the frequency in `xxx.xxxMHz` format.
- Add tone, DCS, or shift if needed to use the node.
- The status should be short.
- Do not use a long description. A mobile operator should be able to read the key data without scrolling.
- The object should be transmitted locally, in the area where the node is actually useful.

## 11. Quick reference

```text
;             start of object
IRLP-1234     object name with IRLP node number
IRLP12345     variant for a five-digit number
*             active object
111111z       fixed timestamp
I             IRLP symbol table
0             IRLP symbol
438.700MHz    frequency
T103          CTCSS tone 103 Hz
D023          DCS 023
-760          shift -7.6 MHz
IDLE          example status
SR5ABC        callsign or short description
```
