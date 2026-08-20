# Global settings

This panel controls application-wide display, retention, and logging defaults. Administrators and operators can save changes; viewers can only inspect the current values.

## Language and units

- `Language` selects the language used by the web interface and contextual help.
- `Units` selects metric or imperial values wherever the application supports unit conversion.
- `Icon set` selects the legacy or modern APRS symbol artwork.
- `Color palette` changes the application color palette for all users.

## Traffic and event logs

- `Traffic history retention` controls how long runtime traffic frames remain in the database. Map and station visibility follow this window.
- `Minimum stored log level` stores the selected level and all more severe event levels.
- `Enable DEBUG logs` allows verbose diagnostic entries. Use it temporarily when troubleshooting because it can increase the number of stored events.

## Coverage display

- `Coverage fill opacity` is saved globally and controls the fill inside coverage areas on the map.
- `Coverage outline opacity` controls only the border and is stored locally in the current browser.
- A value of `0%` hides the corresponding fill or outline.
- `Group overlapping station icons on the map` replaces nearby symbols with a blue icon showing the station count. It is disabled by default so the map shows individual APRS symbols until an operator explicitly enables clustering.
- `Enable spreading overlapping markers` spreads overlapping individual markers on mouse hover near the maximum zoom; clicking a spread icon opens station details, while moving the pointer outside the group collapses it again. On touch devices, the first tap spreads the group and the second opens the selected station.
- `Activate X levels before maximum zoom` sets the activation threshold relative to the active map source's maximum zoom. The default `2` activates at zoom 14, 16, or 18 when the maximum is 16, 18, or 20 respectively.
- `Overlapping marker distance [px]` controls how close visible marker centers may be before they are treated as overlapping. The default is `20` px.

Use `Save Global Settings` to apply globally stored values.
