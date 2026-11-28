"""Persistent SSH commit signing — the design, as code that refuses.

The ruleset on the default branch requires a verified signature on every commit.
That is a good rule, and it broke the moment the agent sandbox was recycled: the
private key lived only in an ephemeral ``~/.ssh`` and vanished with it, so the
next commit was unsigned and the pull request could not merge.

This module is the *design* half of the fix. It never touches a private key:

* it parses a **public** key and computes the SHA-256 fingerprint, so the owner
  can prove the key registered on GitHub is the key they generated;
* it decides whether a branch may be signed at all (never the default branch);
* it decides whether the workflow is running from a trusted ref, which is the
  guard that stops a modified workflow on a feature branch from reading the
  signing secret;
* it reports what the current environment can actually do (``ssh-keygen``
  present? key present?), so a fresh container says "I cannot sign" instead of
  failing somewhere confusing;
* it emits the exact git commands as **data**, never executing them.

Signature *verification* is not reimplemented: ``evolution.signed_commit`` is the
canonical reader of GitHub's verdict and is reused here.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from genesis_protocol.evolution.signed_commit import (
    CommitSignature,
    read_signature,
    signature_blockers,
)

#: Repository secret that holds the private half. Only the owner can set it and
#: GitHub never shows the value back, which is why it is the right storage.
SIGNING_KEY_SECRET = "SSH_SIGNING_KEY"

#: A branch named like this is never signed by the automation: main moves only
#: through a reviewed pull request.
FORBIDDEN_BRANCHES = frozenset({"main", "master", "HEAD"})

#: Only work branches are signable. Keep this list narrow.
SIGNABLE_PREFIXES = ("agent/", "feat/", "fix/", "sec/", "docs/", "test/", "chore/")

SIGN_MODES = ("squash-sign", "resign")

_KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
              "ecdsa-sha2-nistp521", "sk-ssh-ed25519@openssh.com")


class SigningError(ValueError):
    """A signing precondition is not met. Always raised, never swallowed."""


class InvalidPublicKeyError(SigningError):
    """The text is not an OpenSSH public key."""


@dataclass(frozen=True)
class KeyFingerprint:
    """What the owner compares against GitHub's key page."""

    key_type: str
    blob_sha256: str
    comment: str = ""

    @property
    def fingerprint(self) -> str:
        return f"SHA256:{self.blob_sha256}"

    def to_dict(self) -> dict[str, str]:
        return {"key_type": self.key_type, "fingerprint": self.fingerprint,
                "comment": self.comment}


def fingerprint_public_key(text: str) -> KeyFingerprint:
    """Parse ``<type> <base64> [comment]`` and return its SHA-256 fingerprint.

    This is the same value ``ssh-keygen -lf`` prints and GitHub displays, so a
    mismatch is immediately visible. Only public material is accepted.
    """
    fields = (text or "").strip().split()
    if len(fields) < 2:
        raise InvalidPublicKeyError("expected '<type> <base64> [comment]'")
    key_type, encoded = fields[0], fields[1]
    if key_type not in _KEY_TYPES:
        raise InvalidPublicKeyError(f"unsupported key type: {key_type!r}")
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidPublicKeyError(f"base64 body is not decodable: {exc}") from exc
    if not blob:
        raise InvalidPublicKeyError("empty key body")
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return KeyFingerprint(key_type=key_type, blob_sha256=digest,
                          comment=" ".join(fields[2:]))


def public_keys_match(left: str, right: str) -> bool:
    """True when two public keys are the same key, ignoring comments/spacing."""
    try:
        return (fingerprint_public_key(left).fingerprint
                == fingerprint_public_key(right).fingerprint)
    except InvalidPublicKeyError:
        return False


def branch_is_signable(branch: str) -> tuple[bool, str]:
    """Whether the automation may sign ``branch``. Default branch is refused."""
    name = (branch or "").strip()
    if name.startswith("refs/heads/"):
        name = name[len("refs/heads/"):]
    if not name:
        return False, "no branch given"
    if name in FORBIDDEN_BRANCHES:
        return False, f"{name} is the default branch; it moves only through a reviewed PR"
    if not name.startswith(SIGNABLE_PREFIXES):
        return False, f"{name} is outside the signable prefixes {SIGNABLE_PREFIXES}"
    return True, "signable"


def workflow_ref_is_trusted(workflow_ref: str, repo: str) -> tuple[bool, str]:
    """The signing workflow must be the copy that lives on the default branch.

    ``workflow_dispatch`` runs the workflow *file from the selected ref*, so a
    branch could otherwise ship a modified workflow that prints the secret. The
    guard is that the running definition must be the one at ``refs/heads/main``.
    """
    ref = (workflow_ref or "").strip()
    if not ref:
        return False, "no workflow ref"
    if not ref.endswith("@refs/heads/main"):
        return False, f"workflow is not running from the default branch: {ref}"
    if repo and not ref.startswith(f"{repo}/"):
        return False, f"workflow belongs to {ref.split('/.github')[0]}, not {repo}"
    return True, "trusted"


def secret_configured(env: dict | None = None) -> bool:
    """Whether the signing secret is present. Returns a boolean, never a value.

    Deliberately separate from :func:`readiness`: a report that mixes a fact
    about a secret into data destined for a log invites that value to leak the
    day someone adds a field. Nothing in this module logs the result.
    """
    env = os.environ if env is None else env
    return bool(env.get(SIGNING_KEY_SECRET))


def readiness(env: dict | None = None, which: Callable[[str], str | None] = shutil.which,
              exists: Callable[[str], bool] = os.path.exists) -> dict[str, Any]:
    """Can this environment sign a commit right now?

    Reports facts about the *machine* only. It never reads the secret, so its
    output is safe to print (and CodeQL agrees, which is why the split exists).
    """
    env = os.environ if env is None else env
    key_path = (env.get("GENESIS_SIGNING_KEY_PATH")
                or os.path.expanduser("~/.ssh/genesis_signing"))
    has_keygen = bool(which("ssh-keygen"))
    has_key = bool(exists(key_path))
    return {
        "ssh_keygen": has_keygen,
        "private_key_present": has_key,
        "can_sign_locally": has_keygen and has_key,
        "can_sign_in_ci": True,  # the workflow materialises the secret on the runner
        # Literal, not interpolated: CodeQL (rightly) treats any expression
        # derived from a secret-named constant as secret material, and a log
        # line is no place to argue about it. The name is public; the value is
        # never read here at all.
        "detail": ("local signing available" if has_keygen and has_key else
                   "no private key on this machine; sign in CI from the "
                   "SSH_SIGNING_KEY secret (or on the owner's machine)"),
    }


def sign_plan(branch: str, mode: str = "squash-sign", base: str = "main",
              commits: int = 1) -> dict[str, Any]:
    """The exact commands a signer would run, as data. Nothing is executed.

    ``squash-sign`` flattens the branch onto ``base`` into one signed commit,
    which satisfies both ``required_signatures`` and ``required_linear_history``.
    ``resign`` amends the head, so it only makes sense for a single commit.
    """
    ok, reason = branch_is_signable(branch)
    if not ok:
        raise SigningError(f"refusing to sign: {reason}")
    if mode not in SIGN_MODES:
        raise SigningError(f"unknown mode {mode!r}; expected one of {SIGN_MODES}")
    if mode == "resign" and commits != 1:
        raise SigningError("resign needs exactly one commit; use squash-sign")

    config = [
        "git config gpg.format ssh",
        "git config commit.gpgsign true",
        'git config user.signingkey "$SIGNING_KEY_PATH"',
    ]
    if mode == "squash-sign":
        # The message and author are captured *before* the reset: reset --soft
        # moves the branch pointer, so reading them afterwards reads base's
        # commit instead of the branch's.
        rewrite = [
            "git log -1 --format='%B' > \"$COMMIT_MESSAGE_FILE\"",
            "ORIGINAL_AUTHOR=\"$(git log -1 --format='%an <%ae>')\"",
            f"git fetch origin {base}",
            f"git reset --soft origin/{base}",
            "git commit -S -F \"$COMMIT_MESSAGE_FILE\" --author=\"$ORIGINAL_AUTHOR\"",
        ]
    else:
        rewrite = ["git commit --amend --no-edit -S"]
    return {
        "branch": branch,
        "mode": mode,
        "base": base,
        "config": config,
        "rewrite": rewrite,
        "push": f"git push --force-with-lease origin HEAD:{branch}",
        "verify": f"python3 scripts/verify_signed_commits.py verify --branch {branch}",
    }


def verify_branch(repo: str, shas: Iterable[str],
                  http: Callable[[str, str, dict | None], Any]) -> dict[str, Any]:
    """Verify every commit; fail closed. Wraps the canonical reader."""
    shas = list(shas)
    blockers = signature_blockers(repo, shas, http)
    verdicts: list[CommitSignature] = [read_signature(repo, sha, http) for sha in shas]
    return {
        "ok": not blockers,
        "checked": len(shas),
        "blockers": blockers,
        "commits": [v.to_dict() for v in verdicts],
    }
