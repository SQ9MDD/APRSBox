# Rate Limit Filter

This filter is not a packets-per-minute counter. It is a simple time gate based on the source callsign.

Rule format:

```text
CALL_OR_PATTERN - LIMIT
```

Examples:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
SQ9MDD - 20s
* - 20s
```

How it works:

- it operates only on the source callsign,
- the first matching frame always passes,
- the next frame from the same source under the same matched rule is blocked until the limit expires,
- timer state is updated only by frames that actually passed,
- if no rule matches the source, the filter does nothing and the frame passes.

How patterns are matched:

- `SQ9MDD-7` without wildcard matches only that exact SSID,
- `SQ9MDD` without wildcard and without SSID matches that callsign with any SSID,
- `SQ*` works as wildcard,
- if several rules match, runtime picks the most specific one; on tie, the earlier line wins.

Format limits:

- `LIMIT` may be written as `30`, `30s`, or `30S`,
- allowed range is 5 to 300 seconds,
- step is 5 seconds.

Use it when:

- very active stations generate too much traffic,
- an RF path needs soft traffic control without a full block.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
