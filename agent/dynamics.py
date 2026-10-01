"""Strict v4 personal-dynamics data contracts and conservative, provider-free gates.

A model supplies provisional semantic decisions. These functions never infer absence
from silence, equate an unknown pair with separate events, or turn a retelling into
another occurrence. Persist ``as_dict()`` and validate with ``from_dict()``.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .episodes import Episode, GROUNDED_FIELDS


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"not JSON data: {type(value).__name__}")

def canonical(value: object) -> str:
    """One canonical encoding for definition, claim, view and insight identities."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", by_alias=True)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=_json_default)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _predicate(text: str) -> str:
    return " ".join(text.split()).casefold()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True,
                              alias_generator=lambda name: re.sub(r"_([a-z])", lambda m: m[1].upper(), name))

    def as_dict(self) -> dict:
        return self.model_dump(by_alias=True, mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        if not isinstance(data, dict):
            raise ValueError("contract must be a JSON object")
        return cls.model_validate_json(canonical(data))


class Definition(Contract):
    context_predicate: str = Field(min_length=1)
    response_predicate: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    proposed_account_ids: list[str] = Field(default_factory=list)
    owner_report_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def nonblank(self) -> Self:
        if not _predicate(self.context_predicate) or not _predicate(self.response_predicate) or not self.title.strip():
            raise ValueError("empty dynamic definition")
        return self


class QuoteRef(Contract):
    model_config = ConfigDict(frozen=True)
    account_id: str
    field: Literal["situation", "response", "demand", "information", "feeling", "concern",
                   "immediate_outcome", "later_outcome", "explanation", "self_report"]
    citation_index: int = Field(ge=0)


class FieldCheck(Contract):
    field: Literal["situation", "response", "demand", "information", "feeling", "concern",
                   "immediate_outcome", "later_outcome", "explanation", "self_report"]
    verdict: Literal["supported", "contradicted", "not_stated", "unclear"]
    refs: list[QuoteRef]


class FieldChecks(Contract):
    account_id: str
    checks: list[FieldCheck]


def validate_field_checks(episode: Episode, result: FieldChecks) -> None:
    """A complete reply must judge every populated grounded field exactly once."""
    wanted = {field for field in GROUNDED_FIELDS if getattr(episode, field) is not None}
    found = [row.field for row in result.checks]
    if len(found) != len(set(found)) or set(found) != wanted:
        raise ValueError("incomplete or duplicate field checks")
    validate_refs((ref for row in result.checks for ref in row.refs), {result.account_id: episode})


class Membership(Contract):
    dynamic_id: str  # definition_key in drafts; owner-bound dynamic_id in published views
    account_id: str
    group_id: str | None = None
    role: Literal["support", "exception", "response_elsewhere", "unrelated", "unclear", "mixed"] = "unclear"
    context_decision: Literal["present", "absent", "unclear"]
    response_decision: Literal["present", "absent", "unclear"]
    relation_decision: Literal["linked", "contradicted", "unclear"]
    refs: list[QuoteRef] = Field(default_factory=list)
    owner_verdict: Literal["yes", "no", "unsure"] | None = None
    verdict_note: str | None = Field(default=None, max_length=1000)
    excluded: bool = False


class PairDecision(Contract):
    left_account_id: str
    right_account_id: str
    decision: Literal["same_event", "distinct_events", "unclear"]
    refs: list[QuoteRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_accounts(self) -> Self:
        if self.left_account_id == self.right_account_id:
            raise ValueError("pair cannot judge itself")
        if (self.decision != "unclear" and
                {self.left_account_id, self.right_account_id} -
                {ref.account_id for ref in self.refs}):
            raise ValueError("checked event pair needs passages from both accounts")
        return self


class EventGroup(Contract):
    id: str
    account_ids: list[str]
    role: Literal["support", "exception", "response_elsewhere", "unrelated", "unclear", "mixed"]
    independently_countable: bool = False
    independence_uncertain: bool = False

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.account_ids or len(set(self.account_ids)) != len(self.account_ids):
            raise ValueError("group must contain unique accounts")
        return self


class GroundedClause(Contract):
    text: str = Field(min_length=1, max_length=400)
    refs: list[QuoteRef] = Field(min_length=1)

    @model_validator(mode="after")
    def grounded(self) -> Self:
        if not self.text.strip() or len({(r.account_id, r.field, r.citation_index)
                                         for r in self.refs}) != len(self.refs):
            raise ValueError("grounded clause needs content and distinct source selectors")
        return self


class Hypothesis(Contract):
    text: str = Field(min_length=1, max_length=600)
    premises: list[GroundedClause] = Field(min_length=1)
    scope_group_ids: list[str]
    owner_report_ids: list[str]

    @model_validator(mode="after")
    def tentative(self) -> Self:
        if (not self.text.strip() or
                len(re.findall(r"[.!?](?=\s|$)", self.text)) > 2 or
                not (self.scope_group_ids or self.owner_report_ids) or
                len(set(self.scope_group_ids)) != len(self.scope_group_ids) or
                len(set(self.owner_report_ids)) != len(self.owner_report_ids)):
            raise ValueError("hypothesis needs content and a definite evidence scope")
        return self


class LensMatch(Contract):
    lens_id: str
    qualifying_group_ids: list[str]
    self_report_ids: list[str]
    requirement_refs: list[QuoteRef]
    excluded_group_ids: list[str]


class Feedback(Contract):
    verdict: Literal["rings_true", "does_not", "unsure"] | None
    note: str | None = Field(max_length=1000)
    updated_at: str
    needs_review: bool


class Example(Contract):
    account_id: str
    recorded_on: date | None
    citation: dict


class PersonalPattern(Contract):
    id: str
    title: str = Field(min_length=1, max_length=100)
    context: GroundedClause
    response: GroundedClause
    evidence_state: Literal["owner_described", "emerging", "recurring"]
    owner_meanings: list[GroundedClause]
    immediate_return: GroundedClause | None
    later_cost: GroundedClause | None
    possible_meaning: Hypothesis | None
    alternative: Hypothesis | None
    open_question: str
    lens_matches: list[LensMatch] = Field(max_length=2)
    exception_group_ids: list[str]
    response_elsewhere_group_ids: list[str]
    independent_group_count: int = Field(ge=0)
    account_count: int = Field(ge=0)
    entry_count: int = Field(ge=0)
    recorded_from: date | None
    recorded_to: date | None
    undated_account_count: int = Field(ge=0)
    exception_count: int = Field(ge=0)
    unknown_account_count: int = Field(ge=0)
    example: Example | None
    range: Literal["all", "30d", "90d"]
    as_of: date
    claim_hash: str
    snapshot: str
    feedback: Feedback | None


class PersonalInsight(Contract):
    id: str
    kind: Literal["function_and_tradeoff", "contextual_difference", "shared_concern"]
    dynamic_ids: list[str]
    title: str
    observation: GroundedClause
    possible_meaning: Hypothesis
    alternative: Hypothesis
    immediate_return: GroundedClause | None
    later_cost: GroundedClause | None
    supporting_groups: list[str]
    contrary_groups: list[str]
    unknown_account_ids: list[str]
    question: str
    range: Literal["all", "30d", "90d"]
    as_of: date
    claim_hash: str
    snapshot: str
    feedback: Feedback | None
    left_label: str | None = None
    right_label: str | None = None
    left_group_ids: list[str] | None = None
    right_group_ids: list[str] | None = None

    @model_validator(mode="after")
    def contrast_shape(self) -> Self:
        contrast = self.kind == "contextual_difference"
        values = (self.left_label, self.right_label, self.left_group_ids, self.right_group_ids)
        if ((contrast and (any(v is None for v in values) or
                           set(self.left_group_ids or ()) & set(self.right_group_ids or ())))
                or (not contrast and any(v is not None for v in values))):
            raise ValueError("invalid disjoint contextual difference sides")
        if len(self.dynamic_ids) != (2 if self.kind == "shared_concern" else 1):
            raise ValueError("invalid insight dynamic count")
        return self


class DiscoveryDraft(Contract):
    episodes: dict[str, dict]  # Episode.as_dict; validated on load, keyed by full fingerprint
    definitions: list[Definition]
    memberships: list[Membership]
    pair_decisions: list[PairDecision]
    groups: dict[str, list[EventGroup]]
    independent_group_ids: dict[str, list[str]]
    counts: dict[str, int]
    user_id: int | None = None
    projected: bool = False  # only a range projection may retain hidden identity constraints

    @model_validator(mode="after")
    def checked(self) -> Self:
        from .reference_evaluation import account_fingerprint
        for key, raw in self.episodes.items():
            Episode.from_dict(raw)
            if account_fingerprint(raw) != key:
                raise ValueError("draft account identity differs from source content")
        if len({definition_key(d) for d in self.definitions}) != len(self.definitions):
            raise ValueError("duplicate definitions")
        keys = {definition_key(d) for d in self.definitions}
        if set(self.groups) != keys or set(self.independent_group_ids) != keys:
            raise ValueError("incomplete draft group sets")
        normalized = validate_matrix(self.definitions, self.episodes, self.memberships)
        if any(given.role != checked.role for given, checked in zip(self.memberships, normalized)):
            raise ValueError("stored membership role differs from checked decisions")
        if self.projected:
            seen_pairs: set[frozenset[str]] = set()
            for pair in self.pair_decisions:
                pair_key = frozenset((pair.left_account_id, pair.right_account_id))
                if pair_key in seen_pairs:
                    raise ValueError("duplicate projected pair")
                seen_pairs.add(pair_key)
                validate_refs((ref for ref in pair.refs if ref.account_id in self.episodes),
                              self.episodes)
        else:
            _pair_index(self.pair_decisions, self.episodes)
        for key in keys:
            selected = set(self.independent_group_ids[key])
            ids = [g.id for g in self.groups[key]]
            if len(ids) != len(set(ids)) or set(selected) - set(ids) or len(selected) != len(set(selected)) or (
                    set(selected) != {g.id for g in self.groups[key] if g.independently_countable}):
                raise ValueError("draft independent set inconsistent with groups")
            assigned = [aid for g in self.groups[key] for aid in g.account_ids]
            if len(assigned) != len(set(assigned)) or set(assigned) - set(self.episodes):
                raise ValueError("draft groups contain duplicated or foreign accounts")
            qualifying = {m.account_id for m in self.memberships if m.dynamic_id == key and
                          m.role in {"support", "exception", "response_elsewhere"} and
                          (ep := Episode.from_dict(self.episodes[m.account_id])).actor == "self" and
                          ep.record_kind == "event"}
            if set(assigned) != qualifying:
                raise ValueError("incomplete event group partition")
            if not self.projected:
                expected_groups, expected_rows = partition_events(
                    key, self.memberships, self.pair_decisions, self.episodes)
                expected_groups, expected_ids = count_independent(
                    expected_groups, self.pair_decisions, self.episodes)
                if (self.groups[key] != expected_groups or
                        self.independent_group_ids[key] != expected_ids or
                        any(row.group_id != expected.group_id for row, expected in zip(
                            (row for row in self.memberships if row.dynamic_id == key),
                            expected_rows))):
                    raise ValueError("draft groups or independent counts disagree with checked pairs")
        return self


class DiscoveryView(Contract):
    range: Literal["all", "30d", "90d"]
    as_of: date
    patterns: list[PersonalPattern]
    insights: list[PersonalInsight]
    counts: dict[str, int]


def definition_key(definition: Definition) -> str:
    return canonical_hash({"contextPredicate": _predicate(definition.context_predicate),
                           "responsePredicate": _predicate(definition.response_predicate)})


def dynamic_id(user_id: int, definition: Definition) -> str:
    return "d_" + canonical_hash({"version": 1, "userId": user_id,
                                  "contextPredicate": _predicate(definition.context_predicate),
                                  "responsePredicate": _predicate(definition.response_predicate)})


def bind_dynamic_ids(draft: DiscoveryDraft, user_id: int) -> dict[str, str]:
    if user_id <= 0 or (draft.user_id is not None and draft.user_id != user_id):
        raise ValueError("invalid owner for draft")
    return {definition_key(d): dynamic_id(user_id, d) for d in draft.definitions}


def insight_id(user_id: int, kind: str, dynamic_ids: list[str], observation: GroundedClause,
               possible_meaning: Hypothesis, alternative: Hypothesis) -> str:
    return "i_" + canonical_hash({"version": 1, "userId": user_id, "kind": kind,
                                  "dynamicIds": sorted(dynamic_ids), "observation": observation.as_dict(),
                                  "possibleMeaning": possible_meaning.as_dict(),
                                  "alternative": alternative.as_dict()})


def claim_hash(value: object) -> str:
    """Hash substantive claims, not saved opinions, library annotations or snapshots.

    Callers must include the selected-range memberships, source revisions and
    independence decisions in ``value``; missing data cannot be manufactured here.
    """
    def strip(item):
        if isinstance(item, BaseModel):
            item = item.as_dict()
        if isinstance(item, dict):
            return {k: strip(v) for k, v in item.items() if k not in
                    {"feedback", "ownerVerdict", "verdictNote", "lensMatches", "lenses", "snapshot", "claimHash"}}
        if isinstance(item, (list, tuple)):
            return [strip(v) for v in item]
        return item
    return canonical_hash(strip(value))


def snapshot_hash(value: object) -> str:
    """Bind view versions, range/date, annotations and saved feedback, unlike claim_hash."""
    return canonical_hash(value)


def validate_refs(refs, accounts: dict[str, Episode | dict]) -> None:
    for ref in refs:
        episode = accounts.get(ref.account_id)
        if isinstance(episode, dict):
            episode = Episode.from_dict(episode)
        if episode is None or getattr(episode, ref.field) is None or ref.citation_index >= len(episode.citations):
            raise ValueError("quote reference points outside a grounded account")
        if getattr(episode, ref.field) not in episode.citations[ref.citation_index].text:
            raise ValueError("quote reference does not locate its passage")


def derive_role(context: str, response: str, relation: str) -> str:
    """Silence is unclear; only explicit linked contrary content defines a contrast."""
    if relation == "linked":
        if context == "present" and response == "present":
            return "support"
        if context == "present" and response == "absent":
            return "exception"
        if context == "absent" and response == "present":
            return "response_elsewhere"
    if relation == "contradicted" and context == "absent" and response == "absent":
        return "unrelated"
    return "unclear"


def validate_matrix(definitions: list[Definition], accounts: dict[str, Episode | dict],
                    rows: list[Membership]) -> list[Membership]:
    """Require exactly one checked decision for every definition/account pair."""
    keys = [definition_key(d) for d in definitions]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate definition")
    expected = {(key, account_id) for key in keys for account_id in accounts}
    seen = [(m.dynamic_id, m.account_id) for m in rows]
    if len(seen) != len(set(seen)) or set(seen) != expected:
        raise ValueError("incomplete, foreign or duplicate membership decision")
    result = []
    for row in rows:
        validate_refs(row.refs, accounts)
        role = derive_role(row.context_decision, row.response_decision, row.relation_decision)
        if role in {"support", "exception", "response_elsewhere", "unrelated"} and not any(
                ref.account_id == row.account_id for ref in row.refs):
            raise ValueError("checked relation has no account passage selector")
        episode = accounts[row.account_id]
        if isinstance(episode, dict):
            episode = Episode.from_dict(episode)
        if episode.actor != "self" or episode.record_kind not in {"event", "self_report"}:
            role = "unclear"  # excluded classifications cannot become owner evidence
        result.append(row.model_copy(update={"role": role}))
    return result


def _pair_index(pairs: list[PairDecision], accounts: dict[str, Episode | dict]) -> dict[frozenset[str], str]:
    index = {}
    for pair in pairs:
        key = frozenset((pair.left_account_id, pair.right_account_id))
        if (key in index or pair.left_account_id not in accounts or pair.right_account_id not in accounts):
            raise ValueError("duplicate or foreign event pair")
        if pair.decision != "unclear":
            for aid in (pair.left_account_id, pair.right_account_id):
                ep = Episode.from_dict(accounts[aid]) if isinstance(accounts[aid], dict) else accounts[aid]
                if ep.actor != "self" or ep.record_kind != "event":
                    raise ValueError("event identity cannot join reports, plans or another actor")
        validate_refs(pair.refs, accounts)
        index[key] = pair.decision
    return index


def _entry_id(account: Episode | dict) -> int:
    if isinstance(account, dict):
        account = Episode.from_dict(account)
    return min(c.entry_id for c in account.citations)


def _group_role(roles: set[str]) -> str:
    meaningful = roles & {"support", "exception", "response_elsewhere"}
    if len(meaningful) > 1:
        return "mixed"
    if meaningful:
        return next(iter(meaningful))
    if "unclear" in roles:
        return "unclear"
    return "unrelated"


def partition_events(dynamic_id: str, memberships: list[Membership], pairs: list[PairDecision],
                     accounts: dict[str, Episode | dict]) -> tuple[list[EventGroup], list[Membership]]:
    """Group checked same-event links; poison contradictory same/same/distinct triangles.

    A poisoned component remains separate singleton groups with uncertainty;
    count_independent also disallows two members of the original component.
    """
    rows = [m for m in memberships if m.dynamic_id == dynamic_id]
    candidates = {m.account_id for m in rows if m.role in {"support", "exception", "response_elsewhere"}
                  and not m.excluded and (lambda e: e.actor == "self" and e.record_kind == "event")(
                      Episode.from_dict(accounts[m.account_id]) if isinstance(accounts[m.account_id], dict)
                      else accounts[m.account_id])}
    index = _pair_index(pairs, accounts)
    parent = {a: a for a in candidates}

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for pair in pairs:
        if pair.decision == "same_event" and pair.left_account_id in candidates and pair.right_account_id in candidates:
            parent[root(pair.left_account_id)] = root(pair.right_account_id)
    components: dict[str, set[str]] = {}
    for account_id in candidates:
        components.setdefault(root(account_id), set()).add(account_id)
    groups = []
    for members in components.values():
        poisoned = any(index.get(frozenset((a, b))) == "distinct_events"
                       for a in members for b in members if a < b)
        parts = [{a} for a in members] if poisoned else [members]
        for part in parts:
            account_ids = sorted(part)
            roles = {m.role for m in rows if m.account_id in part}
            groups.append(EventGroup(id=account_ids[0], account_ids=account_ids,
                                     role=_group_role(roles), independence_uncertain=poisoned))
    groups.sort(key=lambda g: (_entry_id(accounts[g.id]), g.id))
    by_account = {account_id: g.id for g in groups for account_id in g.account_ids}
    return groups, [m.model_copy(update={"group_id": by_account.get(m.account_id)}) for m in rows]


def count_independent(groups: list[EventGroup], pairs: list[PairDecision],
                      accounts: dict[str, Episode | dict]) -> tuple[list[EventGroup], list[str]]:
    """Greedy lower bound; every pair across admitted groups must be checked distinct.

    A same-event chain remains a constraint even if contradictory links prevented
    grouping it, so no two poisoned members are counted independently.
    """
    index = _pair_index(pairs, accounts)
    parent = {a: a for g in groups for a in g.account_ids}

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for pair in pairs:
        a, b = pair.left_account_id, pair.right_account_id
        if pair.decision == "same_event" and a in parent and b in parent:
            parent[root(a)] = root(b)
    selected: list[EventGroup] = []
    for group in sorted(groups, key=lambda g: (min(_entry_id(accounts[a]) for a in g.account_ids), g.id)):
        if group.role not in {"support", "exception", "response_elsewhere"}:
            continue
        if all(all(root(a) != root(b) and index.get(frozenset((a, b))) == "distinct_events"
                   for a in group.account_ids for b in prior.account_ids) for prior in selected):
            selected.append(group)
    ids = {g.id for g in selected}
    return [g.model_copy(update={"independently_countable": g.id in ids}) for g in groups], [g.id for g in selected]


def mutually_independent(groups: list[EventGroup], pairs: list[PairDecision],
                         accounts: dict[str, Episode | dict]) -> bool:
    """Insight gate: every included event must be distinct from every other.

    Different group IDs (even across two dynamics) do not establish distinct
    occasions. The caller supplies full-archive accounts so a hidden retelling
    bridge still rules out a false cross-range or cross-dynamic contrast.
    """
    if not groups or any(not g.independently_countable or g.role in {"mixed", "unclear"}
                         for g in groups):
        return False
    if len({g.id for g in groups}) != len(groups):
        return False
    members = [aid for group in groups for aid in group.account_ids]
    if len(set(members)) != len(members):
        return False
    index = _pair_index(pairs, accounts)
    parent = {aid: aid for aid in accounts}

    def root(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for pair in pairs:
        if pair.decision == "same_event":
            parent[root(pair.left_account_id)] = root(pair.right_account_id)
    return all(root(a) != root(b) and index.get(frozenset((a, b))) == "distinct_events"
               for index_a, left in enumerate(groups) for right in groups[index_a + 1:]
               for a in left.account_ids for b in right.account_ids)


def evidence_state(groups: list[EventGroup], owner_report_ids: list[str],
                   accounts: dict[str, Episode | dict]) -> str | None:
    """Report only owner-described or independently witnessed relationships."""
    supported = [g for g in groups if g.role == "support" and g.independently_countable]
    entries = {_entry_id(accounts[a]) for g in supported for a in g.account_ids}
    if len(supported) >= 3 and len(entries) >= 3:
        return "recurring"
    if len(supported) >= 2 and len(entries) >= 2:
        return "emerging"
    reports = [aid for aid in owner_report_ids if aid in accounts and
               (lambda ep: ep.actor == "self" and ep.record_kind == "self_report")(
                   Episode.from_dict(accounts[aid]) if isinstance(accounts[aid], dict) else accounts[aid])]
    return "owner_described" if reports else None


def project_range(draft: DiscoveryDraft, period: Literal["all", "30d", "90d"], as_of: date,
                  corrections: dict[tuple[str, str], str | None] | None = None,
                  correction_notes: dict[tuple[str, str], str | None] | None = None) -> DiscoveryDraft:
    """Project accounts without recomputing identity, independence, or group IDs.

    Hidden retelling bridges remain in pair_decisions and original independent
    groups; they never become displayed evidence or a newly independent event.
    """
    if period not in {"all", "30d", "90d"}:
        raise ValueError("unknown range")
    lower = None if period == "all" else as_of - timedelta(days=29 if period == "30d" else 89)
    chosen = {aid: raw for aid, raw in draft.episodes.items()
              if (period == "all" or
                  ((day := Episode.from_dict(raw).recorded_on) is not None and lower <= day <= as_of))}
    corrections = corrections or {}
    correction_notes = correction_notes or {}
    valid_rows = {(key, aid) for key in draft.groups for aid in draft.episodes}
    if set(corrections) - valid_rows or set(correction_notes) - valid_rows:
        raise ValueError("correction refers to an unknown account or definition")
    if any(verdict not in {None, "yes", "no", "unsure"} for verdict in corrections.values()):
        raise ValueError("invalid correction")
    rows = []
    for m in draft.memberships:
        if m.account_id not in chosen:
            continue
        verdict = corrections.get((m.dynamic_id, m.account_id), m.owner_verdict)
        note = correction_notes.get((m.dynamic_id, m.account_id), m.verdict_note)
        rows.append(m.model_copy(update={"owner_verdict": verdict, "verdict_note": note,
                                         "excluded": verdict == "no"}))
    by_key = {(m.dynamic_id, m.account_id): m for m in rows}
    projected = {}
    selected = {}
    for key, source_groups in draft.groups.items():
        projected[key] = []
        selected[key] = []
        for group in source_groups:
            included = [aid for aid in group.account_ids if aid in chosen]
            if not included:
                continue
            roles = {by_key[(key, aid)].role for aid in included if not by_key[(key, aid)].excluded}
            role = _group_role(roles) if roles else "unclear"
            countable = group.id in draft.independent_group_ids[key] and role in {
                "support", "exception", "response_elsewhere"}
            projected[key].append(group.model_copy(update={"account_ids": included, "role": role,
                                                     "independently_countable": countable}))
            if countable:
                selected[key].append(group.id)
    return DiscoveryDraft(episodes=chosen, definitions=draft.definitions, memberships=rows,
                          pair_decisions=draft.pair_decisions, groups=projected,
                          independent_group_ids=selected, counts=draft.counts, user_id=draft.user_id,
                          projected=True)
