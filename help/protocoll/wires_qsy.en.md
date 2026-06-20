# WiRES / WiRES-X objects in APRS

The purpose of such objects is to show local radio resources in a way that is readable to mobile operators and as compatible as possible with APRS Frequency Objects practice. The object should help answer simple questions:

- where the resource is located,
- on what frequency it operates,
- what access parameters it requires,
- what its status or short description is.

Objects of this type should have local meaning. They should not be transmitted far beyond the area where the resource is actually useful.

## 1. When to use such an object

A WiRES or WiRES-X object is used to describe a local node or repeater associated with the Yaesu WiRES / WiRES-X network. Such an object may be useful to a mobile operator who sees APRS information about a local resource on the radio and can quickly switch to the correct frequency.

Typical uses:

- a local repeater with WiRES-X access,
- a local WiRES node,
- information about frequency, DCS/CTCSS, shift, and range,
- a short description or repeater callsign.

## 2. Example object frame

Practical example:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
```

The frame consists of several parts:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- callsign or short description
|        | |      |        | |        | |          |    |    +------- range
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- DCS / SQL / tone
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- longitude
|        | |      |        +--------------------------------------- symbol table
|        | |      +------------------------------------------------ latitude
|        | +------------------------------------------------------- timestamp
|        +--------------------------------------------------------- object name
+------------------------------------------------------------------ frame type: object
```

## 3. Object name

For WiRES objects, a name starting with:

```text
WIR-
```

is recommended.

Examples:

```text
WIR-17967
WIR-1101D
```

The name should show the WiRES node number or identifier, because this number is important to the operator who sees the object in the station list.

For a WiRES-X object associated with a repeater, it is worth keeping the name in the `WIR-xxxxx` form, and putting the frequency, shift, and access parameters in the comment.

## 4. Alive/dead flag and time

After the object name comes the alive/dead flag:

```text
*
```

Meaning:

```text
*  - active object
_  - deleted or inactive object
```

For a fixed object, the following timestamp is often used:

```text
111111z
```

Example:

```text
;WIR-17967*111111z
```

## 5. Coordinates and symbol

The example uses the classic repeater symbol:

```text
5356.33N/02150.80Er
```

Breakdown:

```text
5356.33N   latitude
/          symbol table
02150.80E  longitude
r          repeater symbol
```

In APRS Frequency Objects practice for WiRES, you may also see the `W` symbol table and symbol `0`, intended for marking a WiRES node. In practice, if the object describes a repeater with WiRES-X, the repeater symbol `r` may be clearer for the user.

## 6. Frequency

The frequency is given in the comment:

```text
438.525MHz
```

Recommended format:

```text
xxx.xxxMHz
```

Examples:

```text
438.525MHz
439.000MHz
145.600MHz
```

## 7. DCS, CTCSS, SQL, and access

In the example:

```text
DOFF
```

means information related to DCS or squelch. In WiRES / WiRES-X objects, different local practices may exist, so the most important thing is that the notation is short and unambiguous for operators in the region.

Examples of access fields:

```text
D023    DCS 023
D754    DCS 754
DOFF    DCS disabled or no DCS, according to local description practice
T103    CTCSS tone 103 Hz
C127    CTCSS 127 Hz, repeater opened by tone and transmitting tone
```

## 8. Shift

Shift is written as an offset without a decimal separator:

```text
-760
```

Meaning:

```text
-760  - shift -7.6 MHz
-060  - shift -600 kHz
+760  - shift +7.6 MHz
+060  - shift +600 kHz
```

## 9. Range

Range may be given as:

```text
Rxxk
Rxxm
```

Examples:

```text
R99k  - range about 99 km
R25k  - range about 25 km
R15m  - range about 15 miles
```

## 10. Recommended field order

For readability, it is worth keeping a fixed order:

```text
frequency DCS/CTCSS shift range description
```

Example:

```text
438.525MHz DOFF -760 R99k SR4MIT
```

Other examples:

```text
438.525MHz D023 -760 R50k Wires node
439.000MHz T103 -760 R30k Local Wires
145.600MHz C127 -060 R25k WIRES-X
```

## 11. Good practices

- Use the name `WIR-xxxxx` if you know the node number.
- In the comment, provide the frequency in `xxx.xxxMHz` format.
- Add shift if the resource works through a repeater.
- Add DCS, CTCSS, or a short access note if needed.
- Add range only if you have a sensible approximate value.
- The final comment should be short, for example a repeater callsign or local name.

## 12. Quick reference

```text
;             start of object
WIR-17967     object name with WiRES node number
*             active object
111111z       fixed timestamp
r             repeater symbol, practical for a repeater object
438.525MHz    frequency
D023          DCS 023
DOFF          no DCS or DCS disabled, according to local practice
T103          CTCSS tone 103 Hz
-760          shift -7.6 MHz
R99k          range about 99 km
SR4MIT        callsign or short description
```
