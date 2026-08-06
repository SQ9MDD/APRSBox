# Configuration backup

This panel exports and restores an APRSBox GUI configuration snapshot in UTF-8 `JSON` format.

## Included data

The snapshot contains selected global settings and configuration for map sources, TNC and APRS-IS interfaces, station and WX, routing flows and rules, APRS objects and items, bulletins, and band-condition reference stations.

Runtime traffic, event logs, message history, user accounts, and other tables outside the supported backup format are not included.

The file can contain callsigns, APRS-IS connection data, paths, endpoints, and other operational configuration. Store it as sensitive data.

## Export and import

- `Export configuration backup` downloads the current snapshot.
- `Import configuration backup` validates the format and version, then replaces the supported configuration tables in one database transaction.
- If validation or a database check fails, the import is rolled back.

Import overwrites the current supported configuration. Export the current state before restoring another file. After a successful import, restart APRSBox services; in Docker, recreate or restart the container using the deployment tool.
