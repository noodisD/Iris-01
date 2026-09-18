-- 0009_claim_kind.sql
--
-- What a construct's occurrences actually mean.
--
-- An independent review found that the pipeline treated several different
-- propositions as one: the words exist, the words support the claim, the entry
-- records an occurrence, the owner validated the detector. Only the first was
-- ever verified. Its sharpest demonstration: two authentic quotations
-- explicitly *denying* a behaviour were accepted as proving it, because
-- verification checks that a quote appears in an entry and nothing more.
--
-- So a construct now has to say which kind of claim it makes.
--
--   'mention'   — this subject appears in the writing. A verified quote proves
--                 exactly this, and nothing stronger. Reachable today.
--   'behaviour' — this happened. Needs actor, event identity, negation,
--                 intent-versus-action and retrospective reference before any
--                 construct may claim it. Nothing is born here, and confirmation
--                 refuses it until that contract exists.
--
-- The two never share an occurrence count or a confidence label. A mention
-- counter that silently reads as a behaviour counter is the failure this column
-- exists to prevent.
--
-- `admission_basis` records why a row became an occurrence: a citation the owner
-- read, or a similarity match they never saw. The review's point is that
-- confirming a claim and authorising a detector are different acts, and the
-- evidence should say which one produced each row.

ALTER TABLE themes ADD COLUMN IF NOT EXISTS claim_kind VARCHAR(16) NOT NULL DEFAULT 'mention';

ALTER TABLE theme_occurrences ADD COLUMN IF NOT EXISTS admission_basis VARCHAR(16);

-- Existing rows predate the distinction. Clustered themes never made a claim at
-- all — they are groups of entries with a generated label — so 'mention' is the
-- honest reading of what their counts have always meant.
UPDATE themes SET claim_kind = 'mention' WHERE claim_kind IS NULL;

-- Occurrences written before this column existed came from clustering, which
-- matches rather than cites.
UPDATE theme_occurrences SET admission_basis = 'similarity' WHERE admission_basis IS NULL;

CREATE INDEX IF NOT EXISTS idx_themes_user_kind ON themes(user_id, claim_kind);
