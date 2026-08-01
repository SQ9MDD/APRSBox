# APRS device identification

APRSBox uses this database to recognize APRS software and hardware from destination `TOCALL` values and Mic-E identifiers. The result is shown in station details and device statistics.

## Active data source

APRSBox prefers a valid local cache. If no valid cache is available, it uses the snapshot bundled with the application.

- `Status` reports whether the cache or bundled fallback is active.
- `Active source` shows the source currently used for lookups.
- `Generation time` is the timestamp embedded in the identification dataset.
- `Last successful update` records the most recent completed download.
- `Local cache` and `Local cache updated` describe the downloaded file.
- `Last update error` remains visible after a failed refresh.

## Updating

`Update now` downloads a new dataset, validates its structure, and replaces the local cache only after validation succeeds. A failed download does not remove the usable bundled snapshot or a previously valid cache.

The update requires network access and can be started only by an administrator or operator.
