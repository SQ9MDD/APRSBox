# Database maintenance

This panel reports SQLite storage health and provides manual cleanup actions. Event logs are pruned automatically after midnight; `VACUUM` and runtime history reset remain manual.

## Diagnostics

- File, WAL, and SHM sizes show the physical storage currently used by SQLite.
- `Allocated database size`, `Reclaimable space`, and `Page geometry` are calculated from SQLite pages.
- `Integrity check` is the result of `PRAGMA quick_check`. Investigate any result other than `ok` before maintenance.
- `VACUUM recommendation` compares reclaimable space with the threshold shown in the panel.
- The runtime table list and row total show exactly what the reset action currently targets.

## Run VACUUM

`VACUUM` rebuilds the SQLite file so unused pages can be returned to the filesystem. It can take time and temporarily lock the database. All TNC interfaces must be disabled before it can run.

## Reset runtime logs/data

The reset clears operational history such as event logs, received traffic, routing runtime state, APRS-IS runtime statistics, WX runtime cache, radar state, and band-condition aggregates.

It does not remove TNC or routing configuration, station and WX settings, APRS content, map sources, users, or APRS message history. All TNC interfaces must be disabled before the reset can run.
