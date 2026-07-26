# APRS paths in practice

This page explains APRS paths from the protocol point of view: how to read notation such as `WIDE2-1`, what the difference is between traced and non-traced paths, and how one-part and two-part paths are actually processed.

## 1. What an APRS path is

An APRS path is a list of hops or aliases that tells the RF network how a frame may be repeated further.

Examples:

```text
WIDE2-1
SP2-2
WIDE1-1,WIDE2-1
SP1-1,SP2-2
WIDE2-1,RFONLY
```

Key rules:

- path elements are separated with commas,
- the path is processed from left to right,
- the next element is not touched until the first still-unconsumed element is handled,
- `RFONLY` and `NOGATE` are not repeat hops, but markers that restrict gating to APRS-IS.

In practice, local transmission without digipeaters means no path at all. Many programs and radios also use the convenient label `DIRECT`, but at protocol level this simply means transmission without digi hops.

## 2. How to read `N-N`

In paths such as `WIDEn-N` or `SPn-N`, the number on the left identifies the alias family and its initial scope, while the number on the right acts as the remaining repeat counter.

Example:

```text
WIDE2-2
```

means that the frame may still be repeated two times by successive digipeaters. After the first repeat, the counter is reduced:

```text
WIDE2-2 -> WIDE2-1
```

After the second repeat, the path is consumed:

```text
WIDE2-1 -> WIDE2*
```

The asterisk `*` marks an element that has already been used and should not be used again for further repeats.

Similarly:

```text
SP2-2 -> SP2-1 -> SP2*
```

## 3. Traced and non-traced paths

The main difference is whether the digipeater inserts its own callsign into the path.

### Traced path

With a traced path, each digipeater that repeats the frame leaves a visible trace. That makes it possible to see how the packet travelled through RF.

Example:

```text
SP8XYZ-9>APRS,WIDE2-2:...
```

After the first digi:

```text
SP8XYZ-9>APRS,SR5AAA*,WIDE2-1:...
```

After the second digi:

```text
SP8XYZ-9>APRS,SR5AAA*,SR5BBB*:...
```

Advantages:

- packet routing is easier to inspect,
- network behaviour is easier to diagnose.

Disadvantage:

- the frame grows with every repeat because additional digi callsigns are inserted.

### Non-traced path

With a non-traced path, the digipeater does not insert its own callsign. It only reduces the counter or marks the element as consumed.

Example:

```text
SP8XYZ-9>APRS,SP2-2:...
```

After the first digi:

```text
SP8XYZ-9>APRS,SP2-1:...
```

After the second digi:

```text
SP8XYZ-9>APRS,SP2*:...
```

Advantages:

- shorter frame,
- less packet growth across repeated hops.

Disadvantage:

- you cannot see which exact digipeaters forwarded the frame.

In practice, `WIDE` aliases are usually traced, while national or regional aliases such as `SP` or `WM` are sometimes configured as non-traced. That is not a magical property of the alias word itself, but a result of local digi network configuration.

## 4. One-part path

A one-part path has one element, but that does not necessarily mean only one repeat.

Examples:

```text
WIDE2-1
WIDE2-2
SP2-1
SP2-2
```

Interpretation:

- `WIDE2-1` is one path element and one repeat,
- `WIDE2-2` is one path element and two repeats,
- `SP2-1` is one path element and one repeat,
- `SP2-2` is one path element and two repeats.

This is a common trap: the number of path elements is not the same thing as the number of repeats.

Traced one-part example:

```text
WIDE2-2
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

Non-traced one-part example:

```text
SP2-2
-> SP2-1
-> SP2*
```

## 5. Two-part path

A two-part path has two elements separated by a comma and is always processed from left to right.

Example:

```text
WIDE1-1,WIDE2-1
```

The first element must be consumed first:

```text
WIDE1-1,WIDE2-1
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

There is one important practical detail here: a first element such as `WIDE1-1` or `SP1-1` usually has the special role of a helper segment for `fill-in digi` stations.

As a rule, such a digi should consume only that first element and should not continue repeating the rest of the path. For a handheld or mobile station, `WIDE1-1` is mainly there so that nearby home stations or other local helper digis can bridge the local coverage hole, but stop after handling only `WIDE1-1`.

Another example:

```text
SP1-1,SP2-2
```

Processing:

```text
SP1-1,SP2-2
-> SP1*,SP2-2
-> SP1*,SP2-1
-> SP1*,SP2*
```

Important conclusions:

- `WIDE1-1,WIDE2-1` is two path elements and two repeats in total,
- `WIDE1-1,WIDE2-2` is two path elements, but three repeats in total,
- `SP1-1,SP2-2` is also two path elements and three repeats in total.
- a first element such as `WIDE1-1` or `SP1-1` usually makes sense as the helper segment for a digi that stops after consuming only that single hop.

A traced two-part path grows faster than a non-traced path because each hop may add another digi callsign.

## 6. `RFONLY` and `NOGATE`

At the end of a path you may also see extra markers:

```text
WIDE2-1,RFONLY
WIDE1-1,WIDE2-1,NOGATE
```

In practice they serve a similar purpose: they are used to block gating of RF traffic to APRS-IS.

These elements:

- do not add repeat hops,
- do not extend RF range,
- only limit movement of traffic toward the internet side.

## 7. Practical conclusions

- no path means local transmission without digi repeats,
- a one-part path is often enough where many repeats are not needed,
- a two-part path gives more reach, but quickly increases the number of copies on channel,
- traced paths are better for diagnostics,
- non-traced paths usually keep the frame shorter,
- combinations starting with `WIDE1-1` make sense only if they fit local practice and local network topology,
- it is always best to follow the recommendations used in your region, because the local digi network decides which aliases actually work and how they are processed.
