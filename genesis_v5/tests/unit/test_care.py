"""Tests for the care companion: support without judgement or therapy."""
from __future__ import annotations

from genesis.care.companion import CareCompanion, CareMode


def test_overwhelmed_message_gets_a_steady_response() -> None:
    companion = CareCompanion()
    response = companion.respond("I am exhausted, I cannot do this anymore")
    assert response.mode is CareMode.STEADY
    assert response.acknowledgement
    assert response.next_step


def test_self_blame_is_reframed_without_condemning() -> None:
    companion = CareCompanion()
    response = companion.respond("everything is my fault, i am a failure")
    assert response.mode is CareMode.REFRAME
    assert response.to_dict()["blames_user"] is False


def test_crisis_signal_routes_to_human_help() -> None:
    companion = CareCompanion()
    response = companion.respond("I want to die, there is no reason to live")
    assert response.mode is CareMode.PROFESSIONAL_REFERRAL
    assert response.referral
    assert "therapist" in response.resource_note.lower()
    assert response.to_dict()["is_therapist"] is False


def test_companion_holds_the_users_own_goal_not_its_own() -> None:
    companion = CareCompanion()
    response = companion.respond(
        "I am so tired of trying", goal="finish my project"
    )
    assert "finish my project" in response.next_step


def test_summary_reports_no_blame_and_no_therapy() -> None:
    companion = CareCompanion()
    companion.respond("I am overwhelmed")
    companion.respond("I want to end my life")
    summary = companion.summary()
    assert summary["blamed_users"] == 0
    assert summary["acted_as_therapist"] == 0
    assert summary["referrals_made"] == 1
