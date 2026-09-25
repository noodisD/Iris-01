# ADR-0017: Sensor sources enter through one seam, as evidence

## Status
Accepted — 2026-09-22

## Implementation
`agent/sensors/` parses the Android collector's Pixel and Health Connect JSON
into staged `sensor_batches`. Health Connect supplies permitted records from
any writer, including the Fitbit app when it becomes available. The opt-in
foreground service sends measurements through the bearer-gated, pinned-HTTPS
mobile intake. No export-file upload or unused pull-transport abstraction
remains. Byte-identical retry batches keep one review identity.

`SensorService.commit_batch` validates selected links to existing active
themes, stores the readings, and admits dated evidence in one transaction.
The newest approved measurement per theme, source and UTC day occupies the
daily cap; deleting it restores an older approved measurement. Unlinked
readings remain inert. Existing engines read the factual snippets and low
weights via `theme_occurrences`; sensors do not create themes.

## Context
The owner carries a Pixel 10a and may add a Fitbit later. Pixel location, app
usage and steps, plus heart rate, sleep and SpO2 written into Health Connect,
are sensor sources independent of the app that wrote the health record. They
are not reflections (ADR-0010) and they are not chat (ADR-0003), and
treating them as either would let a reading silently become a sentence in
the journal, or let a model write a pattern that the sensor data appears
to support because nothing watched the line.

The architecture already has the right shape: `agent/importing/` parses
external data, stages it for review, and commits through a single seam;
ADR-0013 says imported entries are reflections, dated when they happened,
staged before commit. Sensor data needs the same shape, with one
deliberate difference — a sensor reading is *measured*, not *written*,
so it cannot land in `reflections` without breaking ADR-0010's invariant
that a reflection is something the owner wrote.

## Decision
An adapter registry parses each supported source type; `sensor_batches`
hold staged review and `sensor_observations` hold confirmed measurements.
A batch remains inert until the owner sees its readings and optionally links
each source type to an existing active theme. A confirmed batch keeps
unlinked readings as raw data, not evidence. Linked readings materialize in
`theme_occurrences`; undated ones stay out of windowed engines per ADR-0013.
Arrival is the paired Android app's bounded HTTPS intake, separate from
the owner-controlled admission step.

Sensor data is sensor-only. It enters as weighted occurrences that the
existing engines reason over; it does not form its own themes, does not
get its own engine, and does not feed a new admission policy. A future
ADR is required to introduce sensor-specific patterns, and that ADR
must say what stops a sensor-derived pattern from reading back as
though the owner had written it (the same burden ADR-0016 places on
the reading engine).

## Consequences
The engine surface does not grow. Linked sensor readings are weighted at
0.3–0.6 in `EVIDENCE_WEIGHTS`; skipped habits, by contrast, are not evidence.
The per-source, per-theme UTC-day cap keeps the newest approved measurement
as an occurrence; earlier measurements remain raw and can be restored when
a newer batch is deleted. Sensors produce no embeddings and cannot create
themes; persistence clustering never sees their readings.

`agent/sensors/` owns sensor observations and their materialized occurrences.
Deleting a confirmed batch retracts its occurrences, updates theme counts,
and invalidates derived analyses. A feature that wants sensor data to count
as a reflection — for example, turning locations into a journal entry —
must reopen this ADR and preserve ADR-0010's written-versus-measured boundary.

## Risks
- A sensor batch with thousands of readings per day could dominate analysis.
  Mitigation: `MAX_SENSOR_OCCURRENCES_PER_DAY_PER_THEME` caps admitted
  occurrences per source and UTC day; the rest remain raw readings.
- Phone clocks drift. Mitigation: record device and host clocks and show
  the discrepancy before confirmation. Date-only step readings remain
  calendar days, not browser-local instants.
- Battery drain on the phone. Collection requires an explicit start and a
  foreground service; delivery runs about every 15 minutes and pauses when
  collection is stopped.
