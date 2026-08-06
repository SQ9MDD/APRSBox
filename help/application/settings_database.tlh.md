# De' ngaS QummeH

panelvam SQLite storage health 'ang 'ej cleanup actions manual nob. Event logs midnight pIq automatically prune; `VACUUM` runtime history reset je manual ratlh.

## Diagnostics

- File, WAL, SHM sizes physical storage lo'lu'bogh 'ang.
- `Allocated database size`, `Reclaimable space`, `Page geometry` SQLite pagesvo' chen.
- `Integrity check` `PRAGMA quick_check` result 'oH. `ok` 'oHbe'chugh maintenancepa' Qagh yInuD.
- `VACUUM recommendation` reclaimable space threshold je compare.
- Runtime table list row total je reset target exact 'ang.

## VACUUM

`VACUUM` SQLite file chenqa'moH unused pages filesystemvaD nobmeH. PoH nI' poQlaH 'ej database lock temporary. Taghpa' TNC interfaces Hoch disablelu'nIS.

## Runtime logs/data reset

Reset event logs, received traffic, routing runtime state, APRS-IS statistics, WX cache, radar state, band-condition aggregates je Qaw'.

TNC routing configuration, station WX settings, APRS content, map sources, users, APRS message history je Qaw'be'. Resetpa' TNC interfaces Hoch disablelu'nIS.
