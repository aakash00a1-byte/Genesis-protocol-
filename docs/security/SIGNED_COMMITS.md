# Signed commits — persistent SSH signing that survives a recreated sandbox

**Status:** implemented, tested, **not activated**. Activation is owner-side and
requires one secret, one environment and one workflow run.

The default branch requires a verified signature on every commit (ruleset
`Gen`: `required_signatures`, `bypass_actors: []`,
`current_user_can_bypass: never`). That rule is correct and stays untouched.
What broke was the *supply* of signatures: the private key lived only in an
ephemeral `~/.ssh/genesis_signing` inside an agent sandbox. The sandbox was
recycled, the key vanished, the next commit was unsigned, and PR #91 could not
merge.

This document is the permanent fix, and an honest account of what it does and
does not protect.

---

## 1. Architecture

```
owner's machine                       GitHub                          runner (ephemeral)
────────────────                      ──────                          ──────────────────
ssh-keygen -t ed25519
  ├─ public  ──► Settings → SSH keys → type "Signing Key"
  └─ private ──► Environment "signing" secret SSH_SIGNING_KEY
                 (required reviewer: owner)
                        │
                        │  Actions → Sign Branch → Run workflow
                        ▼
                 environment approval prompt  ──────────────────►  write key to $RUNNER_TEMP (0600)
                                                                   git commit -S  (ssh format)
                                                                   push --force-with-lease
                                                                   verify via GitHub API
                                                                   rm -f key  (always)
                                                                   dispatch ci.yml
```

Three properties carry the design:

1. **The key is never in the repository, a log, a chat or a sandbox.**
   GitHub does not return a secret's value after it is set. The agent's token
   cannot read it (`GET /actions/secrets` → **403**, verified), so no agent
   session can ever see it.
2. **The key cannot push.** It is registered as a *signing* key, not an
   authentication key. Even a leaked copy can only sign commits; landing them
   still needs a token and the merge gate.
3. **Nothing depends on local state.** The runner is destroyed after every run
   and re-created from the secret. A new sandbox, a new container, a new month —
   the same command works.

### Why an environment secret and not a repository secret

A repository secret is readable by **any** workflow in the repository, including
one pushed on a feature branch by anyone who can push. An environment secret is
readable only by a job that declares `environment: signing`, and with a
**required reviewer** that job blocks until the owner approves. The approval
prompt is the control: the owner sees which workflow, on which branch, is asking
for the key — and can refuse.

Defence in depth in the workflow itself: it runs only on `workflow_dispatch`,
refuses a workflow definition that is not the default-branch copy
(`github.workflow_ref` must be `…/sign-branch.yml@refs/heads/main`), and refuses
the default branch before anything is checked out.

## 2. Feasibility audit of the options (all free)

| Option | Free? | Survives a fresh sandbox? | Key exposure | Verdict |
|---|---|---|---|---|
| **Environment secret + dispatch workflow** | yes (public repo: unlimited Actions minutes) | **yes** | key materialised only on a disposable runner, owner-approved | **chosen** |
| Repository secret + workflow | yes | yes | readable by any workflow in the repo | weaker; use only if approvals are impossible |
| Local `~/.ssh` key (today's state) | yes | **no** — this is the failure | key dies with the sandbox | rejected |
| GitHub App / bot identity | yes | yes | needs app private key + attribution work | heavier, no benefit here |
| GitHub's own squash-merge signature | yes | n/a | none | **viable second path** — see below; not relied on because it cannot sign *our* history, only what GitHub creates |
| Ruleset change (drop `required_signatures`) | yes | n/a | none | **rejected**: the rule is worth keeping |

**A verified second path, for the record.** `main`'s current tip `09dfa791` is
`verified: true, reason: valid, committer: GitHub` — GitHub web-flow signed the
squash merge of PR #90, whose head commit was itself unsigned. So "Squash and
merge" in the web UI produces a verified commit on `main`. What is *not* proven
is whether the `required_signatures` rule lets the button be pressed for an
unsigned head (the rule was updated after #90 merged). It is one click to find
out, and it is free; the workflow path below is the deterministic one.

Verified facts behind the table (2026-11-24, read-only probes):

- repository `visibility: public` → Actions minutes are not billed, so the
  signing workflow costs nothing;
- `GET /repos/…/actions/secrets` → **403** for the agent token → secrets are
  owner-only, by construction;
- `GET /user/ssh_signing_keys` → **403** → the agent cannot register, list or
  rotate the owner's signing keys;
- environments present: `Genesis`, `github-pages`, `production`, two generated
  names — **no `signing` environment yet**, which is step 4 below;
- this sandbox has **no `ssh-keygen`** and **no** `~/.ssh/genesis_signing`, so
  `readiness()` correctly reports `can_sign_locally: false`.

## 3. Owner-side steps (exact)

Run these once. Nothing here needs the agent.

**1. Generate the key on your own machine**

```bash
ssh-keygen -t ed25519 -C "genesis-signing" -f ~/.ssh/genesis_signing -N ""
```

**2. Read the fingerprint**

```bash
ssh-keygen -lf ~/.ssh/genesis_signing.pub
# equivalently, with no OpenSSH needed:
python3 scripts/verify_signed_commits.py fingerprint ~/.ssh/genesis_signing.pub
```

Both print the same `SHA256:…` value. That is the value GitHub will show next.

**3. Register the PUBLIC half as a signing key**

GitHub → **Settings → SSH and GPG keys → New SSH key**:

- Title: `genesis-signing`
- Key type: **Signing Key** ← not "Authentication Key"; a signing key cannot push
- Key: paste the contents of `~/.ssh/genesis_signing.pub`

Confirm the fingerprint GitHub displays equals step 2. If it does not, stop:
the wrong key is registered and every signature will read `unverified`.

**4. Create the protected environment**

Repository → **Settings → Environments → New environment** → name it exactly
`signing` → **Required reviewers** → add yourself → Save.

This is the step that makes a branch-pushed workflow unable to read the key
without your explicit approval. Do not skip it.

**5. Store the PRIVATE half as an environment secret**

Environments → `signing` → **Add secret** → name exactly `SSH_SIGNING_KEY` →
value: the full contents of `~/.ssh/genesis_signing` (including the BEGIN/END
lines) → Add.

Never paste this into a chat, an issue, a PR body or a file in the repository.

**6. Run the signing workflow**

Actions → **Sign Branch** → *Run workflow*:

- branch: `feat/signed-commit-architecture`
- mode: `squash-sign`

Approve the environment prompt when it appears.

**7. Verify, from anywhere**

```bash
python3 scripts/verify_signed_commits.py verify \
  --repo aakash00a1-byte/Genesis-protocol- \
  --branch feat/signed-commit-architecture
```

Expect `RESULT: OK - 1 commit(s) verified`. The workflow prints the same result
as its second-to-last step, and the PR's head shows a **Verified** badge.

## 4. What "squash-sign" does to the branch

The ruleset wants signed commits **and** linear history. The branch carries one
unsigned commit, so it is rewritten on the branch (never on `main`):

```bash
git log -1 --format='%B' > "$COMMIT_MESSAGE_FILE"      # read before the reset
ORIGINAL_AUTHOR="$(git log -1 --format='%an <%ae>')"
git fetch origin main
git reset --soft origin/main
git commit -S -F "$COMMIT_MESSAGE_FILE" --author="$ORIGINAL_AUTHOR"
git push --force-with-lease origin HEAD:<branch>
```

The message and author are captured **before** the reset — `reset --soft` moves
the branch pointer, so reading them afterwards would read `main`'s commit.
`--force-with-lease` refuses if someone else pushed meanwhile.
`scripts/verify_signed_commits.py plan` prints exactly these commands as data;
nothing executes them.

After the push the workflow dispatches `ci.yml` on the branch, because a push
made with `GITHUB_TOKEN` does not trigger its own workflows — without that, the
new head would have no `lint`/`test` checks and the required-check rule would
block instead.

## 5. Automated checks

- `scripts/verify_signed_commits.py verify` reads GitHub's own verdict per
  commit (the same source the merge gate uses) and exits **1** if any commit is
  unsigned, **2** if the verdict could not be read. It never treats "unknown" as
  "signed".
- `Sign Branch` runs that check on the head it just pushed and fails if the
  signature did not land.
- `Verify Signatures` (manual + weekly cron) reports the state of `main` or any
  branch. Read-only: `contents: read`, no signing, no merge, no push.
- `tests/test_commit_signing.py` (35 tests) pins the fingerprint maths against a
  published key, the branch/ref guards, the plan ordering, and fail-closed
  verification.

## 6. Test design for recreated sessions and fresh containers

| Test | How | Expected |
|---|---|---|
| Fresh container, no key | `python3 scripts/verify_signed_commits.py readiness` | `can_sign_locally: false`, `can_sign_in_ci: true` — it says so instead of failing late |
| Verification needs no local key | run `Verify Signatures` on `main` | `RESULT: OK` — the API holds the verdict, not the sandbox |
| Signature is real, not claimed | `verify --branch <branch>` after signing | `verified: true` from GitHub, independent of the runner |
| Re-run after the sandbox is recycled | delete the sandbox, redo steps 6–7 | same result; nothing depended on local state |
| Adversarial: modified workflow on a branch | push a `sign-branch.yml` that echoes the secret, dispatch it from that branch | run stops at the environment approval; the owner denies; no key in logs |
| Adversarial: wrong key registered | register a different public key | `verify` reports `unverified` and the workflow fails — no silent pass |
| Adversarial: verdict unreadable | block the API | exit 2, "unreadable", never "ok" |

## 7. Rotation, revocation, compromise

- **Rotate (routine):** generate a new key, register it as a signing key, replace
  `SSH_SIGNING_KEY` in the `signing` environment, run `Sign Branch` again, then
  delete the old key from Settings.
- **Revoke (compromise):** delete the key in Settings **first** — every commit it
  signed after that point reads `unverified` — then rotate the secret and audit:
  `git log --show-signature main` and the API verdicts for anything landed while
  the key was live.
- **Lost owner access:** the key is useless without the environment secret and
  the environment approval; the ruleset blocks merges until a new key is set up.
  That is the rule working, not a bug.

## 8. What this does **not** protect against

- **A collaborator with write access and environment-approval rights.** They
  could push a workflow and approve it themselves. Keep the reviewer list to the
  owner and do not grant write to anyone you would not trust with a signing key.
- **A compromised owner account.** Environment secrets are only as strong as the
  account that can approve them.
- **Bad code.** A signature proves *who* committed, not that the change is
  correct. The merge gate's evidence record, the tests and the review still
  decide that.
- **A key that stays unregistered.** If the public half is added as an
  *authentication* key instead of a *signing* key, GitHub reports
  `unverified` for every commit. Step 3 is not optional.

## 9. Honest status of PR #91

PR #91's head commit `39364982` is unsigned. A signature is part of the commit
object, so it cannot be added without rewriting that commit. The only two ways
out are:

1. rewrite the branch with a signed commit (**force-push on the branch** — what
   `Sign Branch` does, owner-triggered),
2. let GitHub sign it for you: **Squash and merge** in the web UI creates a
   single commit signed by `GitHub` (verified on `main`'s tip), if the rule
   permits the button — one click, no key needed, but it discards the branch's
   individual commits, or
3. change the ruleset (`required_signatures` off), which is explicitly not done
   here.

This branch (`feat/signed-commit-architecture`) is based on `39364982`, so it
contains every change from #91 plus this work. After `Sign Branch` runs on it,
the branch is a single signed commit on top of `main` and can be merged. PR #91
should then be closed as superseded — its content is not lost, and its branch is
left exactly as it is.

Nothing in this document was bypassed, disabled or force-pushed by the agent.
