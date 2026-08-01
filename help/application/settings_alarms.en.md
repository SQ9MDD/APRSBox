# APRS alarm settings

This panel configures the receive-only alarm channel for APRS group messages. It controls which destination groups are treated as alarms, which events reach the Alerts list, which may open an emergency-style popup, and which groups are appended to the APRS-IS receive filter.

## Quick configuration

- Enable `APRS alarms`.
- Enter comma-separated group addressees, for example `PL-WARN, NWS-WARN`.
- Set the `Alerts` and `Alert popup` thresholds for each event category.
- Save and check the effective RF groups and automatic APRS-IS filter shown below the form.

A group name must contain 1–9 uppercase letters, digits, or hyphens. Lowercase input is converted to uppercase, duplicates are removed, and `BLN...` bulletin addresses are rejected.

## What happens to a received frame

- Only an APRS message addressed to an enabled, configured alarm group enters this path.
- The event name selects a category such as tornado, thunderstorm, flood, wind, heat, or `Other / unknown`.
- The final digits of the event code are interpreted as severity.
- `Alerts` decides whether the frame creates or updates a record in the Alerts list.
- `Alert popup` independently decides whether the first frame of that alarm may open the global popup.
- The map layer has its own visibility control on the Map page and requires a matching local geometry record for each area code.

For a numeric threshold, that level and higher levels are accepted. `Off` disables the category in that column. Unknown severity is retained when the category is enabled, so a new or malformed format is not silently discarded; it has no yellow/orange/red classification and is shown in gray where geometry is available.

## Supported warning envelopes

- [CAWF detailed guide](settings_alarms_cawf.en.md) — country profiles such as `PL-WARN`, multipart alerts, area geometry, lifecycle, and trust.
- [NWS-WARN detailed guide](settings_alarms_nws_warn.en.md) — the U.S. county-warning envelope, UGC county codes, map coverage, and APRSBox limitations.
- [Alerts list, muting, and deletion](alerts.en.md) — operator actions after an alert has been accepted.

## Important boundaries

- The switch affects configured alarm groups. Native APRS emergency and Mic-E emergency frames use the shared Alerts system independently.
- Alarm-group messages are not added to ordinary conversations, do not trigger normal message notification transports, and are never acknowledged with an APRS ACK.
- APRSBox does not currently authenticate warning publishers or maintain a trusted-sender allowlist. APRS-IS delivery alone is not proof that a warning is official.
- An invalid or missing `DDHHMMz` expiry cannot be resolved automatically. Such a record may remain active until it is replaced or deleted by an operator.
