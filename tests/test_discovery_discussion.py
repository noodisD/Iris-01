"""Selected discussion excludes owner-rejected account classifications."""

from agent.discussion import _personal
from agent.evidence_ref import DynamicRef


def test_corrected_memberships_do_not_enter_selected_evidence():
    did = "d_" + "a" * 64
    ref = DynamicRef(kind="dynamic", dynamicId=did, range="all", snapshot="b" * 64)

    def account(aid):
        return {
            "id": aid, "actor": "self", "recordKind": "event", "recordedOn": None,
            "citations": [{"entryId": int(aid[-1]), "entryDate": None,
                           "text": f"Original paragraph for {aid}"}],
            **dict.fromkeys((
                "situation", "response", "demand", "information", "feeling", "concern",
                "immediateOutcome", "laterOutcome", "explanation", "selfReport")),
        }

    evidence = {
        "pattern": {
            "title": "Responding when asked", "context": {"refs": []},
            "response": {"refs": []}, "ownerMeanings": [], "evidenceState": "emerging",
            "exceptionGroupIds": [], "responseElsewhereGroupIds": [],
            "unknownAccountCount": 0, "possibleMeaning": None, "alternative": None,
            "openQuestion": "What differs?", "feedback": None,
        },
        "groups": {did: [
            {"id": "empty", "role": "support", "accountIds": ["a1"]},
            {"id": "mixed", "role": "support", "accountIds": ["a2", "a3"]},
        ]},
        "memberships": {did: [
            {"groupId": "empty", "accountId": "a1", "excluded": True, "ownerVerdict": "no"},
            {"groupId": "mixed", "accountId": "a2", "excluded": True, "ownerVerdict": "no"},
            {"groupId": "mixed", "accountId": "a3", "excluded": False, "ownerVerdict": None},
        ]},
        "accounts": {aid: account(aid) for aid in ("a1", "a2", "a3")},
        "coverage": {},
    }
    selected = _personal(ref, evidence)
    assert selected["limits"]["totalGroupCount"] == 1
    assert selected["limits"]["totalGroupCounts"] == {did: {"support": 1}}
    assert selected["limits"]["selectedGroupCount"] == 1
    group = selected["selectedGroups"][0]
    assert group["group"]["id"] == "mixed"
    assert group["group"]["accountIds"] == ["a3"]
    assert group["group"]["totalAccountCount"] == 1
    assert [row["accountId"] for row in group["memberships"]] == ["a3"]
    assert [row["accountId"] for row in group["accounts"]] == ["a3"]
    assert group["accounts"][0]["originalPassages"][0]["exactExcerpt"] == "Original paragraph for a3"
