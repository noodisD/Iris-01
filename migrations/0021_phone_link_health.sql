-- When the paired phone last reached IRIS; cleared whenever the pairing changes.
ALTER TABLE mobile_pairing
    ADD COLUMN last_seen_at TIMESTAMPTZ,
    ADD COLUMN last_intake_at TIMESTAMPTZ;
