"""Authorization policy for the CLI-backed tools (kubectl, aws, docker, ...).

``shell=False`` removes shell injection; it says nothing about what the tool is
allowed to *do*. ``kubectl delete ns prod`` is a single argv with no
metacharacter anywhere, and it still destroys production. So the decision is
made here, from the binary and its arguments, and it is default-deny:

* ``deny``    - destructive, deployment, credential or privilege-changing
                verbs. Never consentable: no approval record can authorise them.
* ``allow``   - a read-only verb from the per-binary allowlist. The caller is
                still gated by ``ToolPermission.RESTRICTED`` (owner only).
* ``consent`` - anything else. Owner identity **and** a single-use approval
                bound to the exact executable + arguments are required.

Matching is on whole tokens (and their leading verb, so ``delete-context``
matches ``delete``), never on substrings: ``--filter name=delete-me`` is not a
delete.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

DENY = "deny"
ALLOW = "allow"
CONSENT = "consent"


@dataclass(frozen=True)
class Verdict:
    decision: str
    operation: str
    reason: str

    @property
    def denied(self) -> bool:
        return self.decision == DENY

    @property
    def needs_consent(self) -> bool:
        return self.decision == CONSENT


# Destructive, deployment, credential and privilege-changing verbs. A token
# matches when it equals a term, or when its first hyphen-separated word does
# (``delete-context`` -> ``delete``).
DANGEROUS_VERBS = frozenset({
    # destruction
    "delete", "remove", "rm", "rmi", "prune", "purge", "destroy", "terminate",
    "truncate", "drain", "cordon", "uncordon", "taint", "evict", "kill", "stop",
    "restart", "rollback",
    # deployment / state change
    "apply", "create", "replace", "patch", "edit", "scale", "rollout", "upgrade",
    "install", "deploy", "import", "push", "merge", "release", "publish", "sync",
    "set", "unset", "attach", "copy",
    # credentials / privilege
    "login", "logout", "auth", "iam", "sts", "secret", "secretsmanager", "kms",
    "credential", "credentials", "token", "passwd", "password", "chmod", "chown",
    "sudo", "su", "assume-role",
    # arbitrary execution / data movement
    "exec", "run", "api", "cp", "scp", "rsync", "upload", "download",
})

# Credential access, refused wherever it appears - even under a read-only verb
# (``kubectl describe secret`` is a credential read, not a description).
CREDENTIAL_TERMS = frozenset({
    "secret", "secrets", "secretsmanager", "iam", "sts", "kms", "credential",
    "credentials", "token", "passwd", "password", "keychain", "vault",
})

# Read-only verbs per binary. Anything not listed falls through to CONSENT.
READ_ONLY: Dict[str, frozenset] = {
    "kubectl": frozenset({"get", "describe", "logs", "version", "top",
                          "api-resources", "explain", "cluster-info"}),
    "docker": frozenset({"ps", "images", "inspect", "version", "info", "logs",
                         "stats", "history", "top", "port", "diff"}),
    "gcloud": frozenset({"list", "describe", "version", "info"}),
    "az": frozenset({"list", "show", "version"}),
    "terraform": frozenset({"version", "show", "output", "plan", "validate"}),
    "gh": frozenset({"status"}),
}

# Prefixes that mean "read" on binaries whose verbs are hyphenated nouns
# (``aws describe-instances``, ``aws list-buckets``).
READ_ONLY_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "aws": ("describe-", "list-", "get-", "head-"),
}

# ``gh`` groups its verbs under a noun (``gh pr list``). Only these pairs are
# read-only; ``gh pr merge`` is caught by DANGEROUS_VERBS first.
GH_READ_ONLY = frozenset({
    ("pr", "list"), ("pr", "view"), ("pr", "diff"), ("pr", "checks"),
    ("pr", "status"),
    ("issue", "list"), ("issue", "view"), ("issue", "status"),
    ("repo", "view"), ("repo", "list"),
    ("run", "list"), ("run", "view"), ("workflow", "list"), ("workflow", "view"),
    ("release", "list"), ("release", "view"),
})

# Binaries that cannot change state: they print, report or exit. Used by the
# diagnostics/tests, never by the registered CLI tools.
HARMLESS_BINARIES = frozenset({
    "echo", "printf", "false", "true", "date", "uname", "whoami", "id",
})

# Tools that only read an input file and write an output file in the working
# directory (a document compiler is not a privileged operation).
FILE_ONLY_BINARIES = frozenset({"pdflatex", "pandoc"})

# ``crontab`` is persistence: only listing is read-only.
CRONTAB_READ_ONLY = frozenset({"-l", "--list"})


def _verb(token: str) -> str:
    """``--delete-context`` -> ``delete-context`` -> ``delete``."""
    return token.lstrip("-").split("=", 1)[0].lower()


def _matches_dangerous(token: str) -> bool:
    base = _verb(token)
    if base in DANGEROUS_VERBS:
        return True
    return base.split("-", 1)[0] in DANGEROUS_VERBS


def classify(binary: str, args: Sequence[str]) -> Verdict:
    """Decide whether ``binary`` may run with ``args``, and why."""
    argv: List[str] = [str(a) for a in args]

    for token in argv:
        if _verb(token) in CREDENTIAL_TERMS:
            return Verdict(DENY, _verb(token),
                           f"'{_verb(token)}' is a credential or privilege operation")

    # A read-only verb decides, so ``kubectl describe deploy api`` is a read and
    # not a deployment: ``deploy`` is the resource, not the action. Credential
    # nouns were refused above, and no read verb can delete or apply.
    positional = [t for t in argv if not t.startswith("-")]
    if binary == "gh" and len(positional) >= 2:
        pair = tuple(t.lower() for t in positional[:2])
        if pair in GH_READ_ONLY:
            return Verdict(ALLOW, " ".join(pair), "read-only")
    read_set = READ_ONLY.get(binary, frozenset())
    for token in (t.lower() for t in positional):
        if token in read_set or any(token.startswith(p) for p in READ_ONLY_PREFIXES.get(binary, ())):
            return Verdict(ALLOW, token, "read-only")

    # A dangerous verb anywhere in the arguments is refused, not consented to.
    for token in argv:
        if _matches_dangerous(token):
            return Verdict(DENY, _verb(token),
                           f"'{_verb(token)}' is a destructive, deployment, "
                           "credential or privilege operation")

    if binary == "crontab":
        if len(argv) == 1 and argv[0] in CRONTAB_READ_ONLY:
            return Verdict(ALLOW, "list", "read-only")
        return Verdict(DENY, "write", "modifying the crontab is persistence, which is not permitted")

    if binary in HARMLESS_BINARIES:
        return Verdict(ALLOW, binary, "harmless binary")

    if binary in FILE_ONLY_BINARIES:
        return Verdict(ALLOW, "compile", "document compiler")

    if not positional:
        return Verdict(CONSENT, "", "no operation named; an approval is required")

    if binary == "gh":
        pair = tuple(t.lower() for t in positional[:2])
        return Verdict(CONSENT, " ".join(pair), "state-changing; needs a scoped approval")

    return Verdict(CONSENT, positional[0].lower(), "state-changing; needs a scoped approval")


def canonical_command(binary: str, argv: Iterable[str]) -> str:
    """The exact string an approval is bound to (executable + arguments)."""
    return " ".join([binary, *[str(a) for a in argv]])
