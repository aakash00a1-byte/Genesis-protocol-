"""Tests for the self-improvement launcher (scripts/self_improve.py).

The launcher only *starts* an OpenHands conversation and never merges, so the
tests cover the pure pieces: the task prompt is self-contained, and a dry run
prints the prompt without touching the network.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "self_improve.py"


def _load():
    spec = importlib.util.spec_from_file_location("self_improve", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_approval_package_imports_from_another_cwd(tmp_path) -> None:
    """Regression: `python3 scripts/self_improve.py` from any cwd.

    Python puts scripts/ on sys.path, not the repo root, so the approval
    package failed to import and every /approve was silently ignored.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check-approvals"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_task_prompt_is_self_contained() -> None:
    module = _load()
    text = module.TASK.format(repo="owner/repo", branch="main", topic="harden the relay")
    # Must name the repo/branch, forbid merging, and point at the real tests.
    assert "owner/repo" in text and "main" in text
    assert "harden the relay" in text
    assert "Do NOT merge" in text
    assert "tests/" in text


def test_dry_run_prints_prompt_without_network() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "PULL REQUEST" in proc.stdout or "improvement" in proc.stdout


def test_start_conversation_shape(monkeypatch) -> None:
    module = _load()
    captured: dict = {}

    def _fake_api(method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"id": "task-1", "app_conversation_id": "conv-1"}

    monkeypatch.setattr(module, "_api", _fake_api)
    monkeypatch.setattr(module, "REPO", "owner/repo")
    monkeypatch.setattr(module, "BRANCH", "main")
    start = module.start_conversation("harden the relay")
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/app-conversations"
    assert captured["payload"]["selected_repository"] == "owner/repo"
    assert captured["payload"]["selected_branch"] == "main"
    assert "harden the relay" in captured["payload"]["initial_message"]["content"][0]["text"]
    assert start["app_conversation_id"] == "conv-1"


def test_slug_is_branch_safe() -> None:
    module = _load()
    slug = module._slug("Harden the relay: retries, edge-cases!")
    assert slug == "harden-the-relay-retries-edge-cases"
    assert " " not in slug and ":" not in slug


def test_open_agent_prs_filters_to_agent_branches(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_github",
        lambda *a, **k: [
            {"head": {"ref": "agent/self-improve-x"}},
            {"head": {"ref": "feature/human-work"}},
            {"head": {"ref": "agent/self-improve-y"}},
        ],
    )
    assert len(module.open_agent_prs()) == 2


def test_run_cycle_pauses_when_too_many_agent_prs(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "MAX_OPEN_PRS", 1)
    monkeypatch.setattr(module, "open_agent_prs", lambda: [{"number": 1}])
    started: list = []
    monkeypatch.setattr(module, "start_conversation", lambda topic: started.append(topic) or {})
    monkeypatch.setattr(module, "_notify", lambda text: None)
    module.run_cycle(0)
    assert started == []


def _github_with_mergeability(prs: list[dict], detail: dict[int, dict]):
    def _fake(method, path, payload=None):
        if "?" in path:
            return prs
        return detail[int(path.rsplit("/", 1)[-1])]

    return _fake


def test_open_agent_prs_excludes_prs_that_cannot_merge(monkeypatch) -> None:
    """Regression: a conflicted PR must not hold a review slot forever.

    PR #15 sat at mergeable=false / mergeable_state=dirty and the loop logged
    "5 agent PRs already await review; skipping this cycle" for two days.
    """
    module = _load()
    prs = [
        {"number": 15, "head": {"ref": "agent/self-improve-conflicted"}},
        {"number": 16, "head": {"ref": "agent/self-improve-clean"}},
        {"number": 17, "head": {"ref": "agent/self-improve-stale"}},
        {"number": 18, "head": {"ref": "feature/human-work"}},
    ]
    detail = {
        15: {"mergeable": False, "mergeable_state": "dirty"},
        16: {"mergeable": True, "mergeable_state": "unstable"},
        17: {"mergeable": True, "mergeable_state": "dirty"},
    }
    monkeypatch.setattr(module, "_github", _github_with_mergeability(prs, detail))
    assert [p["number"] for p in module.open_agent_prs()] == [16]


def test_open_agent_prs_keeps_prs_with_unknown_mergeability(monkeypatch) -> None:
    module = _load()
    prs = [{"number": 5, "head": {"ref": "agent/self-improve-x"}}]
    monkeypatch.setattr(module, "_github", _github_with_mergeability(prs, {5: {}}))
    assert len(module.open_agent_prs()) == 1


def test_run_cycle_not_blocked_by_unmergeable_agent_pr(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "MAX_OPEN_PRS", 1)
    prs = [{"number": 15, "head": {"ref": "agent/self-improve-conflicted"}}]
    detail = {15: {"mergeable": False, "mergeable_state": "dirty"}}
    monkeypatch.setattr(module, "_github", _github_with_mergeability(prs, detail))
    started: list = []

    def _start(topic: str) -> dict:
        started.append(topic)
        raise RuntimeError("stop after the slot check")

    monkeypatch.setattr(module, "start_conversation", _start)
    monkeypatch.setattr(module, "_notify", lambda text: None)
    module.run_cycle(0)
    assert started, "a conflicted PR must not pause the loop"


def test_choose_topic_falls_back_to_rotation_without_backlog(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", "/nonexistent/backlog.jsonl")
    assert module.choose_topic(0) == module.TOPICS[0]


def test_choose_topic_prefers_highest_priority_evolution_proposal(monkeypatch, tmp_path) -> None:
    import json

    module = _load()
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text(
        json.dumps(
            {
                "proposals": [
                    {"title": "low", "priority": 0.2},
                    {"title": "Fix gateway: credential leak", "priority": 0.9},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(backlog))
    assert module.choose_topic(0) == "Fix gateway: credential leak"


def test_choose_topic_ignores_corrupt_backlog(monkeypatch, tmp_path) -> None:
    module = _load()
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text("not json\n", encoding="utf-8")
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(backlog))
    assert module.choose_topic(1) == module.TOPICS[1]


def test_choose_topic_skips_focuses_with_an_open_pr(monkeypatch, tmp_path) -> None:
    import json

    module = _load()
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text(
        json.dumps(
            {
                "proposals": [
                    {"title": "top idea", "priority": 0.9},
                    {"title": "second idea", "priority": 0.5},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(backlog))
    taken = {module._slug("top idea")}
    assert module.choose_topic(0, taken) == "second idea"


def test_choose_topic_rotates_when_every_focus_is_taken(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", "/nonexistent/backlog.jsonl")
    taken = {module._slug(t) for t in module.TOPICS}
    # Nothing left to pick, so it must still return a usable topic.
    assert module.choose_topic(3, taken) in module.TOPICS


def test_land_pr_reuses_existing_pr_on_422(monkeypatch, tmp_path) -> None:
    module = _load()
    calls = []

    def fake_git(*args, **kwargs):
        class R:
            returncode = 0
            stderr = ""

        return R()

    def fake_github(method, path, payload=None):
        calls.append((method, path))
        if method == "POST":
            raise RuntimeError('POST /pulls -> HTTP 422: {"message":"Validation Failed"}')
        return [{"html_url": "https://github.com/o/r/pull/7"}]

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module, "_github", fake_github)
    url = module.land_pr("diff --git a/x b/x\n", "some focus", "app123")
    assert url == "https://github.com/o/r/pull/7"
    assert any(m == "GET" and "pulls?head=" in p for m, p in calls)


def test_land_pr_reraises_unexpected_http_error(monkeypatch) -> None:
    module = _load()

    def fake_git(*args, **kwargs):
        class R:
            returncode = 0
            stderr = ""

        return R()

    def fake_github(method, path, payload=None):
        raise RuntimeError("POST /pulls -> HTTP 500: boom")

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module, "_github", fake_github)
    import pytest

    with pytest.raises(RuntimeError):
        module.land_pr("diff --git a/x b/x\n", "some focus", "app123")


def test_pr_number_extracts_trailing_id() -> None:
    module = _load()
    assert module._pr_number("https://github.com/o/r/pull/42") == "42"
    assert module._pr_number("https://github.com/o/r/pull/42/") == "42"
    assert module._pr_number("") == "?"


def test_process_approvals_merges_via_transport(monkeypatch) -> None:
    module = _load()
    module.GH_MERGE_TOKEN = "tok"
    replies: list[str] = []
    monkeypatch.setattr(module, "_notify", lambda text: replies.append(text))
    monkeypatch.setattr(module, "_incoming_commands", lambda: ["/approve 7"])
    monkeypatch.setattr(module, "_clear_commands", lambda: None)

    class Transport:
        def approve(self, token, reason=""):
            return f"✅ Approved & merged: fix relay ({token})"

        def reject(self, token, reason=""):
            return "rejected"

        def status(self, token):
            return "status"

        def list_open(self):
            return []

    monkeypatch.setattr(module, "_transport", lambda: Transport())
    module.process_approvals()
    assert any("Approved & merged" in r for r in replies)


def test_process_approvals_without_token_warns(monkeypatch) -> None:
    module = _load()
    replies: list[str] = []
    monkeypatch.setattr(module, "_notify", lambda text: replies.append(text))
    monkeypatch.setattr(module, "_incoming_commands", lambda: ["/approve 1"])
    monkeypatch.setattr(module, "_transport", lambda: None)
    monkeypatch.setattr(module, "_clear_commands", lambda: None)
    module.process_approvals()
    assert any("merge token" in r for r in replies)


def test_process_approvals_no_commands_is_noop(monkeypatch) -> None:
    module = _load()
    called = {"clear": False}
    monkeypatch.setattr(module, "_incoming_commands", lambda: [])
    monkeypatch.setattr(module, "_clear_commands", lambda: called.update(clear=True))
    module.process_approvals()
    assert called["clear"] is False


def test_requeue_stuck_orders_requeues_only_running(monkeypatch) -> None:
    """Regression: an order left ``running`` by a dead run must be requeued.

    Otherwise the order is stranded forever: the loop only ever starts orders
    in state ``queued``.
    """
    module = _load()
    monkeypatch.setattr(
        module,
        "_space_tasks",
        lambda: [
            {"id": "1", "state": "running"},
            {"id": "2", "state": "queued"},
            {"id": "3", "state": "done"},
        ],
    )
    patched: list[dict] = []
    monkeypatch.setattr(module, "_space_patch_task", lambda order_id, **kw: patched.append({"id": order_id, **kw}))

    module._requeue_stuck_orders()

    assert patched == [{"id": "1", "state": "queued", "note": "requeued after restart"}]



def test_open_agent_prs_fails_safe_on_unexpected_body(monkeypatch) -> None:
    """A non-list /pulls body must not read as 'no open PRs'.

    Failing open here would let the loop open a PR past the review cap; the
    count must fail closed instead.
    """
    import pytest

    module = _load()
    monkeypatch.setattr(module, "_github", lambda *a, **k: {"message": "Bad credentials"})
    with pytest.raises(RuntimeError):
        module.open_agent_prs()


def test_run_cycle_skips_when_pr_count_is_unavailable(monkeypatch) -> None:
    """An unreadable count skips the cycle instead of starting new work."""
    module = _load()

    def _boom():
        raise RuntimeError("GET /pulls -> HTTP 403")

    monkeypatch.setattr(module, "open_agent_prs", _boom)
    started: list = []
    monkeypatch.setattr(module, "start_conversation", lambda topic: started.append(topic) or {})
    module.run_cycle(0)
    assert started == []


def test_github_transport_error_is_a_runtime_error(monkeypatch) -> None:
    """A DNS/timeout failure must not surface as a bare None."""
    import urllib.error
    import urllib.request

    import pytest

    module = _load()

    def _fail(*a, **k):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    with pytest.raises(RuntimeError):
        module._github("GET", "/repos/x/y/pulls")


def test_dispatch_ci_posts_to_the_ci_workflow(monkeypatch) -> None:
    """CI must be dispatched by name for an agent PR.

    An agent PR is opened with the default GITHUB_TOKEN, whose events GitHub
    suppresses, so `on: pull_request` never fires. The harness must ask CI to
    run against the branch instead.
    """
    module = _load()
    seen: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=30):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["ref"] = json.loads(req.data.decode())["ref"]
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    module._dispatch_ci("agent/self-improve-x")

    assert seen["url"].endswith("/actions/workflows/ci.yml/dispatches")
    assert seen["method"] == "POST"
    assert seen["ref"] == "agent/self-improve-x"


def test_dispatch_ci_never_raises_when_the_call_fails(monkeypatch) -> None:
    """CI dispatch is best effort: a failure must not break the PR landing."""
    import urllib.error
    import urllib.request

    module = _load()

    def _fail(*a, **k):
        raise urllib.error.HTTPError("u", 403, "no", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    module._dispatch_ci("agent/self-improve-x")  # must not raise


def test_land_pr_dispatches_ci_for_the_new_branch(monkeypatch) -> None:
    """Opening a PR must also ask for its CI."""
    module = _load()
    monkeypatch.setattr(module, "_git", lambda *a: subprocess.CompletedProcess(a, 0, "", ""))
    monkeypatch.setattr(module, "_github", lambda *a, **k: {
        "html_url": "https://github.com/x/y/pull/1",
        "head": {"ref": "agent/self-improve-x"},
    })
    dispatched: list = []
    monkeypatch.setattr(module, "_dispatch_ci", lambda ref: dispatched.append(ref))

    url = module.land_pr("diff --git a/x b/x\n", "topic", "app-1")
    assert url == "https://github.com/x/y/pull/1"
    assert dispatched == ["agent/self-improve-x"]


# ---------------------------------------------------------------------------
# Evolution backlog: the committed file must be real, and the harness must
# actually consume it (SELF_IMPROVE_EVOLUTION_BACKLOG -> evolution_topics()).
# ---------------------------------------------------------------------------
BACKLOG = ROOT / "genesis_v5" / "data" / "evolution" / "backlog.jsonl"


def test_committed_evolution_backlog_exists_and_is_tracked() -> None:
    """The backlog must be in the repo, not ignored.

    `.gitignore` has a broad `data/` rule, which silently excluded
    genesis_v5/data/evolution/backlog.jsonl from the branch entirely.
    """
    assert BACKLOG.is_file(), f"{BACKLOG} must be committed"
    ignore = subprocess.run(
        ["git", "check-ignore", "-v", str(BACKLOG)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    # `git check-ignore` exits 1 (and prints nothing) when the path is tracked.
    assert "backlog.jsonl" not in ignore.stdout or "!" in ignore.stdout, (
        f"backlog is still ignored by {ignore.stdout.strip()}"
    )


def test_committed_evolution_backlog_is_well_formed() -> None:
    """Follow the schema the agent writes: real proposals, not placeholders."""
    records = [json.loads(line) for line in BACKLOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert records, "the backlog must not be empty"
    for record in records:
        for key in ("cycle_id", "verdict", "signals", "proposals"):
            assert key in record, f"missing {key}"
        assert record["proposals"], "a record with no proposals is a placeholder"
        for proposal in record["proposals"]:
            for key in (
                "proposal_id",
                "title",
                "area",
                "kind",
                "priority",
                "severity",
                "source_signal_id",
                "requires_review",
                "requires_authority",
            ):
                assert key in proposal, f"proposal missing {key}"
            # Every proposal must be review-gated: the agent changes nothing.
            assert proposal["requires_review"] is True
            assert proposal["requires_authority"] is True
            assert proposal["title"].strip()
            assert 0.0 <= proposal["priority"] <= 1.0


def test_backlog_proposals_reference_a_real_signal() -> None:
    """Evidence-backed: each proposal points at a signal in the same record."""
    for line in BACKLOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        signal_ids = {s["signal_id"] for s in record["signals"]}
        for proposal in record["proposals"]:
            assert proposal["source_signal_id"] in signal_ids, (
                f"{proposal['proposal_id']} points at a signal that is not in the record"
            )


def test_evolution_topics_loads_the_committed_backlog(monkeypatch) -> None:
    """The real workflow path: the committed file drives the focus rotation."""
    module = _load()
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(BACKLOG))
    topics = module.evolution_topics()
    assert topics, "the harness must read focuses from the committed backlog"

    committed = json.loads(BACKLOG.read_text(encoding="utf-8").splitlines()[0])
    titles = {p["title"] for p in committed["proposals"]}
    assert set(topics) <= titles, "evolution_topics returned a title not in the backlog"


def test_choose_topic_prefers_the_backlog_over_the_static_rotation(monkeypatch) -> None:
    """An evidence-backed focus must win over a generic rotation entry."""
    module = _load()
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(BACKLOG))
    topics = module.evolution_topics()
    assert topics
    # The best proposal (highest priority) must be chosen first.
    assert module.choose_topic(0, set()) == topics[0]
    # A taken slug is skipped in favour of the next real one.
    taken = {module._slug(topics[0])}
    assert module.choose_topic(0, taken) == topics[1]


def test_choose_topic_falls_back_when_the_backlog_is_absent(monkeypatch) -> None:
    """The backlog is an optimisation, never a dependency."""
    module = _load()
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", "/nonexistent/backlog.jsonl")
    assert module.evolution_topics() == []
    assert module.choose_topic(0, set()) in module.TOPICS


def test_evolution_backlog_generator_is_reproducible() -> None:
    """The committed snapshot must not churn: random ids would rewrite it."""
    gen = ROOT / "scripts" / "generate_evolution_backlog.py"
    assert gen.is_file()
    outs = []
    for _ in range(2):
        out = ROOT / "genesis_v5" / "data" / "evolution" / "_repro_check.jsonl"
        proc = subprocess.run(
            [sys.executable, str(gen), "--out", str(out)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        outs.append(out.read_bytes())
        out.unlink()
    assert outs[0] == outs[1], "the generator must be deterministic"
