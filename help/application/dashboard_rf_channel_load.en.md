# Activity charts and estimated APRS RF channel load

This block contains two charts that share the same time range, buckets, and zoom. The upper chart shows APRS traffic event counts. The lower chart estimates APRS RF channel load. Choose a range at the block's upper right; drag on a chart to zoom and double-click to restore the full range.

## Upper chart: APRS activity

The upper chart shows the number of events in each bucket:

- **RX** — frames received by APRSBox,
- **TX** — locally logged RF transmissions,
- **repeats** — transmissions marked as digipeated,
- **APRS-IS uplink** — frames sent from APRSBox to APRS-IS.

These are frame counts, so they do not directly express channel occupancy: short and long frames have the same value. APRS-IS uplink is Internet traffic and does not consume RF airtime.

## Lower chart: RF channel load

The lower chart estimates APRS RF channel load from frames APRSBox successfully receives and decodes, plus locally logged RF transmissions. It is a diagnostic view of observed APRS traffic, not a measurement of actual physical channel occupancy.

Each point is estimated RF airtime divided by the full bucket duration. For example, `60 s` of airtime in a `5 min` bucket produces `20%` load.

Select one RF interface. Its KISS ports must represent one physical RF channel. APRSBox never sums separate interfaces because they may use different frequencies or hear the same traffic through separate receivers.

Data appears when a complete aggregation bucket closes. A gap means there is insufficient data for an estimate, not a zero-load channel.

## Airtime model

APRSBox uses the available raw AX.25 frame length rather than the TNC2 text length or KISS framing. KISS `SERIALL` and `TCP` interfaces use the fixed RF bitrate `1200 bit/s`; a serial UART `Baud Rate` is not the radio-modem bitrate and is never used here.

It adds two physical FCS bytes and two HDLC flag delimiters. HDLC bit stuffing is represented by a fixed deterministic `63/62` approximation, without analyzing each frame's bitstream:

```
airtime_s = ((AX.25_length + 2) × 8 × 63/62 + 16) / 1200
```

KISS framing is not RF airtime. APRSBox generally does not know another station's TXDELAY, preamble, or tail, so it does not invent them. The chart therefore reports estimated frame airtime, not complete carrier time.

Bucket load is:

```
load_% = total_airtime_s / bucket_duration_s × 100
```

Values over `100%` remain visible. They mean the sum of logged transmission events exceeds the bucket duration; APRSBox does not hide or clamp them. APRS-IS uses no RF airtime. A frame received over RF and later digipeated produces two RF transmission events, so both are included.

## Diagnostic thresholds

- below `20%` — **normal**,
- `20%` to below `40%` — **busy**,
- `40%` or more — **congested**.

These thresholds help assess locally observed traffic. They are diagnostic values, not physical channel limits or DCD-derived boundaries.

## Measurement limits

APRSBox only sees frames that its radio and TNC decode correctly, plus locally logged RF transmissions. Collisions, interference, carrier without a valid AX.25 frame, and transmissions the TNC cannot decode can be invisible. Without DCD telemetry, this chart does not measure actual physical channel utilization.

Use the model to compare periods of traffic and identify a rise in observed APRS channel load.
