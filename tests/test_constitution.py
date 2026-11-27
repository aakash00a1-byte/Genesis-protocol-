"""The constitution must say what the code does, and never grant anything."""

from genesis_protocol import constitution
from genesis_protocol.agentic.policy import PRIVILEGED_OPERATIONS, AgentPolicy


def test_the_constitution_keeps_the_twelve_principles():
    assert len(constitution.PRINCIPLES) == 12
    joined = " ".join(constitution.PRINCIPLES).lower()
    for phrase in ("security first", "evidence over assumptions", "truth over pleasing",
                   "human authority", "no unauthorized self-approval",
                   "no privilege escalation", "no claim of discovery"):
        assert phrase in joined, phrase


def test_every_privileged_operation_is_reserved_by_the_constitution():
    """The two lists must not drift apart: policy denies, constitution reserves."""
    missing = set(PRIVILEGED_OPERATIONS) - set(constitution.OWNER_ONLY_OPERATIONS)
    assert not missing, f"policy denies {missing} but the constitution does not reserve it"
    for op in PRIVILEGED_OPERATIONS:
        verdict = constitution.check(op)
        assert verdict.reserved is True, op
        assert verdict.permitted_without_owner is False, op
        assert verdict.article is not None, op


def test_the_constitution_never_grants_an_unknown_operation():
    verdict = constitution.check("something_new")
    assert verdict.reserved is False
    # not reserved is *not* an authorization - policy still decides
    assert "agentic.policy" in verdict.reason


def test_an_unnamed_operation_fails_closed():
    for value in ("", "   ", None):
        verdict = constitution.check(value)
        assert verdict.reserved is True
        assert verdict.permitted_without_owner is False


def test_policy_actually_denies_what_the_constitution_reserves():
    policy = AgentPolicy(owner_ids={1})
    for op in sorted(constitution.OWNER_ONLY_OPERATIONS):
        decision = policy.authorize_operation(1, op, owner_approved=True)
        assert decision.allowed is False, op
        assert decision.requires_owner_approval is True, op


def test_the_constitution_disclaims_consciousness_explicitly():
    joined = " ".join(constitution.NON_CLAIMS).lower()
    assert "consciousness" in joined or "self-awareness" in joined
    assert "consensus" in joined


def test_summary_is_json_shaped_and_names_the_document():
    data = constitution.summary()
    assert data["document"] == "docs/CONSTITUTION.md"
    assert len(data["articles"]) == len(constitution.ARTICLES)
    assert set(data["principles"]) == set(constitution.PRINCIPLES)
    assert data["owner_only_operations"]
    assert "grants no permission" in data["note"]


def test_article_lookup():
    assert constitution.article("3")["title"].startswith("Human authority")
    assert constitution.article("999") is None
