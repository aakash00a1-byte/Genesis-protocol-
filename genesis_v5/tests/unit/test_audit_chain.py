"""Tamper-evidence tests for the hash-chained AuditLogger.

The audit log must let a reviewer detect a record that was changed, removed or
reordered after the fact. These tests exercise the chain directly and never
rely on the internal record list being trustworthy.
"""
from __future__ import annotations

from genesis.security.audit import AuditLogger


def _fill(audit: AuditLogger, n: int = 4) -> None:
    for i in range(n):
        audit.record(event_type=f"e{i}", actor="agent", action=f"a{i}")


def test_chain_verifies_when_untouched() -> None:
    audit = AuditLogger()
    _fill(audit)
    ok, bad, reason = audit.verify_chain()
    assert ok is True
    assert bad is None
    assert reason == ""


def test_records_carry_chain_fields() -> None:
    audit = AuditLogger()
    _fill(audit, 2)
    events = audit.events()
    assert [e["seq"] for e in events] == [0, 1]
    assert events[0]["prev_hash"] == AuditLogger.GENESIS_HASH
    assert events[1]["prev_hash"] == events[0]["hash"]
    assert all(e["hash"] for e in events)


def test_modified_record_is_detected() -> None:
    audit = AuditLogger()
    _fill(audit)
    audit._records[1]["action"] = "tampered"
    ok, bad, reason = audit.verify_chain()
    assert ok is False
    assert bad == 1
    assert "hash" in reason.lower() or "modified" in reason.lower()


def test_missing_record_is_detected() -> None:
    audit = AuditLogger()
    _fill(audit, 4)
    del audit._records[2]
    ok, bad, reason = audit.verify_chain()
    assert ok is False
    assert bad is not None
    assert "missing" in reason.lower() or "seq" in reason.lower()


def test_reordered_records_are_detected() -> None:
    audit = AuditLogger()
    _fill(audit, 4)
    audit._records[1], audit._records[2] = audit._records[2], audit._records[1]
    ok, bad, reason = audit.verify_chain()
    assert ok is False
    assert bad is not None


def test_appending_after_tamper_still_detected() -> None:
    audit = AuditLogger()
    _fill(audit, 3)
    audit._records[0]["actor"] = "someone-else"
    audit.record(event_type="later", actor="agent", action="z")
    ok, bad, reason = audit.verify_chain()
    assert ok is False
    assert bad == 0


def test_checkpoint_matches_head_and_detects_rewrite() -> None:
    """A checkpoint is a commitment to the chain head.

    It catches a sophisticated rewrite where the attacker also recomputes every
    hash (so verify_chain would pass), which an external checkpoint still
    rejects. A mid-chain edit that leaves the head hash untouched is caught by
    verify_chain instead, not here.
    """
    audit = AuditLogger()
    _fill(audit, 3)
    cp = audit.checkpoint()
    assert cp["count"] == 3
    assert audit.verify_checkpoint(cp) is True

    # Rewrite a middle record and recompute the whole chain like a real attacker.
    audit._records[1]["action"] = "changed"
    prev = AuditLogger.GENESIS_HASH
    for i, rec in enumerate(audit._records):
        rec["seq"] = i
        rec["prev_hash"] = prev
        rec["hash"] = AuditLogger._compute_hash(rec)
        prev = rec["hash"]

    assert audit.verify_chain()[0] is True, "rewritten chain is internally consistent"
    assert audit.verify_checkpoint(cp) is False, "checkpoint failed to catch a rewrite"


def test_checkpoint_detects_truncation() -> None:
    audit = AuditLogger()
    _fill(audit, 3)
    cp = audit.checkpoint()
    del audit._records[-1]
    assert audit.verify_checkpoint(cp) is False


def test_clear_resets_chain() -> None:
    audit = AuditLogger()
    _fill(audit)
    audit.clear()
    assert audit.count() == 0
    ok, bad, reason = audit.verify_chain()
    assert ok is True
    _fill(audit, 1)
    assert audit.events()[0]["seq"] == 0
    assert audit.events()[0]["prev_hash"] == AuditLogger.GENESIS_HASH


def test_events_returns_a_copy_not_internal_state() -> None:
    """Mutating the returned list must not alter the stored chain."""
    audit = AuditLogger()
    _fill(audit, 2)
    events = audit.events()
    events[0]["action"] = "mutated-outside"
    ok, bad, reason = audit.verify_chain()
    assert ok is True, "external mutation of events() corrupted the chain"


def test_disabled_logger_records_nothing_and_verifies() -> None:
    audit = AuditLogger(enabled=False)
    audit.record(event_type="x", actor="a", action="y")
    assert audit.count() == 0
    assert audit.verify_chain()[0] is True
