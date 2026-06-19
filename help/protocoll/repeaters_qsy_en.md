# Repeater objects in APRS

This document describes a practical format for a repeater object in APRS. It is intended as a help file for a user creating frequency objects, especially for FM repeaters.

The goal is to prepare a frame that is readable for operators, consistent with APRS Frequency Objects practice, and supported as well as possible by mobile APRS radios.

## 1. Example object frame

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

The frame consists of several logical parts:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- comment, callsign, or description
|        | |      |        | |        | |          |    |    +------- repeater range
|        | |      |        | |        | |          |    +------------ repeater shift
|        | |      |        | |        | |          +----------------- CTCSS tone and FM width
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- longitude
|        | |      |        +--------------------------------------- symbol table
|        | |      +------------------------------------------------ latitude
|        | +------------------------------------------------------- timestamp
|        +--------------------------------------------------------- object name
+------------------------------------------------------------------ frame type: object
```

## 2. Frame type: object

An APRS object starts with a semicolon:

```text
;
```

After the semicolon comes the object name:

```text
;438.462WX
```

In the example, the object name contains the frequency and a local suffix:

```text
438.462WX
```

where:

```text
438.462  - repeater frequency shown as the object name
WX       - local suffix, in Poland often a county code
```

## 3. Object name: frequency and local suffix

For repeater objects, it is recommended that the object name starts with the frequency:

```text
438.462WX
145.600WA
145.775KR
```

This notation is intentional. In APRS repeater and frequency objects, putting the frequency in the object name improves readability on mobile APRS radios. The radio shows the object name in the station list, so the operator can immediately see the repeater frequency without opening the object details.

The frequency should also be repeated in the object comment, for example:

```text
438.462MHz C127 -760 R10k SR5WWL
```

The first occurrence of the frequency, in the object name, is mainly for readability in the object list. The second occurrence, in the comment, is part of the frequency information and may be used by radios or applications for QSY/TUNE functions or for presenting repeater parameters.

The frequency in the name and the frequency in the comment should not be treated as an incorrect duplicate. It is a deliberate compromise resulting from compatibility and practical use of frequency objects.

## 4. Object name uniqueness

The APRS object name has a limited length, so the notation:

```text
frequency + local suffix
```

is a compromise between readability and uniqueness.

Example:

```text
438.462WX
```

means an object for frequency `438.462 MHz` with local suffix `WX`.

In Poland, a county code is often used as the suffix. This helps distinguish repeater objects operating on the same frequency in different locations.

For permanent objects, however, remember that the object may enter the entire APRS-IS network. A local suffix such as a county code reduces the risk of local collisions, but it does not fully guarantee global uniqueness.

Practical rule:

```text
recommended scheme:
    frequency + local suffix
    example: 438.462WX

recommendation:
    the object name should start with the frequency

warning:
    for permanent objects sent to APRS-IS, check
    whether the name is as globally unique as possible
```

If the repeater has a well-known callsign, name, or identifier, it can be placed in the final comment instead of removing the frequency from the object name.

## 5. Alive/dead flag

After the object name comes the alive/dead flag:

```text
*
```

Example:

```text
;438.462WX*
```

Meaning:

```text
*  - active object
_  - deleted or inactive object
```

For a normal working repeater, use `*`.

## 6. Timestamp

The example uses:

```text
111111z
```

Full fragment:

```text
;438.462WX*111111z
```

The `111111z` timestamp is often used as a fixed timestamp for permanent objects.

Practical rule:

```text
fixed or permanent object:
    111111z

temporary object:
    current UTC time generated on each transmission
```

For a fixed object, correct regular refreshing of the object is more important than reporting the exact time when it was generated.

## 7. Coordinates and symbol

Example position:

```text
5218.54N/02113.09Er
```

Breakdown:

```text
5218.54N   latitude
/          symbol table
02113.09E  longitude
r          symbol
```

For the repeater object in the example, symbol `r` is used.

## 8. Repeater frequency in the comment

After the position, provide the repeater operating frequency:

```text
438.462MHz
```

Recommended format:

```text
xxx.xxxMHz
```

Examples:

```text
145.600MHz
438.462MHz
439.000MHz
```

The frequency in the comment should match the frequency used in the object name.

Correct example:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

Suspicious example:

```text
;438.462WX*111111z5218.54N/02113.09Er439.000MHz C127 -760 R10k SR5WWL
```

In the second example, the object name suggests `438.462 MHz`, but the comment gives `439.000 MHz`. Such notation may mislead the operator.

## 9. CTCSS, tone, and FM width

In the example:

```text
C127
```

This means information about the CTCSS tone and repeater mode.

Meaning of letters:

```text
t and c  - narrow FM
T and C  - wide FM

t and T  - repeater opens with tone
c and C  - repeater opens with tone and transmits tone
```

Example interpretation:

```text
T127  - wide FM, repeater opens with 127 Hz tone
C127  - wide FM, repeater opens with 127 Hz tone and transmits tone
t127  - narrow FM, repeater opens with 127 Hz tone
c127  - narrow FM, repeater opens with 127 Hz tone and transmits tone
```

It is worth keeping a three-digit format when the tone has fewer than three digits:

```text
T088
c088
```

## 10. Repeater shift

In the example:

```text
-760
```

It means shift `-7.6 MHz`.

Notation rule:

```text
-760  -> shift -7.6 MHz
-060  -> shift -600 kHz
+760  -> shift +7.6 MHz
+060  -> shift +600 kHz
```

So the value is written as the offset without a decimal separator.

Examples:

```text
145.600MHz -060
438.462MHz -760
439.000MHz +760
```

## 11. Repeater range: Rxxk / Rxxm

For repeater objects, the range can be given as:

```text
Rxxk
Rxxm
```

Meaning:

```text
R10k  - range about 10 km
R25k  - range about 25 km
R15m  - range about 15 miles
```

In the example:

```text
R10k
```

so the declared repeater range is about 10 km.

For repeater objects, the `Rxxk` or `Rxxm` notation is preferred. It should not be confused with the classic `RNGxxxx` extension, which is a different mechanism for describing radio coverage.

## 12. Comment, callsign, or description

At the end, you can place a callsign, repeater name, or short description:

```text
SR5WWL
```

Full ending fragment:

```text
438.462MHz C127 -760 R10k SR5WWL
```

The comment should be short. An APRS frame is not a good place for long descriptions, website addresses, or multi-sentence information.

## 13. Recommended field order in the comment

For readability and compatibility, it is worth keeping a fixed order:

```text
frequency mode/CTCSS shift range comment
```

Example:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Other examples:

```text
145.600MHz T103 -060 R25k SR9ABC
439.000MHz C123 +760 R30k Local
145.775MHz c088 -060 R15k SR5YYY
```

## 14. Recommended form or generator fields

When creating a repeater object, a simple generator that builds the object name and comment from separate fields is helpful.

Suggested fields:

```text
Object name:
    438.462WX

Object name mode:
    frequency + local suffix
    custom name

Local suffix:
    WX

Frequency:
    438.462

CTCSS tone:
    127

Tone mode:
    opens with tone
    opens with tone and transmits tone

FM width:
    narrow FM
    wide FM

Shift:
    -7.6 MHz
    -0.6 MHz
    +0.6 MHz
    +7.6 MHz
    custom

Range:
    10

Range unit:
    km
    miles

Comment:
    SR5WWL
```

Result:

```text
object name:
    438.462WX

comment:
    438.462MHz C127 -760 R10k SR5WWL
```

The generator should ensure that the frequency is visible both in the object name and in the comment. The frequency should not be removed from the name only because it already appears in the comment.

For a permanent object sent to APRS-IS, it is worth showing a warning:

```text
Names of permanent objects should be as globally unique as possible.
The frequency + local suffix scheme is recommended for readability on APRS radios,
but it does not guarantee full uniqueness across the entire APRS-IS network.
```

## 15. Recommended validation

Suggested validation rules:

```text
object name:
    required
    recommended format for repeaters: frequency + local suffix
    example: 438.462WX
    warning if a permanent object is to be sent to APRS-IS
    and the name looks too generic or does not contain a suffix

frequency:
    required
    format xxx.xxx

consistency of name and comment:
    the frequency from the object name should match
    the frequency in the comment, if both are given

CTCSS:
    optional
    only popular CTCSS values or a 2-3 digit number

tone mode:
    t / T / c / C

shift:
    optional
    format +xxx or -xxx

range:
    optional
    format Rxxk or Rxxm

comment:
    optional
    short text without overloading the frame
```

Validation should help the user instead of blocking all unusual cases. For an informed user, it is worth keeping the option of manual correction.

## 16. Ready-made object examples

### UHF repeater, wide FM, CTCSS, shift -7.6 MHz

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

### VHF repeater, wide FM, tone on input, shift -600 kHz

```text
;145.600WA*111111z5215.00N/02055.00Er145.600MHz T103 -060 R25k SR5XXX
```

### VHF repeater, narrow FM, tone on input and output

```text
;145.775KR*111111z5215.00N/02055.00Er145.775MHz c088 -060 R15k SR5YYY
```

## 17. How to read the object details

From the example frame:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

you can read:

```text
Object name: 438.462WX
Frequency from name: 438.462 MHz
Local suffix: WX
Position: 52°18.54'N, 21°13.09'E
Symbol: r
Frequency: 438.462 MHz
CTCSS: 127 Hz
FM width: wide
Tone mode: opens with tone and transmits tone
Shift: -7.6 MHz
Range: 10 km
Description: SR5WWL
```

## 18. Quick reference

```text
;             start of object
438.462WX     object name: frequency + local suffix
*             active object
_             deleted or inactive object
111111z       fixed timestamp
/             symbol table
r             repeater symbol
438.462MHz    frequency in comment
T127          wide FM, opens with 127 Hz tone
C127          wide FM, opens with 127 Hz tone and transmits tone
t127          narrow FM, opens with 127 Hz tone
c127          narrow FM, opens with 127 Hz tone and transmits tone
-760          shift -7.6 MHz
-060          shift -600 kHz
R10k          range 10 km
R15m          range 15 miles
```
