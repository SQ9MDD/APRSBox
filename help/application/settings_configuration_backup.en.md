# Configuration backup

This panel exports and restores an APRSBox GUI configuration snapshot in UTF-8 `JSON` format.

## Included data

The v2 snapshot contains global, message, and notification settings and configuration for map sources, TNC and APRS-IS interfaces, station and WX, notification transports and radar rules, routing flows and rules, APRS objects and items, bulletins, and band-condition reference stations.

Runtime traffic, transport test results, notification radar state, event logs, message history, own APRS alerts, user accounts, and other tables outside the supported backup format are not included.

The file can contain callsigns, APRS-IS connection data, paths, endpoints, webhook and Telegram tokens, and other operational configuration. Store it as sensitive data.

## Export and import

- `Export configuration backup` downloads the current snapshot.
- `Import configuration backup` validates the format and version, then replaces the supported configuration tables in one database transaction.
- If validation or a database check fails, the import is rolled back.
- Only the v2 format is supported. V1 files created by older releases cannot be imported.

Import overwrites the current supported configuration. Export the current state before restoring another file. After a successful import, restart APRSBox services; in Docker, recreate or restart the container using the deployment tool.
