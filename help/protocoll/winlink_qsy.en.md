# Winlink objects in APRS

This document is a help file for a user creating APRS frequency objects.

The purpose of such objects is to show local radio resources in a way that is readable to mobile operators and as compatible as possible with APRS Frequency Objects practice. The object should help answer simple questions:

- where the resource is located,
- on what frequency it operates,
- what access parameters it requires,
- what its status or short description is.

Objects of this type should have local meaning. They should not be transmitted far beyond the area where the resource is actually useful.

## 1. When to use such an object

A Winlink object is used to describe a local radio access point to Winlink, for example a packet gateway. This is not a typical voice repeater object. Its purpose is to show the operator where the local Winlink resource is and what parameters can be used to connect to it.

The most important information:

- the gateway callsign or identifier,
- the operating frequency,
- the packet speed,
- any offset or local notes,
- a short comment.

## 2. Example object frame

Schematic example:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
```

The frame consists of several parts:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- short description
|        | |      |        | |        | |          |    +------- offset / additional information
|        | |      |        | |        | |          +------------ packet speed
|        | |      |        | |        +----------------------- symbol
|        | |      |        | +-------------------------------- longitude
|        | |      |        +---------------------------------- Winlink symbol table
|        | |      +------------------------------------------- latitude
|        | +-------------------------------------------------- timestamp
|        +---------------------------------------------------- object name
+------------------------------------------------------------- frame type: object
```

## 3. Object name

For Winlink objects, the following names are used:

```text
WL-CALL
W1-CALL
W2-CALL
...
W9-CALL
```

Examples:

```text
WL-SR5ABC
W1-SR5ABC
W2-SP9XYZ
```

`WL-` means the basic Winlink object. Variants `W1-` to `W9-` may be used when there are several objects associated with the same callsign or location.

The name should be short and readable, because it is shown in the object list.

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
;WL-SR5ABC*111111z
```

## 5. Coordinates and symbol

In the Winlink format, the `W` symbol table and symbol `a` are used:

```text
5215.00NW02055.00Ea
```

Breakdown:

```text
5215.00N   latitude
W          Winlink symbol table
02055.00E  longitude
a          symbol
```

If the exact gateway position should not be published, an approximate position may be used within the area where the resource is useful.

## 6. Frequency

The frequency is given in the comment:

```text
144.950MHz
```

Recommended format:

```text
xxx.xxxMHz
```

Examples:

```text
144.950MHz
145.050MHz
430.525MHz
```

## 7. Packet speed

In a Winlink object, the place where voice repeaters usually carry tone information is used for packet speed instead.

Examples:

```text
1200
9600
```

Example comment:

```text
144.950MHz 1200 -000 Winlink
```

## 8. Offset and comment

After the speed, you may add offset or a short additional note.

Examples:

```text
-000    no offset, simplex
+060    offset +600 kHz
-060    offset -600 kHz
```

The final comment should be short:

```text
Winlink
RMS
Packet
SR5ABC
```

## 9. Recommended field order

For readability, it is worth keeping the order:

```text
frequency speed offset/description short-comment
```

Example:

```text
144.950MHz 1200 -000 Winlink
```

Other examples:

```text
145.050MHz 1200 -000 RMS
430.525MHz 9600 -000 Winlink
144.950MHz 1200 Packet SR5ABC
```

## 10. Good practices

- Remember that Winlink is a packet/data resource, not a voice repeater.
- In the name, use `WL-` or `W1-` to `W9-` and a callsign or short identifier.
- In the comment, provide the frequency in `xxx.xxxMHz` format.
- Provide packet speed, for example `1200` or `9600`.
- Do not put CTCSS tone in place of packet speed if the object describes a typical Winlink packet point.
- The final description should be short.

## 11. Quick reference

```text
;             start of object
WL-SR5ABC     basic Winlink object name
W1-SR5ABC     additional variant
*             active object
111111z       fixed timestamp
W             Winlink symbol table
a             Winlink symbol
144.950MHz    frequency
1200          packet speed
9600          packet speed
-000          simplex / no offset
Winlink       short description
```
