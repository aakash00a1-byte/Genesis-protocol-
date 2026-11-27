"""Consensus is not truth: agreement between correlated models is one opinion.

These tests pin the property that matters - the assessment must get *harder* to
satisfy as independence drops, and it must never report evidence.
"""

import pytest

from genesis_protocol.ai.council import CouncilResult, CouncilStrategy
from genesis_protocol.ai.independence import assess, describe, provider_family


class Member:
    def __init__(self, provider, model, content, sources=None, error=None):
        self.provider = provider
        self.model = model
        self.content = content
        self.sources = sources or []
        self.error = error


ANSWER = "The treaty was signed in 1648 and ended the Thirty Years War."


def test_same_family_agreement_is_flagged_as_correlated():
    members = [Member("groq", "llama-3.3-70b", ANSWER),
               Member("cerebras", "llama-3.3-70b", ANSWER),
               Member("nvidia", "llama-3.1-8b", ANSWER)]
    result = assess(members)
    assert result.agreement == 1.0
    assert result.correlated_risk == "high"
    assert result.requires_independent_check is True
    assert result.is_evidence is False
    assert any("family" in r for r in result.reasons)


def test_distinct_families_agreeing_is_lower_risk_but_still_not_evidence():
    members = [Member("groq", "llama-3.3-70b", ANSWER),
               Member("gemini", "gemini-2.5-flash", ANSWER),
               Member("mistral", "ministral-8b", ANSWER)]
    result = assess(members)
    assert result.agreement == 1.0
    assert result.correlated_risk == "low"
    assert result.is_evidence is False
    assert "not proof" in " ".join(result.reasons)


def test_disagreement_is_not_dressed_up_as_consensus():
    members = [Member("groq", "llama", "Paris is the capital of France."),
               Member("gemini", "gemini", "Berlin is the capital of Germany."),
               Member("mistral", "ministral", "Madrid is the capital of Spain.")]
    result = assess(members)
    assert result.agreement < 0.6
    assert result.largest_cluster == 1


def test_aggregators_count_for_less_independence():
    direct = [Member("groq", "llama", ANSWER), Member("gemini", "gemini", ANSWER)]
    proxied = [Member("openrouter", "llama", ANSWER), Member("orcarouter", "gemini", ANSWER)]
    assert assess(direct).independence > assess(proxied).independence


def test_shared_sources_raise_the_risk():
    url = "https://en.wikipedia.org/wiki/Peace_of_Westphalia"
    same = [Member("groq", "llama", ANSWER, [url]),
            Member("gemini", "gemini", ANSWER, [url])]
    result = assess(same)
    assert result.source_overlap == pytest.approx(1.0)
    assert result.correlated_risk in {"medium", "high"}


def test_a_silent_member_is_not_a_witness():
    members = [Member("groq", "llama", ANSWER),
               Member("gemini", "gemini", "", error="timeout"),
               Member("mistral", "ministral", "   ")]
    result = assess(members)
    assert result.members == 1


def test_no_usable_members_is_unknown_not_evidence():
    result = assess([Member("groq", "llama", "", error="boom")])
    assert result.correlated_risk == "unknown"
    assert result.is_evidence is False
    assert result.requires_independent_check is True


def test_provider_family_mapping():
    assert provider_family("groq") == provider_family("cerebras") == "open-weights"
    assert provider_family("gemini") == "google"
    assert provider_family("openrouter") == "aggregator"
    assert provider_family("something", "gpt-4o-mini") == "openai"


def test_describe_is_honest_about_evidence():
    result = assess([Member("groq", "llama", ANSWER)])
    text = describe(result)
    assert "evidence: no" in text


def test_council_result_carries_the_assessment_without_breaking_callers():
    result = CouncilResult(True, CouncilStrategy.BEST, answer="x")
    assert result.independence is None            # additive, optional
    result.independence = assess([Member("groq", "llama", "x")]).to_dict()
    assert result.independence["is_evidence"] is False
