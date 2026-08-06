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

Use `Save Global Settings` to apply globally stored values.
