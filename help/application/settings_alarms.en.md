# APRS alarm settings

This panel controls alarm intake, transfer to the Alerts list, emergency-style popups, and the automatic APRS-IS filter for alarm groups.

## Main switch and groups

- `Enable APRS alarms` turns alarm processing on or off.
- `Alarm groups` accepts one or more APRS group names separated by commas.
- Configured alarm groups are added to the effective RF message receive groups and to the automatic APRS-IS alarm-group filter.

The summary below the form shows the effective RF groups and the exact automatic filter generated from the saved configuration.

## Thresholds by event type

Each event category has two independent thresholds:

- `Alerts` controls transfer from Messages to the Alerts list.
- `Alert popup` controls the emergency-style popup.
- A numeric value accepts that severity and all higher severities.
- `Off` disables the category in that column.

Unknown severity values are preserved for safety instead of being silently discarded.

Alarm visibility on the map is managed directly from the alarm panel on the Map page. These settings do not replace that map control.
