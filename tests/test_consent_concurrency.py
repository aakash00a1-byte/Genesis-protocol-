"""R2: an approval is consumed exactly once, even under concurrent claims.

The store must be safe across threads *and* processes, because the Space may
run several workers. Both tests race real ``claim()`` calls on one id and
assert a single winner; nothing is mocked.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genesis_protocol.agentic.code_consent import CodeConsentStore

OWNER = 1
CODE = "print('race')"


def _claim_in_process(path: str, request_id: str, queue) -> None:
    store = CodeConsentStore(path=path)
    request, reason = store.claim(OWNER, request_id, CODE)
    queue.put("approved" if request is not None else reason)


def _spawn(path: str, request_id: str, workers: int = 4) -> list:
    ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else mp.get_context()
    queue = ctx.Queue()
    processes = [ctx.Process(target=_claim_in_process, args=(path, request_id, queue))
                 for _ in range(workers)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
    results = [queue.get(timeout=5) for _ in range(workers)]
    for process in processes:
        process.close()
    return results


def test_concurrent_threads_claim_exactly_once(tmp_path):
    store = CodeConsentStore(path=str(tmp_path / "consent.json"))
    approval = store.request(OWNER, CODE)

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(
            lambda _: store.claim(OWNER, approval.request_id, CODE), range(16)
        ))

    wins = [request for request, _ in results if request is not None]
    reasons = [reason for request, reason in results if request is None]
    assert len(wins) == 1
    assert reasons and all("already used" in reason for reason in reasons)


def test_concurrent_processes_claim_exactly_once(tmp_path):
    path = str(tmp_path / "consent.json")
    approval = CodeConsentStore(path=path).request(OWNER, CODE)

    results = _spawn(path, approval.request_id)

    assert results.count("approved") == 1, results
    assert all("already used" in reason for reason in results if reason != "approved"), results


def test_the_winner_still_gets_the_code_and_the_loser_leaves_it_spent(tmp_path):
    path = str(tmp_path / "consent.json")
    store = CodeConsentStore(path=path)
    approval = store.request(OWNER, CODE)

    first, _ = store.claim(OWNER, approval.request_id, CODE)
    second, reason = store.claim(OWNER, approval.request_id, CODE)

    assert first is not None and first.code == CODE
    assert second is None and "already used" in reason
    assert store.get(OWNER, approval.request_id) is None


def test_concurrent_claims_keep_user_binding_and_hash(tmp_path):
    store = CodeConsentStore(path=str(tmp_path / "consent.json"))
    approval = store.request(OWNER, CODE)

    with ThreadPoolExecutor(max_workers=8) as pool:
        wrong_user = list(pool.map(lambda _: store.claim(2, approval.request_id, CODE), range(8)))

    assert all(request is None for request, _ in wrong_user)
    assert all("another user" in reason for _, reason in wrong_user)
    # Still unused for its owner after the foreign attempts.
    claimed, reason = store.claim(OWNER, approval.request_id, CODE)
    assert claimed is not None and reason == "approved"


def test_concurrent_claims_with_a_modified_code_never_succeed(tmp_path):
    store = CodeConsentStore(path=str(tmp_path / "consent.json"))
    approval = store.request(OWNER, CODE)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: store.claim(OWNER, approval.request_id, "print('evil')"), range(8)
        ))

    assert all(request is None for request, _ in results)
    assert all("does not match" in reason for _, reason in results)


def test_lock_file_is_created_next_to_the_state(tmp_path):
    store = CodeConsentStore(path=str(tmp_path / "consent.json"))
    store.request(OWNER, CODE)
    store.claim(OWNER, store.pending(OWNER)[0].request_id, CODE)

    assert store.lock_path.exists()
    assert store.lock_path.parent == store.path.parent
