"""Hardening tests for the approval gate, the KDF and the parser rewrites.

These pin the findings of the independent review of PR #87:

* the gate read only the first page of a PR's commits, so commit 101 onward was
  never signature-checked;
* ``require_checks=False`` (reachable through ``SELF_IMPROVE_REQUIRE_CHECKS=0``)
  switched off CI, evidence *and* signature verification at once;
* the key derivation needed to move to 600,000 iterations, which strands older
  ciphertext unless there is a migration path;
* two hand-rolled parsers changed behaviour for hyphenated ids and for prose
  between numbered list items.

Every test here drives real code. No network: the transports get a fake HTTP
callable, exactly as the production transport does.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HEAD = "a" * 40
MID = "b" * 40


# ------------------------------------------------------------------
# fakes
# ------------------------------------------------------------------
def _green_checks() -> dict:
    return {
        "check_runs": [
            {"name": "lint", "conclusion": "success"},
            {"name": "test", "conclusion": "success"},
        ]
    }


class FakeGitHub:
    """A paged commits endpoint plus per-commit verdicts."""

    def __init__(self, pages, verdicts=None, checks=None):
        self.pages = list(pages)
        self.verdicts = verdicts or {}
        self.checks = checks if checks is not None else _green_checks()
        self.calls: list[str] = []

    def __call__(self, method, url, payload):
        self.calls.append(url)
        if method != "GET":
            return {"merged": True, "sha": "deadbeef"}
        if "/pulls/7/commits" in url:
            page = int(url.rsplit("page=", 1)[-1]) if "page=" in url else 1
            if isinstance(self.pages, Exception):
                raise self.pages
            if page > len(self.pages):
                return []
            return self.pages[page - 1]
        if url.endswith("/check-runs"):
            return self.checks
        if "/commits/" in url:
            sha = url.rsplit("/", 1)[-1]
            return self.verdicts.get(sha, {"commit": {"verification": {"verified": True, "reason": "valid"}}})
        return {}

    def commit_requests(self) -> list[str]:
        return [u for u in self.calls if "/pulls/7/commits" in u]


def _item(sha=HEAD):
    from genesis_protocol.updates import Update

    return Update(id="7", title="t", head_sha=sha, body=f"landed commit: `{sha}`")


def _transport(http, **kwargs):
    from genesis_protocol.updates.github_prs import GitHubPRTransport

    return GitHubPRTransport("o/r", "tok", http=http, **kwargs)


def _shas(n: int, start: int = 0) -> list[dict]:
    return [{"sha": f"{i:040x}"} for i in range(start, start + n)]


# ------------------------------------------------------------------
# F1: complete pagination
# ------------------------------------------------------------------
def test_reads_every_page_of_commits() -> None:
    http = FakeGitHub([_shas(100, 0), _shas(100, 100), _shas(1, 200)])
    shas, why = _transport(http)._commit_shas("7")
    assert why == ""
    assert shas is not None and len(shas) == 201
    assert len(http.commit_requests()) == 3
    assert "page=1" in http.commit_requests()[0]
    assert "page=3" in http.commit_requests()[2]


def test_exactly_one_full_page_still_asks_for_the_next_one() -> None:
    http = FakeGitHub([_shas(100, 0), []])
    shas, why = _transport(http)._commit_shas("7")
    assert shas is not None and len(shas) == 100
    assert len(http.commit_requests()) == 2, "a full page is not proof that the list ended"


def test_gate_checks_commit_101() -> None:
    """The regression: commit 101 was invisible to a single-page implementation."""
    unsigned = f"{100:040x}"
    pages = [_shas(100, 0), _shas(1, 100)]
    http = FakeGitHub(pages, verdicts={unsigned: {"commit": {"verification": {"verified": False, "reason": "unsigned"}}}})
    blockers = _transport(http)._merge_blockers(_item())
    assert any("not signed" in b for b in blockers), blockers


def test_gate_accepts_101_signed_commits() -> None:
    http = FakeGitHub([_shas(100, 0), _shas(1, 100)])
    assert _transport(http)._merge_blockers(_item()) == []


def test_gate_checks_an_unsigned_commit_buried_on_page_three() -> None:
    buried = f"{250:040x}"
    http = FakeGitHub(
        [_shas(100, 0), _shas(100, 100), _shas(51, 200)],
        verdicts={buried: {"commit": {"verification": {"verified": False, "reason": "unsigned"}}}},
    )
    blockers = _transport(http)._merge_blockers(_item())
    assert any(buried[:12] in b for b in blockers), blockers


def test_unreadable_second_page_fails_closed() -> None:
    calls = {"n": 0}

    def http(method, url, payload):
        if "/pulls/7/commits" in url:
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("HTTP 502")
            return _shas(100, 0)
        if url.endswith("/check-runs"):
            return _green_checks()
        return {"commit": {"verification": {"verified": True, "reason": "valid"}}}

    blockers = _transport(http)._merge_blockers(_item())
    assert any("could not be read" in b and "page 2" in b for b in blockers), blockers


def test_malformed_commit_entry_fails_closed() -> None:
    http = FakeGitHub([[{"sha": HEAD}, {"nope": 1}]])
    shas, why = _transport(http)._commit_shas("7")
    assert shas is None and "without a sha" in why


def test_empty_sha_string_fails_closed() -> None:
    http = FakeGitHub([[{"sha": "   "}]])
    shas, why = _transport(http)._commit_shas("7")
    assert shas is None and "without a sha" in why


def test_non_list_page_fails_closed() -> None:
    http = FakeGitHub([{"message": "Not Found"}])
    shas, why = _transport(http)._commit_shas("7")
    assert shas is None and "not a commit list" in why


def test_page_cap_refuses_a_truncated_list(monkeypatch) -> None:
    from genesis_protocol.updates.github_prs import GitHubPRTransport

    monkeypatch.setattr(GitHubPRTransport, "_COMMITS_MAX_PAGES", 2)
    http = FakeGitHub([_shas(100, 0), _shas(100, 100), _shas(100, 200)])
    shas, why = _transport(http)._commit_shas("7")
    assert shas is None and "refusing a truncated list" in why
    assert len(http.commit_requests()) == 2


def test_empty_first_page_is_reported_as_no_commits() -> None:
    http = FakeGitHub([[]])
    blockers = _transport(http)._merge_blockers(_item())
    assert any("no commits" in b for b in blockers), blockers


# ------------------------------------------------------------------
# F3: the gate cannot be switched off by configuration
# ------------------------------------------------------------------
def test_gate_cannot_be_disabled_by_a_constructor_flag() -> None:
    with pytest.raises(ValueError, match="cannot be disabled"):
        _transport(FakeGitHub([[]]), require_checks=False)


def test_test_hook_allows_the_opt_out_for_isolated_tests() -> None:
    transport = _transport(FakeGitHub([[]]), require_checks=False, allow_unverified=True)
    assert transport.require_checks is False
    assert transport._merge_blockers(_item()) == []


def test_environment_variable_cannot_disable_the_production_gate(monkeypatch) -> None:
    monkeypatch.setenv("SELF_IMPROVE_REQUIRE_CHECKS", "0")
    monkeypatch.setenv("GH_MERGE_TOKEN", "tok")
    spec = importlib.util.spec_from_file_location("self_improve_bypass", ROOT / "scripts" / "self_improve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    transport = module._transport()
    assert transport is not None
    assert transport.require_checks is True
    assert transport.require_signatures is True


def test_no_environment_variable_is_read_for_the_gate() -> None:
    source = (ROOT / "scripts" / "self_improve.py").read_text()
    assert "SELF_IMPROVE_REQUIRE_CHECKS" not in source


# ------------------------------------------------------------------
# F2: KDF iterations and the migration path
# ------------------------------------------------------------------
def test_kdf_uses_600k_iterations() -> None:
    import hashlib

    from genesis_protocol.security.encryption import EncryptionService

    assert EncryptionService._KDF_ITERATIONS == 600_000
    service = EncryptionService(key="pw")
    expected = hashlib.pbkdf2_hmac(
        "sha256", b"pw", service._KDF_SALT_CONTEXT, 600_000, dklen=32
    )
    assert service._key == expected


def test_legacy_ciphertext_raises_an_actionable_error() -> None:
    from genesis_protocol.security.encryption import (
        EncryptionService,
        LegacyCiphertextError,
        encrypt_with_raw_key,
    )

    legacy = encrypt_with_raw_key("old backup", bytes(range(32)))
    with pytest.raises(LegacyCiphertextError) as exc:
        EncryptionService(key="pw").decrypt(legacy)
    message = str(exc.value)
    assert "migrate_backup_vault.py" in message
    assert "wrong" in message  # names the other cause too


def test_raw_key_helpers_round_trip() -> None:
    from genesis_protocol.security.encryption import (
        decrypt_with_raw_key,
        encrypt_with_raw_key,
    )

    key = bytes(range(32))
    assert decrypt_with_raw_key(encrypt_with_raw_key("x", key), key) == "x"
    with pytest.raises(ValueError):
        encrypt_with_raw_key("x", b"short")


def _legacy_sealer(key: bytes):
    from genesis_protocol.security.encryption import decrypt_with_raw_key, encrypt_with_raw_key

    class Sealer:
        def encrypt(self, data: str) -> str:
            return encrypt_with_raw_key(data, key)

        def decrypt(self, data: str) -> str:
            return decrypt_with_raw_key(data, key)

    return Sealer()


def test_vault_migration_reencrypts_and_restores(tmp_path) -> None:
    from genesis_protocol.recovery.vault import BackupVault

    legacy_key = bytes(range(32))
    vault = BackupVault(root=str(tmp_path), key="new-password")
    vault._encryption = _legacy_sealer(legacy_key)
    created = vault.create({"a.txt": b"legacy payload"})
    bid = created["backup_id"]

    current = BackupVault(root=str(tmp_path), key="new-password")
    assert current.verify(bid).ok is False
    assert "LegacyCiphertextError" in current.verify(bid).detail

    report = current.migrate_container(bid, legacy_key)
    assert report["migrated"] is True
    assert report["entries"] == 1
    assert current.verify(bid).ok is True

    dest = tmp_path / "restored"
    result = current.restore(bid, str(dest))
    assert result["ok"] is True
    assert (dest / "a.txt").read_bytes() == b"legacy payload"
    assert (tmp_path / f"{bid}.gbk.pre-migration").is_file()


def test_vault_migration_refuses_the_wrong_legacy_key(tmp_path) -> None:
    from genesis_protocol.recovery.vault import BackupError, BackupVault

    vault = BackupVault(root=str(tmp_path), key="new-password")
    vault._encryption = _legacy_sealer(bytes(range(32)))
    bid = vault.create({"a.txt": b"payload"})["backup_id"]
    before = (tmp_path / f"{bid}.gbk").read_bytes()

    with pytest.raises(BackupError, match="not sealed with the supplied legacy key"):
        vault.migrate_container(bid, bytes(reversed(range(32))))
    assert (tmp_path / f"{bid}.gbk").read_bytes() == before, "a failed migration must not touch the file"
    assert not (tmp_path / f"{bid}.gbk.pre-migration").exists()


def test_vault_migration_can_drop_the_original(tmp_path) -> None:
    from genesis_protocol.recovery.vault import BackupVault

    legacy_key = bytes(range(32))
    vault = BackupVault(root=str(tmp_path), key="new-password")
    vault._encryption = _legacy_sealer(legacy_key)
    bid = vault.create({"a.txt": b"x"})["backup_id"]

    report = vault.migrate_container(bid, legacy_key, keep_original=False)
    assert report["original_kept"] is False
    assert not (tmp_path / f"{bid}.gbk.pre-migration").exists()
    assert vault.verify(bid).ok is True


def test_corrupt_container_reports_a_backup_error(tmp_path) -> None:
    from genesis_protocol.recovery.vault import BackupVault

    vault = BackupVault(root=str(tmp_path), key="pw")
    bid = vault.create({"a.txt": b"x"})["backup_id"]
    (tmp_path / f"{bid}.gbk").write_bytes(b"\xff\xfe\x00binary garbage")

    result = vault.verify(bid)
    assert result.ok is False
    assert "corrupt" in result.detail
    assert "UnicodeDecodeError" not in result.detail


def test_migration_cli_dry_run_then_apply(tmp_path, capsys) -> None:
    spec = importlib.util.spec_from_file_location(
        "migrate_backup_vault", ROOT / "scripts" / "migrate_backup_vault.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    from genesis_protocol.recovery.vault import BackupVault

    legacy_key = bytes(range(32))
    vault = BackupVault(root=str(tmp_path), key="new-password")
    vault._encryption = _legacy_sealer(legacy_key)
    bid = vault.create({"a.txt": b"payload"})["backup_id"]

    args = ["--vault-dir", str(tmp_path), "--new-key", "new-password",
            "--legacy-key-hex", legacy_key.hex()]
    assert cli.main(args) == 0
    assert "dry run" in capsys.readouterr().out
    assert BackupVault(root=str(tmp_path), key="new-password").verify(bid).ok is False

    assert cli.main(args + ["--apply"]) == 0
    assert "migrated + verified" in capsys.readouterr().out
    assert BackupVault(root=str(tmp_path), key="new-password").verify(bid).ok is True

    # idempotent: a second apply finds nothing to do
    assert cli.main(args + ["--apply"]) == 0
    assert "nothing to migrate" in capsys.readouterr().out


def test_migration_cli_rejects_a_bad_legacy_key(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location(
        "migrate_backup_vault_bad", ROOT / "scripts" / "migrate_backup_vault.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--vault-dir", str(tmp_path), "--new-key", "pw", "--legacy-key-hex", "zz"]) == 2
    assert cli.main(["--vault-dir", str(tmp_path), "--new-key", "pw",
                     "--legacy-key-hex", "00" * 31]) == 2


# ------------------------------------------------------------------
# F4: dependency markers with hyphens (pre-refactor behaviour)
# ------------------------------------------------------------------
@pytest.mark.parametrize(
    "clause,expected",
    [
        ("after: t1 - build it", (["t1"], "build it")),
        ("after: t1, t2 - build it", (["t1", "t2"], "build it")),
        ("after: task-1 - build it", (["task-1"], "build it")),
        ("after: a-b, c: build it", (["a-b", "c"], "build it")),
        ("AFTER: t1 - case insensitive", (["t1"], "case insensitive")),
        ("after: t1", None),
        ("build it", None),
        ("after: - build it", None),
    ],
)
def test_after_marker_matches_the_pre_refactor_semantics(clause, expected) -> None:
    from genesis_protocol.mission.planner import _after_marker

    assert _after_marker(clause) == expected


def test_decompose_keeps_hyphenated_dependencies() -> None:
    from genesis_protocol.mission.planner import decompose

    tasks = decompose("first; after: task-1 - second")
    assert tasks[1]["depends_on"] == ["task-1"]


# ------------------------------------------------------------------
# F5: numbered-list parsing (pre-refactor behaviour)
# ------------------------------------------------------------------
@pytest.mark.parametrize(
    "line,expected",
    [
        ("1. body", "body"),
        ("2) body", "body"),
        ("1234. body", "body"),
        ("1.body", ""),
        ("no marker", ""),
        ("1.", ""),
    ],
)
def test_strip_list_marker(line, expected) -> None:
    from genesis_protocol.agentic.reasoning import _strip_list_marker

    assert _strip_list_marker(line) == expected


def test_prose_after_list_items_stays_with_the_item_above() -> None:
    from genesis_protocol.agentic.reasoning import StructuredReasoning

    items = StructuredReasoning._split_subproblems("1. first\n2. second\ntrailing note")
    assert items == ["first", "second trailing note"]


def test_four_digit_list_numbers_still_split() -> None:
    from genesis_protocol.agentic.reasoning import StructuredReasoning

    items = StructuredReasoning._split_subproblems("1234. first\n1235. second")
    assert items == ["first", "second"]


# ------------------------------------------------------------------
# F7: the refusal message no longer contradicts itself
# ------------------------------------------------------------------
def test_non_boolean_verdict_is_described_honestly() -> None:
    from genesis_protocol.evolution.signed_commit import read_signature

    def http(method, url, payload):
        return {"commit": {"verification": {"verified": "true", "reason": "valid"}}}

    verdict = read_signature("o/r", HEAD, http)
    assert verdict.verified is False
    refusal = verdict.refusal()
    assert "not a boolean true" in refusal
    assert "reason: valid" not in refusal


def test_boolean_true_is_accepted() -> None:
    from genesis_protocol.evolution.signed_commit import read_signature

    def http(method, url, payload):
        return {"commit": {"verification": {"verified": True, "reason": "valid"}}}

    assert read_signature("o/r", HEAD, http).refusal() is None


def test_false_verdict_keeps_github_reason() -> None:
    from genesis_protocol.evolution.signed_commit import read_signature

    def http(method, url, payload):
        return {"commit": {"verification": {"verified": False, "reason": "unverified_email"}}}

    refusal = read_signature("o/r", HEAD, http).refusal()
    assert "unverified_email" in refusal
