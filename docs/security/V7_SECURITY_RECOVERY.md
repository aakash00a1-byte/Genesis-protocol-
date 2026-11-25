# V7 security recovery — analysis, fixes and rollback

Baseline: `main` at `676a1dd674669d4ef2c570bb2c03f54c13545b1d`.
Scope: the ten items of the V7 security recovery work order. Nothing here
changes a ruleset, a secret, a key, `main`, or a deployment; the changes in this
PR are code, tests and documentation only.

Everything below separates **verified** facts (an API response, a doc quote, a
test run) from **recommendations** that need the owner's approval.

---

## 1. Direct fast-forward pushes to `main` (item 2)

### What the rules actually do

From GitHub's own ruleset reference
(`docs.github.com/.../managing-rulesets/available-rules-for-rulesets`):

> **Restrict updates** — "If selected, only users with bypass permissions can
> push to branches or tags whose name matches the pattern you specify."

> **Require a pull request before merging** — "You can require that all changes
> to the target branch be associated with a pull request. The pull request
> doesn't necessarily have to be approved, but it must be opened."

A merge is a push performed by the merging user, so with `update` enabled and
`bypass_actors: []` **nobody can merge anything** — which is exactly the
`mergeable_state: blocked` observed on PR #86. `pull_request` alone is the
PR-compatible rule: it rejects direct pushes and permits a merge that goes
through a pull request.

### Conclusion

The configuration already in force on `main` (ruleset `Gen`, id `26347102`) is
the proposed protection:

| Rule | Present | Effect on a direct FF push to `main` |
| --- | --- | --- |
| `pull_request` | yes | **rejects** it (changes must come via a PR) |
| `required_signatures` | yes | unsigned commit rejected |
| `required_status_checks` (lint, test, strict) | yes | green checks required |
| `required_linear_history` | yes | no merge commits |
| `non_fast_forward` | yes | force-push rejected |
| `deletion` | yes | branch deletion rejected |
| `creation` | yes | branch creation rejected |
| `code_scanning` | yes | CodeQL gate |
| `update` | **no** | would reject *every* push, including merges — this is the rule that broke PR #86 and it must not be restored |
| `bypass_actors` | `[]` | nobody can bypass |

**No ruleset change is required.** The earlier report that "direct push is now
possible" was wrong: it inferred behaviour from the rule list instead of the
documented semantics. The `pull_request` rule is what blocks the direct push.

### Empirical test (needs owner approval to run)

`scripts/probe_pr_only_ruleset.py` tests the configuration on disposable
branches (`refs/heads/probe-*`) and removes everything afterwards:

1. create `probe-base` from `main` **before** the ruleset exists;
2. create a temporary ruleset scoped to `refs/heads/probe-*` with only the
   `pull_request` rule and no bypass actors;
3. push a commit directly to `probe-base` → expected **rejected**;
4. open `probe-pr` → `probe-base` and merge → expected **accepted**;
5. delete the PR, both branches and the ruleset.

Dry run (safe, no writes) is the default:

```bash
python3 scripts/probe_pr_only_ruleset.py --repo aakash00a1-byte/Genesis-protocol-
```

The apply path creates and deletes a ruleset, so it is **not** run as part of
this PR — it waits for explicit owner approval:

```bash
AGENT_GH_TOKEN=... python3 scripts/probe_pr_only_ruleset.py \
  --repo aakash00a1-byte/Genesis-protocol- --apply
```

---

## 2. Signature gate inside the merge path (item 3)

`genesis_protocol/updates/github_prs.py` merged a head when its check-runs were
green and the PR body carried an evidence record. It never asked whether the
commits were signed, so relaxing `required_signatures` would have gone unnoticed.

`signature_blockers()` (from `genesis_protocol/evolution/signed_commit.py`) is now
part of `_merge_blockers()`:

* the gate lists every commit in the PR (`GET /pulls/{n}/commits`) — not just the
  head, because a squash merge lands them all;
* each commit's GitHub verification verdict must be `verified: true`;
* an unreadable commits endpoint, an empty commit list, an import failure or a
  malformed verdict is a **refusal**, never a pass;
* `require_signatures=True` by default; `require_checks=False` still short-circuits
  the whole gate, which is how the legacy tests exercise the old behaviour.

The import is deferred inside `_signature_blockers()` on purpose:
`genesis_protocol.updates` must stay importable with the standard library alone
(the self-improvement runner installs nothing), and
`genesis_protocol.evolution` pulls a large dependency graph at import time.
`tests/test_updates.py::test_leaf_import_does_not_load_the_whole_app` still holds.

Tests added (all pass):

| Test | Asserts |
| --- | --- |
| `test_transport_refuses_unsigned_commit` | `reason: unsigned` → no merge call |
| `test_transport_refuses_unverified_email_signature` | `unverified_email` → no merge call |
| `test_transport_checks_every_commit_not_just_the_head` | unsigned commit mid-branch → refused |
| `test_transport_refuses_when_commits_cannot_be_read` | 403/unreadable → refused |
| `test_transport_refuses_when_pr_reports_no_commits` | empty list → refused |
| `test_signature_check_is_explicitly_optional` | explicit opt-out still merges |

---

## 3. The 25 High CodeQL alerts (item 4)

Disposition: **fixed** in this PR, or **documented** with the reason it is not a
live vulnerability. No alert is dismissed or suppressed in the CodeQL UI.

### Fixed

| Alert(s) | Rule | Where | Fix |
| --- | --- | --- | --- |
| #98 | `py/path-injection` | `genesis_protocol/legacy/snapshot.py` | `snapshot_type` was already allowlisted; the path is now resolved and checked with `os.path.commonpath` against `storage_path` before writing |
| #99 | `py/weak-sensitive-data-hashing` | `genesis_protocol/security/encryption.py` | `sha256(password)` → `pbkdf2_hmac("sha256", …, 200_000, dklen=32)` with a fixed domain-separation salt (derivation must reproduce across restarts). **Pre-v7 ciphertext is no longer readable** — see the migration note below |
| #100 | `py/bad-tag-filter` | `genesis_protocol/utils/sanitizers.py` | removed the `<[^>]+>` filter: `html.escape()` runs first, so the regex could never match — dead code that looked like sanitization |
| #96 | `py/incomplete-url-substring-sanitization` | `genesis_protocol/integrations/key_free_search.py` | `"duckduckgo.com" in netloc` → exact host or `.duckduckgo.com` suffix |
| #95 | same | `genesis_protocol/skills/specialized/__init__.py` | `"https://github.com" in line` → `urlparse(...).hostname == "github.com"` |
| #97 | same | `tests/test_source_credibility.py` | assert on the parsed host of the rendered URL |
| #7 | `py/clear-text-logging-sensitive-data` | `genesis_protocol/security/secret_registry.py` | no longer logs the secret *name* |
| #3, #4, #5 | same | `genesis_v5/genesis/adapters/{claude,gemini,nemotron}.py` | constant message instead of the env-var name |
| #1 | `py/clear-text-storage-sensitive-data` | `scripts/autonomous_deploy.py` | writes an empty `.env` scaffold, mode 0600; never writes a key value |
| #9 | `py/polynomial-redos` | `genesis_protocol/updates/__init__.py` | the regex now matches only `^/(verb)\b`; the argument is the remaining slice |
| #19 | same | `genesis_protocol/updates/work_orders.py` | same |
| #10, #11 | same | `genesis_protocol/ai/agent.py` | `_fenced_body()` scans for the fences; no regex |
| #12 | same | `genesis_protocol/ai/autonomous_mode.py` | character loop replaces `x` between digits |
| #13 | same | `web/app.py` | `_valid_email()` — linear shape check, no regex |
| #14 | same | `genesis_protocol/mission/planner.py` | `_after_marker()` parses the prefix by hand |
| #15, #16, #17, #18 | same | `genesis_protocol/agentic/reasoning.py` | connectors replaced with a sentinel, then a linear sentence split; list markers parsed by `_strip_list_marker()` |

### Documented, not changed

| Alert | Where | Why |
| --- | --- | --- |
| #2 `py/clear-text-storage-sensitive-data` | `quarantine/genesis_protocol/deploy/genesis_deploy_agent.py` | quarantined legacy module: not importable, not packaged, not run (see `quarantine/README.md`). Fixing it would imply it is supported. |
| #6, #8 `py/clear-text-logging-sensitive-data` | `scripts/patch_verification.py`, `scripts/self_improve.py` | these print harness-owned status text. Wrapping the value in a redaction helper was tried and **did not clear the query** — CodeQL follows the value into the `print`. The only way to clear it is to stop printing, which would hide exactly the failures these scripts exist to report. Left as tracked residual, not suppressed. |

### Migration note from the encryption change

The key derivation changed, so ciphertext written by an older release cannot be
decrypted by this one. Before deploying:

1. decrypt any recovery-vault entry you need to keep, using the previous
   release (or a copy of the old `EncryptionService`), and re-encrypt it after
   the upgrade;
2. `GENESIS_BACKUP_KEY` is fail-closed, so a deployment without it never wrote
   a backup and needs no migration.

A legacy-key fallback was written first and then removed: it kept
`sha256(password)` alive in the decrypt path, which CodeQL correctly flags, and
carrying a weak KDF forever to read hypothetical ciphertext is worse than a
documented one-time migration.

---

## 4. `require_code_owner_review` and `require_extra_approval_for_unattributed_changes` (item 5)

Both were set to `false` during the earlier bisect and left that way. They are
reviewed here rather than silently kept.

**`require_code_owner_review: false` — recommended (keep).**

* The repository has **no `CODEOWNERS` file**, so the setting is currently a
  no-op.
* It becomes a deadlock the moment a `CODEOWNERS` file appears: GitHub does not
  let an author approve their own pull request, and a solo maintainer is the
  author of every change. With `bypass_actors: []` there would be no way to
  merge at all.
* Re-enable it when a second maintainer (or an approving bot) exists; the
  condition is "someone other than the author can approve".

**`require_extra_approval_for_unattributed_changes: true` — recommended (restore).**

* GitHub's docs: it applies only to Copilot pull requests "that isn't attributed
  to a person", and it "has no effect if the ruleset requires zero approvals".
* This ruleset sets `required_approving_review_count: 0`, so restoring `true`
  changes nothing today and is protective if approvals are ever raised above 0.
  Restoring the default is strictly safer than leaving it `false`.

Neither change is applied in this PR — they are ruleset edits and need owner
approval.

---

## 5. Signing-key persistence (item 6)

Current state (verified):

* key id `1364341`, title `genesis-agent-signing-2026-11-25`, `ssh-ed25519`,
  registered on the account;
* the **private** key exists only at `~/.ssh/genesis_signing` (mode 600) inside
  an ephemeral agent sandbox — **not** in the repository, not in any workflow,
  not in `.git/config`, not in `/tmp`;
* a scan of the whole history finds `OPENSSH PRIVATE KEY` only inside
  `mobile-app/node_modules/node-rsa/` docs and source (third-party format
  handling, from before `node_modules` was untracked).

Consequence: the key is **usable today but fragile**. When the sandbox is
recycled the private half is gone and key `1364341` becomes orphaned — it stays
registered, and nothing can sign with it.

Options, all requiring owner approval (this PR changes none of them):

| Option | What it means | Trade-off |
| --- | --- | --- |
| A. Delete the key | `DELETE /user/ssh_signing_keys/1364341`; signed-commit history stays but nothing can sign again | simplest; `required_signatures` then blocks every future PR until a new key is set up |
| B. Store the private key as a repository secret and write it to `~/.ssh` in the workflow | signing survives sandbox churn | a private key in CI secrets; needs rotation discipline and a `permissions` review |
| C. Sign with a GitHub App / `github-actions[bot]` identity | no long-lived key on a workstation | more setup; bot commits need attribution checks |
| D. Keep the current ephemeral key | nothing to do | breaks silently the first time the sandbox is recreated |

Recommendation: **B** if signed commits from the agent are required, otherwise
**A** plus dropping `required_signatures`. Doing nothing (D) is the one option
that fails without warning.

---

## 6. Verification evidence (item 7)

| Check | Command | Result |
| --- | --- | --- |
| Full suite (both `tests/` and `genesis_v5/tests/`) | `python3 -m pytest -q` | **2176 passed**, 0 failed (re-run after the non-regex rewrites) |
| CI lint gate | `flake8 genesis_protocol --count --select=E9,F63,F7,F82` | **0** |
| Signature gate tests | `pytest tests/test_updates.py tests/test_signed_commit.py` | 57 passed |
| Security/encryption tests | `pytest tests/test_security.py` | 32 passed |
| Legacy ciphertext still readable | manual round-trip with a pre-v2 key | decrypts |
| Syntax | `py_compile` on every changed script and `web/app.py` | compiles |

Adversarial cases covered by the new tests: unsigned head, unverified email
signature, unsigned commit buried mid-branch, unreadable commit list, empty
commit list, explicit opt-out.

---

## 7. Remaining risks

1. **The gate runs only where `/approve` runs.** A human merging through the
   GitHub UI bypasses `_merge_blockers()` entirely; `required_signatures` and
   `required_status_checks` are the only controls there.
2. **`require_checks=False` disables the whole gate**, signatures included. It
   exists for tests; a production caller that sets it would merge anything.
3. **The ruleset is the real boundary, and it is one setting away from being
   useless.** Re-adding `update` blocks all merges; clearing `pull_request`
   allows direct pushes. The probe script is the guard against both.
4. **Three High alerts remain** by design: #2 (quarantined code), #6 and #8 (the scripts' own status logging).
5. **The signing key is ephemeral** (section 5) — the most likely silent failure.
6. **`scripts/autonomous_deploy.py` changed behaviour**: it no longer writes key
   values. Anyone relying on it to pre-fill a `.env` must now set secrets in the
   platform instead. That is deliberate, but it is a behaviour change.
7. **This is not a 100% security claim.** These are targeted fixes with tests;
   the repository still has 75 Medium and 100 total open CodeQL alerts that were
   not reviewed here.

---

## 8. Rollback

Every change is a normal revert; nothing is irreversible and no data format
changed irreversibly.

```bash
# revert the whole PR
git revert --no-edit <squash-merge-sha>
git push origin main          # via PR, not directly

# or revert one area
git revert --no-edit <sha> -- genesis_protocol/updates/github_prs.py
```

Per-area notes:

* **Signature gate** — remove the `require_signatures` handling and the
  `_commit_shas`/`_signature_blockers` methods; the previous gate is the code
  below the `if self.require_signatures:` block. Reverting the tests restores the
  old fakes.
* **Encryption KDF** — revert restores single-SHA-256 derivation. Ciphertext
  written by this PR is PBKDF2-keyed and would then be unreadable; decrypt it
  first if you intend to roll back.
* **`autonomous_deploy.py`** — reverting restores writing key values into
  `.env`; do that only if you accept the credential-on-disk exposure.
* **Probe script** — additive; delete the file. If a probe run was interrupted,
  clean up with `DELETE /repos/{repo}/rulesets/{id}` and the `probe-*` branches.

If a probe run leaves a ruleset behind, it is named `pr-only-probe` and scoped to
`refs/heads/probe-*`, so it cannot affect `main`.
