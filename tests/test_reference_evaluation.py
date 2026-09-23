"""Synthetic-only evaluation tests: no application, database, or model imports.

Run independently of the database suite:
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest --noconftest \
    -p no:cacheprovider tests/test_reference_evaluation.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

import agent
from agent.reference_evaluation import account_fingerprint, account_key, score_results
from scripts import reference_labels, verify_fields


def episode(number: int = 1) -> dict:
    return {
        "situation": f"Invented account {number}: a race was approaching.",
        "response": "I planned to practise.",
        "outcome": "The practice happened.",
        "actor": "self",
        "modality": "planned",
        "occurred_on": None,
        "citations": [{"sourceType": "reflection", "entryId": number,
                       "entryDate": "2026-01-02", "text": "I planned to practise."}],
    }


def reference(episodes: list[dict]) -> dict:
    return {"version": 2, "cohort": [account_key(e) for e in episodes], "accounts": {
        account_key(e): {"index": i, "fingerprint": account_fingerprint(e),
                         "verdicts": {"response": "supported", "outcome": "not_stated"}}
        for i, e in enumerate(episodes)}}


def result(e: dict, verdicts: dict) -> dict:
    return {"key": account_key(e), "fingerprint": account_fingerprint(e), "verdicts": verdicts}


def filled_sheet(episodes: list[dict]) -> str:
    return (reference_labels.sheet(episodes, tuple(range(len(episodes))))
            .replace("`response:` ", "`response:` supported")
            .replace("`outcome:` ", "`outcome:` not_stated"))


@pytest.mark.parametrize("field", ["outcome", "actor", "modality", "occurred_on"])
def test_fingerprint_binds_fields_the_legacy_key_does_not(field):
    original = episode()
    changed = deepcopy(original)
    changed[field] = "changed"
    assert account_key(original) == account_key(changed)
    assert account_fingerprint(original) != account_fingerprint(changed)


@pytest.mark.parametrize("field", ["text", "entryDate", "entryId", "sourceType"])
def test_fingerprint_binds_every_citation_field(field):
    original = episode()
    changed = deepcopy(original)
    changed["citations"][0][field] = "changed"
    assert account_fingerprint(original) != account_fingerprint(changed)


def test_fingerprint_ignores_order_but_not_duplicate_evidence():
    original = episode()
    original["citations"].append(episode(2)["citations"][0])
    reordered = dict(reversed(list(original.items())))
    reordered["citations"] = list(reversed(original["citations"]))
    assert account_fingerprint(original) == account_fingerprint(reordered)
    reordered["citations"].append(original["citations"][0])
    assert account_fingerprint(original) != account_fingerprint(reordered)


def test_failed_calls_and_missing_results_stay_in_denominators():
    episodes = [episode(1), episode(2), episode(3)]
    score = score_results(reference(episodes)["accounts"], [
        result(episodes[0], {"response": "supported", "outcome": "contradicted"}),
        result(episodes[1], {"response": "unavailable", "outcome": "unavailable"}),
        # Third account has no result at all, not a smaller reference set.
    ])
    errors, correct = score["overall"]["known_error"], score["overall"]["correct"]
    assert (errors["rejected"], errors["total"], errors["unavailable"]) == (1, 3, 2)
    assert (correct["rejected"], correct["total"], correct["unavailable"]) == (0, 3, 2)
    assert score["by_field"]["outcome"]["known_error"]["total"] == 3
    always_yes = score["baselines"]["constant_supported"]
    always_no = score["baselines"]["constant_reject"]
    assert (always_yes["known_error"]["rejected"], always_yes["correct"]["rejected"]) == (0, 0)
    assert (always_no["known_error"]["rejected"], always_no["correct"]["rejected"]) == (3, 3)


def test_reference_unsure_and_unjudged_outputs_are_separate():
    e = episode()
    ref = reference([e])["accounts"]
    ref[account_key(e)]["verdicts"]["outcome"] = "unsure"
    scored = score_results(ref, [result(e, {"response": "supported"}),
                                 result(episode(2), {"response": "supported"})])
    assert scored["overall"]["known_error"]["total"] == 0
    assert scored["overall"]["unsure"]["total"] == 1
    assert scored["overall"]["unsure"]["unavailable"] == 1
    assert scored["missing_reference"] == {"accounts": 1, "fields": 1}


@pytest.mark.parametrize("verdict", ["wrong_actor", "wrong_modality", "contradicted", "not_stated"])
def test_each_error_kind_counts_as_a_known_error(verdict):
    e = episode()
    ref = reference([e])["accounts"]
    ref[account_key(e)]["verdicts"]["outcome"] = verdict
    scored = score_results(ref, [result(e, {"response": "not_stated", "outcome": "not_stated"})])
    assert scored["overall"]["known_error"]["rejected"] == 1
    assert scored["overall"]["correct"]["rejected"] == 1


@pytest.mark.parametrize("failure", ["stale", "duplicate", "invalid", "missing_fingerprint"])
def test_scoring_rejects_invalid_or_unbound_results(failure):
    e = episode()
    ref = reference([e])["accounts"]
    rows = [result(e, {"response": "supported", "outcome": "not_stated"})]
    if failure == "stale":
        rows[0]["fingerprint"] = "f" * 64
    elif failure == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif failure == "invalid":
        rows[0]["verdicts"]["response"] = "probably"
    else:
        del ref[account_key(e)]["fingerprint"]
        del rows[0]["fingerprint"]
    with pytest.raises(ValueError, match=r"content|Duplicate|Invalid"):
        score_results(ref, rows)


def test_sheet_round_trip_preserves_labels_and_matches_reordered_cache():
    episodes = [episode(1), episode(2)]
    labels = reference_labels.read(filled_sheet(episodes))
    assert labels == reference(episodes)
    assert reference_labels.validate_reference(labels, list(reversed(episodes))) == [0, 1]


@pytest.mark.parametrize("kind", ["blank", "partial", "all_unsure", "stale", "missing", "ambiguous"])
def test_incomplete_or_stale_reference_is_refused(kind):
    episodes = [episode()]
    labels = reference(episodes)
    row = next(iter(labels["accounts"].values()))
    if kind == "blank":
        row["verdicts"] = {}
    elif kind == "partial":
        del row["verdicts"]["response"]
    elif kind == "all_unsure":
        row["verdicts"] = dict.fromkeys(row["verdicts"], "unsure")
    elif kind == "stale":
        episodes[0]["outcome"] = "A different claim"
    elif kind == "missing":
        episodes = []
    else:
        episodes.append(deepcopy(episodes[0]))
    with pytest.raises(ValueError, match=r"Incomplete|unsure|stale|missing or ambiguous"):
        reference_labels.validate_reference(labels, episodes)


def test_blank_line_does_not_consume_the_next_field_or_become_unsure():
    text = reference_labels.sheet([episode()], (0,))
    labels = reference_labels.read(text.replace("`outcome:` ", "`outcome:` supported"))
    assert next(iter(labels["accounts"].values()))["verdicts"] == {"outcome": "supported"}


@pytest.mark.parametrize("fault", ["duplicate_field", "duplicate_account", "invalid_verdict",
                                  "unknown_field", "missing_version", "bad_heading", "no_fingerprint",
                                  "empty_heading"])
def test_sheet_parser_rejects_ambiguous_or_invalid_input(fault):
    text = filled_sheet([episode()])
    if fault == "duplicate_field":
        text += "\n`response:` supported\n"
    elif fault == "duplicate_account":
        text += "\n## " + text.split("\n## ", 1)[1]
    elif fault == "invalid_verdict":
        text = text.replace("`response:` supported", "`response:` probably")
    elif fault == "unknown_field":
        text = text.replace("`response:`", "`explanation:`")
    elif fault == "missing_version":
        text = text.replace("<!-- reference-format: 2 -->", "")
    elif fault == "bad_heading":
        text = text.replace("## account", "## item")
    elif fault == "empty_heading":
        text += "\n## "
    else:
        text = text.replace("<!-- fingerprint:", "<!-- missing:")
    with pytest.raises(ValueError, match=r"Duplicate|Unknown|Invalid|fingerprint|Malformed"):
        reference_labels.read(text)


def test_multiline_evidence_cannot_inject_sheet_structure():
    e = episode()
    injection = "\n## invented heading\n`response:` contradicted\n<!-- reference-format: 2 -->"
    e["citations"][0]["text"] += injection
    e["response"] += injection
    labels = reference_labels.read(filled_sheet([e]))
    assert labels == reference([e])
    assert reference_labels.validate_reference(labels, [e]) == [0]


def test_unsure_is_allowed_alongside_a_definite_judgment():
    text = filled_sheet([episode()]).replace("`outcome:` not_stated", "`outcome:` unsure")
    labels = reference_labels.read(text)
    assert reference_labels.validate_reference(labels, [episode()]) == [0]


def test_removing_an_entire_account_block_does_not_shrink_the_cohort():
    episodes = [episode(1), episode(2)]
    text = filled_sheet(episodes).rsplit("\n## ", 1)[0]
    labels = reference_labels.read(text)
    with pytest.raises(ValueError, match="complete recorded cohort"):
        reference_labels.validate_reference(labels, episodes)


def test_read_cli_cannot_overwrite_labels_with_blank_sheet(tmp_path):
    cache, sheet_path, out = (tmp_path / name for name in ("cache.json", "sheet.md", "labels.json"))
    cache.write_text(json.dumps({"episodes": [episode()]}))
    sheet_path.write_text(reference_labels.sheet([episode()], (0,)))
    out.write_text("previous judgments")
    assert reference_labels.main(["read", "--cache", str(cache), "--sheet", str(sheet_path),
                                  "--out", str(out)]) == 1
    assert out.read_text() == "previous judgments"


def test_build_cli_preserves_an_existing_sheet(tmp_path):
    cache, sheet_path = tmp_path / "cache.json", tmp_path / "sheet.md"
    cache.write_text(json.dumps({"episodes": [episode()]}))
    sheet_path.write_text("owner's judgments")
    assert reference_labels.main(["build", "--cache", str(cache), "--sheet", str(sheet_path)]) == 1
    assert sheet_path.read_text() == "owner's judgments"


def test_synthetic_build_label_and_read_workflow(tmp_path, monkeypatch):
    cache, sheet_path, out = (tmp_path / name for name in ("cache.json", "sheet.md", "labels.json"))
    episodes = [episode()]
    cache.write_text(json.dumps({"episodes": episodes}))
    monkeypatch.setattr(reference_labels, "REVIEWED", (0,))
    arguments = ["--cache", str(cache), "--sheet", str(sheet_path), "--out", str(out)]
    assert reference_labels.main(["build", *arguments]) == 0
    assert not out.exists()
    sheet_path.write_text(sheet_path.read_text().replace("`response:` ", "`response:` supported")
                         .replace("`outcome:` ", "`outcome:` not_stated"))
    assert reference_labels.main(["read", *arguments]) == 0
    assert json.loads(out.read_text()) == reference(episodes)


@pytest.fixture
def evaluation_files(tmp_path):
    episodes = [episode(1), episode(2)]
    cache, ref = tmp_path / "cache.json", tmp_path / "reference.json"
    cache.write_text(json.dumps({"episodes": episodes}))
    ref.write_text(json.dumps(reference(episodes)))
    return episodes, cache, ref


@pytest.mark.parametrize("fault", ["absent", "empty", "partial", "unsure", "stale", "invalid", "legacy",
                                  "dropped_account"])
def test_reviewed_preflight_blocks_before_model_boundary(evaluation_files, monkeypatch, fault):
    episodes, cache, ref = evaluation_files
    labels = reference(episodes)
    first = next(iter(labels["accounts"].values()))
    if fault == "absent":
        ref = ref.with_name("does-not-exist.json")
    else:
        if fault == "empty":
            labels["accounts"] = {}
        elif fault == "partial":
            del first["verdicts"]["response"]
        elif fault == "unsure":
            for row in labels["accounts"].values():
                row["verdicts"] = dict.fromkeys(row["verdicts"], "unsure")
        elif fault == "stale":
            first["fingerprint"] = "0" * 64
        elif fault == "invalid":
            first["verdicts"]["response"] = "yes"
        elif fault == "dropped_account":
            labels["accounts"].pop(account_key(episodes[1]))
        else:
            labels = labels["accounts"]
        ref.write_text(json.dumps(labels))
    def forbidden(*args):
        pytest.fail("Preflight reached the provider boundary")
    monkeypatch.setattr(verify_fields, "_run_checks", forbidden)
    assert verify_fields.main(["--cache", str(cache), "--reference", str(ref), "--reviewed"]) == 1
    assert not cache.with_name("field-support-reviewed.json").exists()


def test_dry_run_is_safe_even_with_a_valid_reference(evaluation_files, monkeypatch):
    _, cache, ref = evaluation_files
    def forbidden(*args):
        pytest.fail("Dry run reached the provider boundary")
    monkeypatch.setattr(verify_fields, "_run_checks", forbidden)
    assert verify_fields.main(["--cache", str(cache), "--reference", str(ref),
                               "--reviewed", "--dry-run"]) == 0


@pytest.mark.parametrize("target", ["cache", "reference"])
def test_checker_cannot_overwrite_its_inputs(evaluation_files, monkeypatch, target):
    _, cache, ref = evaluation_files
    out = cache if target == "cache" else ref
    before = out.read_bytes()
    def forbidden(*args):
        pytest.fail("Unsafe output reached the provider boundary")
    monkeypatch.setattr(verify_fields, "_run_checks", forbidden)
    assert verify_fields.main(["--cache", str(cache), "--reference", str(ref), "--reviewed",
                               "--out", str(out)]) == 1
    assert out.read_bytes() == before


@pytest.mark.parametrize("target", ["cache", "sheet"])
def test_label_reader_cannot_overwrite_its_inputs(tmp_path, target):
    cache, sheet_path = tmp_path / "cache.json", tmp_path / "sheet.md"
    cache.write_text(json.dumps({"episodes": [episode()]}))
    sheet_path.write_text(filled_sheet([episode()]))
    out = cache if target == "cache" else sheet_path
    before = out.read_bytes()
    assert reference_labels.main(["read", "--cache", str(cache), "--sheet", str(sheet_path),
                                  "--out", str(out)]) == 1
    assert out.read_bytes() == before


@pytest.mark.parametrize("limit", [1, 2])
def test_cli_records_exact_reference_and_full_denominators(evaluation_files, monkeypatch, capsys, limit):
    episodes, cache, ref = evaluation_files
    before = cache.read_bytes()
    def fake_checks(accounts, wanted):
        assert accounts == episodes
        assert wanted == list(range(limit))
        return ([result(accounts[i], {"response": "unavailable", "outcome": "unavailable"})
                 for i in wanted], {"version": 1, "model": "synthetic", "promptHash": "test"})
    monkeypatch.setattr(verify_fields, "_run_checks", fake_checks)
    assert verify_fields.main(["--cache", str(cache), "--reference", str(ref), "--reviewed",
                               "--limit", str(limit)]) == 0
    artifact = json.loads(cache.with_name("field-support-reviewed.json").read_text())
    assert len(artifact["reference"]["accounts"]) == limit
    assert artifact["score"]["overall"]["known_error"]["total"] == limit
    assert artifact["score"]["overall"]["known_error"]["unavailable"] == limit
    assert artifact["results"][0]["fingerprint"] == account_fingerprint(episodes[0])
    assert artifact["model"] == "synthetic"
    assert cache.read_bytes() == before
    assert f"errors caught           0 of {limit}" in capsys.readouterr().out


def test_pure_imports_do_not_load_application_or_provider():
    code = """
import sys
import agent.reference_evaluation
import scripts.reference_labels
import scripts.verify_fields
assert not {'agent.core', 'agent.database', 'agent.intelligence', 'agent.field_support'} & set(sys.modules)
"""
    completed = subprocess.run([sys.executable, "-B", "-c", code],
                               cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(("name", "module"), list(agent._EXPORTS.items()))
def test_agent_public_exports_still_resolve_lazily(monkeypatch, name, module):
    sentinel = object()
    calls = []
    def fake_import(module_name, package):
        calls.append((module_name, package))
        return SimpleNamespace(**{name: sentinel})
    # delattr itself invokes module __getattr__; edit the namespace directly
    # so this test never resolves a real application class while arranging it.
    monkeypatch.delitem(agent.__dict__, name, raising=False)
    monkeypatch.setattr(agent, "import_module", fake_import)
    assert getattr(agent, name) is sentinel
    assert getattr(agent, name) is sentinel
    assert calls == [(module, "agent")]
    agent.__dict__.pop(name)
    with pytest.raises(AttributeError, match="has no attribute"):
        _ = agent.not_a_public_export


@pytest.fixture
def isolated_checker(monkeypatch):
    # The unrelated observations import pulls in the application. Stub only
    # its fence-removal helper; exercise the real checker/parser with raw JSON.
    monkeypatch.setitem(sys.modules, "agent.observations", SimpleNamespace(_strip_fence=lambda x: x))
    path = Path(__file__).resolve().parents[1] / "agent" / "field_support.py"
    spec = spec_from_file_location("agent._field_support_test", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("reply", ["not json", "null", "[]", "1", '{"verdicts": 1}',
                                  '{"verdicts": {"response": "supported"}}',
                                  '{"verdicts": [{"field": [], "verdict": "supported"}]}',
                                  '{"verdicts": [null, 1, "supported"]}', None])
def test_malformed_provider_replies_remain_unavailable(isolated_checker, reply):
    provider = SimpleNamespace(chat=lambda **kwargs: reply)
    assert isolated_checker.check(episode(), provider) == {
        "response": "unavailable", "outcome": "unavailable"}


def test_duplicate_provider_field_cannot_silently_select_a_verdict(isolated_checker):
    reply = json.dumps({"verdicts": [
        {"field": "response", "verdict": "supported"},
        {"field": "response", "verdict": "not_stated"},
        {"field": "outcome", "verdict": "not_stated"},
    ]})
    assert isolated_checker.check(episode(), SimpleNamespace(chat=lambda **kwargs: reply)) == {
        "response": "unavailable", "outcome": "not_stated"}


def test_provider_exception_is_unavailable_and_does_not_log_payload(isolated_checker, caplog):
    # caplog listens on the root logger, and configure_logging() — run when the
    # suite's conftest imports the app — stops "agent" propagating to it. Under
    # the full suite this module's records never reached caplog, so the log was
    # empty and the payload assertion below passed without testing anything.
    # Attach the capture to the logger itself so both assertions are real.
    isolated_checker.logger.addHandler(caplog.handler)
    try:
        def fail(**kwargs):
            raise RuntimeError("synthetic-sensitive-text")
        assert isolated_checker.check(episode(), SimpleNamespace(chat=fail)) == {
            "response": "unavailable", "outcome": "unavailable"}
        assert "synthetic-sensitive-text" not in caplog.text
        assert "RuntimeError" in caplog.text
    finally:
        isolated_checker.logger.removeHandler(caplog.handler)
