# Estimated APRS RF channel load

The dashboard's **RF channel load** chart estimates airtime from decoded KISS RX
and locally logged RF TX. It shares the existing activity API, five-minute
aggregation, range/downsampling and bidirectional mouse zoom. It uses Chart.js,
which was already shipped by APRSBox.

Set **RF bitrate (bit/s)** in a serial KISS or TCP KISS interface's settings.
`rf_bitrate` is optional and defaults to unknown (`NULL`) on existing and new
interfaces. Typical values are 1200 and 9600. The UART `baud_rate` is never used
for RF estimates. Unsupported/non-KISS transports have no inferred bitrate.

## Model

For `L` bytes of raw AX.25, excluding FCS, and RF bitrate `R`:

```
frame_seconds = ((L + 2) * 8 * 63/62 + 16) / R
bucket_occupancy_pct = sum(frame_seconds) / bucket_duration_seconds * 100
```

- `L` already contains all AX.25 addresses, control, PID and information bytes.
- Standard KISS provides these bytes without FCS and HDLC flags. Add the two-byte
  FCS once, and two eight-bit delimiter flags. KISS delimiters, command byte,
  escapes, serial start/stop bits and TCP overhead are not radio airtime.
- `63/62` approximates HDLC bit stuffing: independent equiprobable data bits have
  an expected extra zero every 62 data bits. APRS address/text data is not random;
  this is an explicit deterministic approximation, not per-frame bit simulation
  or a claim of exact airtime. No guessed TXDELAY, preamble or TX tail is added.
- For 100 AX.25 bytes: approximately 0.7043 s at 1200 bit/s, 0.08804 s at
  9600 bit/s. Sixty seconds in a 300-second bucket gives 20%.
- Thresholds live together in `app/services/radio_activity.py`: `<20% normal`,
  `20% <= load < 40% busy`, `>=40% congested`. These are diagnostic thresholds,
  not physical limits or ALOHA throughput limits. Values over 100% are preserved
  in the API; the chart has a fixed 0–100% axis.

Each interface is reported separately. Multiple receivers on the same channel
must not be added together; neither should different frequencies. The current
interface model does not describe per-KISS-port RF frequencies or bitrates.
Use this diagnostic only when an interface and its KISS ports represent one RF
channel at one bitrate. It does not deduplicate receptions across interfaces.

RX and a later digipeated TX are two distinct transmissions. The repeat count
is not added again to TX airtime. Network-only APRS-IS frames and `TX-SKIP` are
excluded. `aprsis_to_rf` TX consumes RF airtime even though the existing activity
counters deliberately exclude it; those counters retain their old behavior.

`TX` means the existing outbound dispatcher successfully handed a frame to the
TNC/transport. Standard KISS has no on-air transmission acknowledgement; modem
queueing can shift the real transmission to another bucket or a TNC may drop it.
`TX-PROXY` is logged at proxy ingress without successful-send confirmation, so
its airtime is unknown. OpenWebRX may log JSON length or generated TNC2 (including
non-APRS sources); this model does not treat those lengths as AX.25 or guess from
text. Nonstandard KISS including FCS, FX.25/FEC, LoRa and other PHY overhead are
not modelled.

## API and history

`GET /api/dashboard/radio-activity?range=...` retains its existing fields and adds:

```
rf_channel_load:
  measurement: estimated_aprs_rf_channel_load
  airtime_model: ax25_length_fcs_flags_random_stuffing_v1
  thresholds_pct: {busy: 20, congested: 40}
  interfaces:
    - interface_id: ...
      name: ...
      configured_rf_bitrate: ...  # current configuration, not a historical rate
      series:
        rf_airtime_seconds: [...]
        rf_rx_airtime_seconds: [...]
        rf_tx_airtime_seconds: [...]
        rf_channel_occupancy_pct: [...]
        rf_channel_state: [...]
        rf_frames_total: [...]
        rf_unestimated_frames_total: [...]
```

All arrays use the existing `bucket_starts_utc`, `labels` and
`output_bucket_minutes`. Downsampling sums airtime and divides by the whole
output bucket duration; it does not average percentages incorrectly.

Unknown bitrate, missing raw metadata, legacy rows or incomplete output windows
produce `null` airtime/load/state, not a false zero/normal result. A bucket with
any unestimated eligible frame is conservatively a gap. `rf_frames_total` counts
only estimated RF transmissions; `rf_unestimated_frames_total` counts frames
whose airtime could not be estimated. Fully processed empty buckets are zero.
Older empty periods before the feature boundary are gaps. This also does not
claim that a disconnected or silent receiver actually observed an empty channel.

The additive migration adds nullable `modems.rf_bitrate` and four nullable
columns to `radio_activity_5m` (RX/TX seconds, estimated/unestimated frame counts).
An `app_settings` feature boundary distinguishes old empty periods. It does not
scan, update or backfill traffic logs or reset the existing aggregation cursor.
Old bucket rows remain NULL. Existing retention is unchanged.

The aggregator reads configuration per bucket. There is no historical bitrate
snapshot per packet. Buckets preceding the latest interface settings edit are
conservatively unestimated, including an edit during a bucket, since their RF
bitrate cannot be established. Already aggregated airtime remains unchanged
when settings are edited. This deliberately favors missing data over applying
an incorrect rate to history.

## Hot path audit

Before this change:

1. `TrafficMonitorService._consume_kiss_chunk` separates KISS frames and retains
   receive timestamp/monotonic timestamp.
2. `_record_kiss_frame` unescapes the KISS body, obtains `len(payload)`, decodes
   AX.25 to TNC2 and constructs the existing traffic entry.
3. `_persist_frame` supplies the interface ID, band, raw length, hex and timestamp
   to `process_normalized_tnc2_rx`.
4. The normalized RX function parses TNC2 and calls the already configured
   `DigiFlowRuntimeService.enqueue_rx_tnc2_frame` **before** its existing traffic
   transaction and map/device projections. Existing buffers, message processing
   and other side effects follow. This ordering is unchanged.
5. DigiFlow applies existing routing; the outbound runtime builds KISS, sends it
   and records successful TX through `persist_outbound_frame`. RX `length` is
   raw AX.25; TX `length` is TNC2 text, while TX `hex` stores the KISS frame.

After this change: **zero new per-packet operations in these paths**. No new
SQL/commit, await, lock, queue, parsing, encoding, copy or log line is added.
The traffic, DigiFlow, RF outbound and APRS-IS service files are byte-for-byte
unchanged from the `dev` baseline. The RX-used
`record_traffic_device_station_observation` function has an unchanged AST.

Only the existing background aggregation thread reads two additional traffic
metadata fields, takes one modem configuration snapshot per bucket, and computes
the estimates while already visiting rows. It counts/unescapes stored TX KISS
bytes there; it does not reparse AX.25. The four aggregates are persisted in the
existing per-source bucket UPSERT/transaction. Dashboard reads add grouped
queries over retained buckets/configuration, not raw packet history.

A local alternating before/after microbenchmark (31 runs, 600 logged frames per
bucket, half RX/half TX, band-condition processing off) measured median bucket
collection of **4.54 ms before / 6.04 ms after**: about **1.50 ms per bucket**, or
2.50 microseconds per logged frame **in aggregation**, not in RX/DIGI/TX. At one
such bucket per 300 seconds this is approximately 0.0005% of one CPU's time.
This is a local microbenchmark, not a hardware RF latency guarantee.

## Sources

- Marco Bersani IK2PIH, *APRS Performance and Limits*, revision 1.02, August 2020,
  TAPR DCC 2020. Local copy:
  [PDF](APRS-SPEC/IK2PIH_APRS-Performance_and_limits-rev_1_02.pdf).
  [Original TAPR publication](https://files.tapr.org/meetings/DCC_2020/IK2PIH/IK2PIH_APRS-Performance_and_limits-rev_1_02.pdf).
  Section 2.1 discusses frame length and transmission duration; its assumed
  0.3-second TX delay is not used as knowledge of other stations. The author's
  note explains why decoded-packet statistics cannot reveal collisions.
- [KISS protocol, Chepponis/Karn](https://www.ka9q.net/papers/kiss.html): framing,
  escaping, modem-controlled keying and absence of transmission acknowledgements.
- [AX.25 v2.2, TAPR](https://files.tapr.org/tech_docs/AX25/AX25.2.2.1997.pdf): flags,
  FCS and bit stuffing.

Without DCD telemetry, these estimates cannot measure physical channel occupancy.
Collisions, interference, undecodable signals and other traffic can be invisible.

## Validation (local dev checkout, 2026-09-05)

- New RF tests: **19/19 pass**. Cover 1200/9600/other bitrates, 60 s / 300 s,
  empty and >100% buckets, exact classification boundaries, KISS escaping and
  FCS accounting, malformed/missing metadata, UART separation, RX + repeat,
  APRS-IS exclusion and APRS-IS-to-RF inclusion, gaps, downsampling, configuration
  changes, migration, idempotence and the existing authenticated API endpoint.
- Full suite: **1054 tests, 8 failures + 2 errors**. A clean `git archive dev`
  snapshot with its test database initialized runs 1035 tests with **the exact
  same 8 failures + 2 errors**. No new failing test IDs. Existing failures cover
  alert map/UI behavior, alert models/migrations, a device-statistics count and
  two serial-TX expectations; these unrelated issues were not changed.
- Test command: `python -m unittest discover -s tests -q`, with repository
  requirements plus `httpx` installed in a temporary virtual environment.
  TCP/PTY tests require execution outside the socket-restricting sandbox.
- Browser verification with an isolated synthetic database and radio runtime
  disabled: desktop/mobile layouts, interface switching, shared range, drag zoom
  in both charts, double-click reset, translated tooltip, gaps and 0–100% axis.
  No JavaScript errors. CSS cache key was advanced using the existing convention.
- `git diff --check` passes; the working branch remains `dev`.

Changed/added files:

- `app/services/radio_activity.py`: aggregation, airtime model and existing API payload.
- `app/db.py`: additive schema and feature boundary.
- `app/services/content.py`, `app/sections.py`, `app/routers/pages.py`,
  `app/templates/partials/modem_form_fields.html`: optional RF bitrate settings.
- `app/templates/dashboard.html`, `app/static/css/style.css`,
  `app/templates/base.html`: chart, synchronized interactions and CSS cache key.
- `app/languages/{en,pl,de,es,tlh}.json`: PL/EN/DE/ES translations; new English
  fallback entries in the Klingon catalog preserve the existing catalog key parity.
- `tests/test_rf_channel_load.py`: new tests.
- `RF-CHANNEL-LOAD.md`: this model, audit and validation report.
- `APRS-SPEC/IK2PIH_APRS-Performance_and_limits-rev_1_02.pdf`: original 32-page
  Bersani publication downloaded from TAPR, including its author/license notice.
