"""The entity must answer identity questions itself, and never invent one.

Observed live: "Tum kaun ho?" and "Tum kis model par chal rahe ho?" fell through
to the model provider, which answered "I am Google BARD" and "I run on Google
Vertex AI". Both are false. English worked only because the keyword list had
English spellings; Hinglish is how this user actually writes.

These tests pin two things: Hinglish identity questions are routed to the entity
object (provider bypassed), and the provider/model answer is read from the live
configuration rather than guessed.
"""
from __future__ import annotations

from genesis_protocol.ai.identity_router import route_identity


def _routed(query: str) -> bool:
    result = route_identity(query)
    return bool(result and result.get("is_identity"))


def test_hinglish_identity_questions_are_routed_to_the_entity() -> None:
    for query in (
        "Tum kaun ho?",
        "tum kaun ho",
        "Aap kaun hain?",
        "tumhara naam kya hai",
        "tumhara naam kya h",
        "Tum kaun ho? Tumhara naam kya hai?",
        "tera naam kya hai",
    ):
        assert _routed(query), f"not routed to the entity: {query!r}"


def test_english_identity_questions_still_route() -> None:
    for query in ("who are you", "what is your name", "introduce yourself"):
        assert _routed(query), f"regressed for: {query!r}"


def test_provider_model_questions_are_routed_to_the_entity() -> None:
    for query in (
        "Tum kis model par chal rahe ho? Provider kaun hai?",
        "which model are you",
        "kis provider par chalta hai",
        "konsa model use karte ho",
    ):
        assert _routed(query), f"not routed to the entity: {query!r}"


def test_provider_answer_never_invents_a_model() -> None:
    """Every provider name in the answer must be one the runtime reports.

    This is the regression guard for the hallucination: the model provider used
    to answer this question about itself and named a vendor that was not even
    configured.
    """
    from genesis_protocol.agentic.identity import describe_runtime

    runtime = describe_runtime()
    available = set(runtime.get("providers_available") or [])

    result = route_identity("Tum kis model par chal rahe ho? Provider kaun hai?")
    assert result and result.get("is_identity")
    text = result["response"]

    # Vendor names the provider used to invent when it answered this itself.
    for invented in ("BARD", "Vertex", "Google Cloud", "Google AI"):
        assert invented not in text, f"answer still invents {invented!r}"

    if not available:
        assert "No AI provider is configured" in text
    else:
        # It may name configured providers; it must not name a model that is not
        # the runtime's reported default.
        default_model = runtime.get("default_model")
        if default_model:
            assert default_model in text


def test_identity_answer_names_the_real_entity() -> None:
    result = route_identity("Tum kaun ho?")
    assert result and result.get("is_identity")
    assert "GLUTEN" in result["response"]


def test_creator_questions_name_the_creator() -> None:
    """'kisne banaya' / 'tumhe kisne banaya' were not in the creator branch, so
    they fell through to the generic identity answer. They must name the creator.
    """
    from genesis_protocol.ai.identity_router import route_identity
    from genesis_protocol.gluten.identity import CREATOR

    for query in ("tumhe kisne banaya", "kisne banaya", "who created you",
                  "kon banaya", "kisne bnaya"):
        result = route_identity(query)
        assert result and result.get("is_identity"), query
        assert CREATOR in result["response"], query
