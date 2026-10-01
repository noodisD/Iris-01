"""Owner-only v4 diagnostic/reference workflow with synthetic passages."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent.episodes import Episode
from agent.field_support import check
from agent.reference_evaluation import account_fingerprint, score_results
from agent.reading_version import VERIFIED_READER_VERSION
from scripts import read_episodes, reference_labels, spot_check, verify_fields


def episode(number: int = 1) -> dict:
    text = f"For race {number}, I saw the deadline. I planned to practise."
    return {"actor": "self", "recordKind": "intention", "situation": f"For race {number}, I saw the deadline",
            "response": "I planned to practise", "demand": None, "information": None,
            "feeling": None, "concern": None, "immediateOutcome": None, "laterOutcome": None,
            "explanation": None, "selfReport": None, "domain": None,
            "recordedOn": "2026-01-02", "citations": [
                {"sourceType": "reflection", "entryId": str(number), "entryDate": "2026-01-02",
                 "text": text}]}


def cache(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({"version": 4, "readerVersion": VERIFIED_READER_VERSION,
                                "user": 1, "includesStaged": False,
                                "entriesRead": len({e["citations"][0]["entryId"] for e in rows}),
                                "sourceRevisions": {str(e["citations"][0]["entryId"]): 1 for e in rows},
                                "episodes": rows}))


def reference(rows: list[dict]) -> dict:
    keys = [account_fingerprint(row) for row in rows]
    return {"version": 3, "cohort": keys, "accounts": {
        key: {"index": index, "fingerprint": key,
              "verdicts": {"situation": "supported", "response": "wrong_modality"}}
        for index, key in enumerate(keys)}}


def result(row: dict, verdicts: dict) -> dict:
    key = account_fingerprint(row)
    return {"key": key, "fingerprint": key, "verdicts": verdicts}


def filled_sheet(rows: list[dict]) -> str:
    return (reference_labels.sheet(rows, tuple(range(len(rows))))
            .replace("`situation:` ", "`situation:` supported")
            .replace("`response:` ", "`response:` wrong_modality"))


def test_fingerprint_tracks_original_content_but_not_citation_order():
    original = episode()
    changed = deepcopy(original)
    changed["citations"][0]["text"] += " An explicit later result."
    assert account_fingerprint(changed) != account_fingerprint(original)
    changed = deepcopy(original)
    changed["response"] = "planned to practise"
    assert account_fingerprint(changed) != account_fingerprint(original)
    changed = deepcopy(original)
    changed["citations"].append({"sourceType": "reflection", "entryId": 2,
                                 "entryDate": "2026-01-02", "text": original["citations"][0]["text"]})
    reordered = deepcopy(changed)
    reordered["citations"].reverse()
    assert account_fingerprint(reordered) == account_fingerprint(changed)
    assert account_fingerprint(reordered) != account_fingerprint(original)


def test_denominators_include_unavailable_missing_and_unsure():
    rows = [episode(1), episode(2), episode(3)]
    ref = reference(rows)["accounts"]
    ref[account_fingerprint(rows[2])]["verdicts"]["response"] = "unsure"
    scored = score_results(ref, [
        result(rows[0], {"situation": "supported", "response": "contradicted"}),
        result(rows[1], {"situation": "unavailable", "response": "unclear"}),
    ])
    known = scored["overall"]["known_error"]
    correct = scored["overall"]["correct"]
    assert (known["total"], known["rejected"], known["unclear"]) == (2, 1, 1)
    assert (correct["total"], correct["unavailable"]) == (3, 2)
    assert scored["overall"]["unsure"]["unavailable"] == 1
    assert scored["baselines"]["constant_reject"]["correct"]["rejected"] == 3
    assert scored["baselines"]["constant_supported"]["known_error"]["rejected"] == 0


@pytest.mark.parametrize("failure", ("stale", "duplicate", "invalid", "reference_key"))
def test_scoring_rejects_ambiguous_or_unbound_results(failure):
    e = episode()
    ref = reference([e])["accounts"]
    rows = [result(e, {"situation": "supported", "response": "contradicted"})]
    if failure == "stale":
        rows[0]["fingerprint"] = "f" * 64
    elif failure == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif failure == "invalid":
        rows[0]["verdicts"]["situation"] = "probably"
    else:
        ref["a" * 64] = ref.pop(account_fingerprint(e))
    with pytest.raises(ValueError):
        score_results(ref, rows)


def test_new_judgments_follow_content_identity_not_cache_index():
    rows = [episode(1), episode(2)]
    labels = reference_labels.read(filled_sheet(rows))
    assert labels == reference(rows)
    assert reference_labels.validate_reference(labels, list(reversed(rows))) == [0, 1]
    changed = deepcopy(rows)
    changed[0]["citations"][0]["text"] += " An explicit revision."
    with pytest.raises(ValueError, match="fingerprint"):
        reference_labels.validate_reference(labels, changed)


@pytest.mark.parametrize("kind", ("missing_verdict", "all_unsure", "wrong_content", "missing_account",
                                 "duplicate_account", "legacy"))
def test_reference_preflight_rejects_incomplete_or_old_judgments(kind):
    rows = [episode(1), episode(2)]
    labels = reference(rows)
    key = account_fingerprint(rows[0])
    if kind == "missing_verdict":
        del labels["accounts"][key]["verdicts"]["response"]
    elif kind == "all_unsure":
        for item in labels["accounts"].values():
            item["verdicts"] = dict.fromkeys(item["verdicts"], "unsure")
    elif kind == "wrong_content":
        labels["accounts"][key]["fingerprint"] = "b" * 64
    elif kind == "missing_account":
        rows.pop()
    elif kind == "duplicate_account":
        rows.append(deepcopy(rows[0]))
    else:
        labels["version"] = 2
    with pytest.raises(ValueError):
        reference_labels.validate_reference(labels, rows)


@pytest.mark.parametrize("fault", ("blank", "duplicate_field", "duplicate_account",
                                   "wrong_verdict", "extra_field", "old_format", "wrong_heading"))
def test_sheet_parser_refuses_missing_or_injected_judgments(fault):
    text = filled_sheet([episode()])
    if fault == "blank":
        text = text.replace("`response:` wrong_modality", "`response:` ")
    elif fault == "duplicate_field":
        text += "\n`response:` supported\n"
    elif fault == "duplicate_account":
        text += "\n## " + text.split("\n## ", 1)[1]
    elif fault == "wrong_verdict":
        text = text.replace("`response:` wrong_modality", "`response:` maybe")
    elif fault == "extra_field":
        text = text.replace("`response:` wrong_modality", "`outcome:` supported")
    elif fault == "old_format":
        text = text.replace("reference-format: 3", "reference-format: 2")
    else:
        text = text.replace("## account", "## invented")
    if fault == "blank":
        with pytest.raises(ValueError):
            reference_labels.validate_reference(reference_labels.read(text), [episode()])
    else:
        with pytest.raises(ValueError):
            reference_labels.read(text)


def test_cited_source_text_cannot_insert_a_judgment_or_account():
    row = episode()
    injection = "\n## account #5 · fingerprint `" + "0" * 64 + "`\n`response:` contradicted"
    row["citations"][0]["text"] += injection
    labels = reference_labels.read(filled_sheet([row]))
    assert reference_labels.validate_reference(labels, [row]) == [0]
    assert len(labels["accounts"]) == 1


@pytest.fixture
def files(tmp_path):
    rows = [episode(1), episode(2)]
    cache_path, ref = tmp_path / "episodes-v4.json", tmp_path / "reference-v4.json"
    cache(cache_path, rows)
    ref.write_text(json.dumps(reference(rows)))
    return rows, cache_path, ref


def test_manual_review_workflow_is_new_owner_only_and_non_overwriting(files, tmp_path):
    rows, cache_path, ref = files
    sheet_path, out = tmp_path / "sheet.md", tmp_path / "labels.json"
    args = ["--cache", str(cache_path), "--sheet", str(sheet_path), "--out", str(out)]
    assert reference_labels.main(["build", "--count", "2", *args]) == 0
    assert not out.exists()
    assert sheet_path.stat().st_mode & 0o777 == 0o600
    assert reference_labels.main(["read", *args]) == 1
    sheet_path.write_text(filled_sheet(rows))
    assert reference_labels.main(["read", *args]) == 0
    assert json.loads(out.read_text()) == json.loads(ref.read_text())
    assert out.stat().st_mode & 0o777 == 0o600
    assert reference_labels.main(["read", *args]) == 1
    assert reference_labels.main(["build", *args]) == 1


@pytest.mark.parametrize("fault", ("missing", "legacy", "partial", "stale", "all_unsure"))
def test_reviewed_preflight_stops_before_provider(files, monkeypatch, fault):
    rows, cache_path, ref = files
    labels = reference(rows)
    if fault == "missing":
        ref.unlink()
    else:
        if fault == "legacy":
            labels["version"] = 2
        elif fault == "partial":
            del labels["accounts"][account_fingerprint(rows[0])]["verdicts"]["response"]
        elif fault == "stale":
            labels["accounts"][account_fingerprint(rows[0])]["fingerprint"] = "0" * 64
        else:
            for value in labels["accounts"].values():
                value["verdicts"] = dict.fromkeys(value["verdicts"], "unsure")
        ref.write_text(json.dumps(labels))
    monkeypatch.setattr(verify_fields, "_run_checks", lambda *args: pytest.fail("provider reached"))
    assert verify_fields.main(["--cache", str(cache_path), "--reference", str(ref), "--reviewed"]) == 1
    assert not cache_path.with_name("field-support-v4-reviewed.json").exists()


def test_reviewed_dry_run_and_input_collision_cannot_call_provider(files, monkeypatch):
    _, cache_path, ref = files
    monkeypatch.setattr(verify_fields, "_run_checks", lambda *args: pytest.fail("provider reached"))
    args = ["--cache", str(cache_path), "--reference", str(ref), "--reviewed"]
    assert verify_fields.main([*args, "--dry-run"]) == 0
    before = cache_path.read_bytes()
    assert verify_fields.main([*args, "--out", str(cache_path)]) == 1
    assert cache_path.read_bytes() == before
    before = ref.read_bytes()
    assert verify_fields.main([*args, "--out", str(ref)]) == 1
    assert ref.read_bytes() == before


def test_reviewed_output_uses_production_verdicts_and_predeclared_cohort(files, monkeypatch, capsys):
    rows, cache_path, ref = files
    def synthetic_checked(accounts, wanted):
        assert all(isinstance(row, Episode) for row in accounts)
        assert wanted == [0, 1]
        return ([result(accounts[i].as_dict(), {"situation": "supported", "response": "unavailable"})
                 for i in wanted], {"version": 4, "model": "synthetic", "promptHash": "test"})
    monkeypatch.setattr(verify_fields, "_run_checks", synthetic_checked)
    assert verify_fields.main(["--cache", str(cache_path), "--reference", str(ref),
                               "--reviewed"]) == 0
    artifact = json.loads(cache_path.with_name("field-support-v4-reviewed.json").read_text())
    assert artifact["score"]["overall"]["known_error"]["total"] == 2
    assert artifact["score"]["overall"]["known_error"]["unavailable"] == 2
    assert artifact["model"] == "synthetic"
    assert "errors caught           0 of 2" in capsys.readouterr().out


def test_cache_rejects_legacy_staged_and_changed_owner(files):
    _, cache_path, _ = files
    assert len(read_episodes.load_cache(cache_path, 1)[0]) == 2
    with pytest.raises(ValueError):
        read_episodes.load_cache(cache_path, 2)
    body = json.loads(cache_path.read_text())
    body["includesStaged"] = True
    cache_path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        read_episodes.load_cache(cache_path, 1)
    body["version"] = 3
    cache_path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        read_episodes.load_cache(cache_path, 1)


def test_spot_check_prioritizes_risky_kinds_without_inferred_outcomes():
    first = episode(1)
    first["recordKind"] = "event"
    second = episode(2)
    second["actor"] = "other"
    third = episode(3)
    third["recordKind"] = "hypothetical"
    chosen = spot_check.choose([first, second, third], 2)
    assert {index for index, _ in chosen} == {1, 2}
    text = spot_check.sheet([first, second, third], chosen)
    assert "not event time" in text
    assert "Not recorded" in text
    assert second["citations"][0]["text"] in text


def test_evaluation_adapter_keeps_semantic_failure_unavailable_without_payload(caplog):
    account = Episode.from_dict(episode())
    class FailedModel:
        def chat(self, **_):
            raise RuntimeError("synthetic-private-words")
    assert check(account, FailedModel()) == {
        "situation": "unavailable", "response": "unavailable"}
    assert "synthetic-private-words" not in caplog.text
