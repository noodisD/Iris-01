# ADR-0017: Sensor sources enter through one seam, as evidence

## Status
Proposed — 2026-09-22

## Context
The owner carries a Pixel 10a and (later this month) a Fitbit Air. Both are
sensor sources: location, app usage, steps; heart rate, sleep, SpO2. They
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
A new package `agent/sensors/` mirrors `agent/importing/`'s shape: an
adapter registry per source, a `SyncTransport` interface that decouples
how bytes leave the device from how bytes become evidence, a
`sensor_batches` table that stages parsed observations for owner review,
and a `sensor_observations` table that holds what the owner confirms.
Sensor observations are read by the existing engines through a new
`get_sensor_occurrences` helper that respects ADR-0013's date rules:
no date, no window.

The sync mechanism is a *seam*, not a decision. The first transport is
manual export (a file lands in `data/sensors/`); a local-network pull
and a cloud mirror can be added later behind the same interface without
changing anything downstream. Picking one is therefore deferred.

Sensor data is sensor-only. It enters as weighted occurrences that the
existing engines reason over; it does not form its own themes, does not
get its own engine, and does not feed a new admission policy. A future
ADR is required to introduce sensor-specific patterns, and that ADR
must say what stops a sensor-derived pattern from reading back as
though the owner had written it (the same burden ADR-0016 places on
the reading engine).

## Consequences
The engine surface does not grow. A phone reading has the same status
as a skipped habit — present in the data, weighted low, never driving a
pattern on its own. The deliberate boundary is in `EVIDENCE_WEIGHTS`
and in the test that watches it: every sensor source type appears
there, and nowhere in `get_unassigned_embeddings`'s skip-list.

`agent/sensors/` is the only code that writes `sensor_observations`.
`SensorService.create_sensor_observation` is the only seam, mirroring
`ReflectionService.create_reflection`. A future feature that wants
sensor data to count as a reflection — for example, "summarise today's
locations into a sentence and commit it as a journal entry" — must
reopen this ADR and say what stops a sensor-derived sentence from
reading back as though the owner had written it.

Sensor data does not become a theme on its own. The persistence engine
(`agent/persistence.py`) never sees a sensor observation, because
sensor observations have no semantic content to embed; they are
counted by the engines that measure in days and that is the end of
their analytical life.

## Risks
- A sensor batch with thousands of readings per day would dominate
  trajectory counts at any non-trivial weight. Mitigation: per-source
  daily caps in `EVIDENCE_WEIGHTS` are deliberate, and a `MAX_SENSOR_
  OCCURRENCES_PER_DAY_PER_THEME` constant bounds the count.
- Phone clocks drift. Mitigation: the adapter records `device_clock`
  and `host_clock` and the discrepancy is shown in the review screen.
- Battery drain on the phone. Mitigation: the manual export transport
  is pull-on-demand; any future always-on sync must record its power
  budget in the ADR that introduces it.
