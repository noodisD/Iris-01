# IRIS architecture

What the code does now, then what it did on 18 September and what changed.

---

## Now

```mermaid
flowchart TB
    subgraph write["What the owner writes"]
        J["Reflection<br/><i>dated, or undated when the date is unknown</i>"]
        H["Habit completion"]
        C["Chat message<br/><i>recall only, never evidence</i>"]
        S["Staged import items<br/><i>undated transcripts</i>"]
    end

    subgraph ingest["Ingest — one transaction (ADR-0011)"]
        Q["Database._queue<br/><i>job written with the entry;<br/>generation bump on re-queue</i>"]
        W["work_queue worker<br/><i>notify() wakes it; missing source fails the job</i>"]
        P["pipeline.run_processing_pipeline"]
        E[("embeddings<br/>pgvector 1536")]
    end

    subgraph discover["Theme discovery"]
        PE["persistence.py<br/>clustering — finds themes, is not a finding"]
        CS["comparison.py<br/><b>ComparisonSpace</b>"]
        T[("themes · clustered | observed")]
        TO[("theme_occurrences<br/><i>dated-only reads by default</i>")]
    end

    subgraph read["Reading — on request only (ADR-0015, ADR-0016)"]
        OE["ObservationEngine.discover"]
        IL["interleave → chunk_entries"]
        VF["_verified<br/><i>verbatim, source-qualified</i>"]
        CO["consolidate<br/><b>Jaccard ≥ 0.5</b>"]
        SY["synthesise<br/><i>fail closed</i>"]
        SU["check_support<br/><i>supports / denies / mentions, fail closed</i>"]
        CN["constructs.promote<br/><i>null span when undated</i>"]
        TC[("themes · candidate")]
        OR[("observation_runs")]
    end

    subgraph engines["canonical_pipeline — six engines"]
        EN["trajectory · tension · resolution<br/>leverage (pairs) · decision_impact (live) · lifelong"]
    end

    subgraph policy["admit — one policy for both surfaces (ADR-0007)"]
        G0["drop_unsupported · coverage"]
        G1["enablement"]
        G2["confidence floor"]
        G3["conflict"]
        G4["rank<br/><i>orders, never cuts</i>"]
    end

    subgraph surfaces["Surfaces"]
        CHAT["Chat<br/><i>select: one per pattern, max_items</i>"]
        INS["Insights<br/><i>every admitted finding, as cards</i>"]
        LET["Weekly letter<br/><i>facts + admitted findings,<br/>firewall, quotes verified</i>"]
        REV["Constructs review"]
    end

    J --> Q
    H --> Q
    Q --> W --> P --> E
    C -.->|"recall, never an occurrence"| E
    E --> PE
    PE <--> CS
    PE --> T
    PE --> TO

    J --> OE
    S -.->|"read, never counted"| OE
    OE --> IL --> VF --> CO --> SY --> SU --> CN
    OE -.-> OR
    CN --> TC
    TC --> REV -->|"owner confirms"| CONF["constructs.confirm → scan"]
    CONF --> T
    CONF --> TO

    T --> EN
    TO --> EN
    EN --> G0 --> G1 --> G2 --> G3 --> G4
    G4 --> CHAT
    G4 --> INS
    G4 --> LET
```

The dashed edges are what is read but never counted: chat (ADR-0003) and undated
transcripts. The candidate store reaches the review surface and nothing else.

*Verified against `agent/pipeline_orchestrator.py` (`canonical_pipeline`, `admit`),
`agent/core.py`, `agent/insights_service.py`, `agent/observations.py`,
`agent/review_letter.py`, `agent/database.py::_queue`, migrations 0012–0014.*

---

## Invariants

1. **Nothing is measured before confirmation.** The candidate store is reachable only by
   the review surface; `get_themes` filters to `status='active'`.
2. **Reading happens only when asked.** No pipeline, queue or background job reaches
   `ObservationEngine`; a test asserts the pipeline, chat core, orchestrator and insights
   service cannot import it.

---

## Before — 18 September

The system as it was when `docs/constructs-review.md` was written. The rust border was the
defect: `consolidate` merged on a single shared citation. Chat and Insights also admitted
findings through different code; that is not drawn here.

```mermaid
flowchart TB
    subgraph write["What the owner writes"]
        J["Journal entry / reflection<br/><i>dated, evidence</i>"]
        H["Habit completion"]
        C["Chat message<br/><i>recall only, never evidence</i>"]
        S["Staged import items<br/><i>43 transcripts, undated</i>"]
    end

    subgraph ingest["Ingest — decoupled (ADR-0011)"]
        Q["work_queue.enqueue"]
        P["pipeline.run_processing_pipeline"]
        E[("embeddings<br/>pgvector 1536")]
    end

    subgraph discover["Theme discovery"]
        PE["persistence.py<br/>complete-linkage clustering"]
        CS["comparison.py<br/><b>ComparisonSpace</b><br/><i>mean-centred, shared voice removed</i>"]
        T[("themes<br/>origin='clustered' · 18 rows")]
        TO[("theme_occurrences · 70")]
    end

    subgraph read["Reading — on request only"]
        OE["observations.py<br/><b>ObservationEngine.read_archive</b>"]
        CH["chunk_entries<br/><i>20K token budget · 6 passes</i>"]
        VF["_verified<br/><i>verbatim citation check<br/>keyed on (source_type, id)</i>"]
        CO["consolidate<br/><b>single-linkage merge</b>"]
        CN["constructs.promote"]
        TC[("themes<br/>origin='observed'<br/>status='candidate' · 10 rows")]
        TP[("theme_prototypes · 110")]
    end

    subgraph engines["Six analytical engines"]
        EN["persistence · trajectory · tension<br/>resolution · leverage · decision_impact"]
    end

    subgraph policy["Admission policy — ADR-0007"]
        G0["coverage gate · order 0<br/><i>≥3 observed days</i>"]
        G1["enablement · order 1"]
        G2["confidence · order 2"]
        G3["conflict suppression"]
        G4["prioritisation"]
        G5["budget<br/><i>chat only, after ranking</i>"]
    end

    subgraph surfaces["Surfaces"]
        CHAT["Chat context"]
        INS["Insights screen"]
        REV["Constructs review<br/><i>confirm / reject</i>"]
    end

    J --> Q
    H --> Q
    C -.->|"embedded for recall,<br/>never an occurrence"| E
    Q --> P --> E
    E --> PE
    PE <--> CS
    PE --> T
    PE --> TO

    J --> OE
    S -.->|"read, never counted"| OE
    OE --> CH --> VF --> CO --> CN
    CN --> TC
    CN --> TP

    TC -->|"owner confirms"| CONF["constructs.confirm"]
    CONF --> SC["constructs.scan<br/><i>matches archive at 0.40</i>"]
    SC <--> CS
    SC --> TO
    CONF --> T

    T --> EN
    TO --> EN
    EN --> G0 --> G1 --> G2 --> G3 --> G4
    G4 --> G5 --> CHAT
    G4 --> INS
    TC --> REV
    REV --> CONF

    classDef broken stroke:#A8521F,stroke-width:3px
    classDef gated stroke:#0F7A84,stroke-width:2px
    class CO broken
    class TC,REV gated
```

**Reading the diagram.** `get_themes` returns only `status='active'`, so the candidate
store (`TC`) reaches the review surface and *nothing else* — no engine can see it until
the owner confirms. The dashed edges are the two things that are read but never counted:
chat messages (ADR-0003) and undated transcripts. The thick rust border marks the
defect: `consolidate` merges on a single shared citation.

### What changed

*Status as of 2026-09-19.*

| Change | Why (at the time) | Status |
|---|---|---|
| `consolidate` → complete-linkage or minimum overlap | Single-linkage chaining merged unrelated findings; 6 of 10 candidates ended less coherent than the 0.40 bar an entry must clear to join them. | Done — minimum overlap (Jaccard ≥ 0.5); complete linkage was tested and fails the bridge case |
| **New:** cohesion check before promotion | A candidate whose own prototypes fail its own admission test should never reach review. Catches the failure at the point it happens rather than after confirmation. | Not built — the measure it rested on compared the wrong statistics (see the erratum) |
| `chunk_entries` interleaves sources | Today passes 3–6 are recordings only, so a journal-and-voice pattern has one chance in six. | Done — `interleave`, dated by date with undated spread through |
| `promote` carries a null span when undated | Four candidates are stamped `2026-09-18`, implying transcripts were written the day they were discovered. | Done — `span_is_undated` (migration 0011) |
| **New:** `observation_runs` table | Nothing currently records how many raw observations preceded a merge, so the merge's behaviour can only be inferred from its output. | Done — runs, passes, raw pre-merge output (ADR-0016) |
| `origin` exposed on the insight payload | A confirmed construct is presently indistinguishable from a generated cluster on screen, which defeats the point of the owner vouching for it. | Done — on the payload and on the card |
