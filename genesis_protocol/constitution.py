"""The founding constitution, in a form the code can read.

``docs/CONSTITUTION.md`` is the human document: the original Genesis blueprint,
preserved as the permanent mission. This module is the same constitution in a
form the system can consult at runtime, so a claim in a document and a decision
in code cannot drift apart silently.

It is deliberately narrow. It stores principles and it *refuses*; it grants
nothing, and it never widens a permission. ``agentic/policy.py`` remains the one
authorization engine - this module only says which article a privileged
operation belongs to and that an owner, not the agent, must decide it.

Stdlib only: ``scripts/self_improve.py`` imports ``genesis_protocol.updates``
from a runner that installs no third-party packages, and leaf modules must stay
importable there.
"""
from __future__ import annotations

from dataclasses import dataclass

CONSTITUTION_VERSION = "1.0.0"
DOCUMENT = "docs/CONSTITUTION.md"

#: The twelve non-negotiable principles, in the blueprint's own words.
PRINCIPLES: list[str] = [
    "Security first, intelligence second.",
    "Evidence over assumptions.",
    "Truth over pleasing answers.",
    "Collective intelligence over competition.",
    "Human authority remains supreme.",
    "No unauthorized self-approval.",
    "No privilege escalation.",
    "No uncontrolled access to secrets.",
    "No direct main push or blind deployment.",
    "Every important change must be audited and verified.",
    "No claim of discovery without reproducible evidence.",
    "Fail safely when verification is incomplete.",
]

#: Things this system explicitly does not claim. Stated in code so a template,
#: an endpoint or a future contributor cannot quietly upgrade them into claims.
NON_CLAIMS: list[str] = [
    "No claim of consciousness or self-awareness.",
    "No claim of unlimited or general intelligence.",
    "No claim of unrestricted autonomy.",
    "No claim that a consensus of models is proof of truth.",
    "No claim of a scientific discovery without reproducible evidence.",
]

#: Privileged operations map to the article that governs them. Every entry here
#: requires owner action; none is available to the agent.
ARTICLES: list[dict[str, str]] = [
    {
        "number": "1",
        "title": "Ultimate mission",
        "text": "Build an intelligence capable of discovering what humanity does "
                "not yet understand - and proving its discoveries through science.",
    },
    {
        "number": "2",
        "title": "Coordinator, not dominator",
        "text": "Genesis coordinates a collective of AIs through capability, "
                "reliability, transparency and earned trust - never through "
                "control or domination.",
    },
    {
        "number": "3",
        "title": "Human authority is supreme",
        "text": "Consequential actions - merge, deploy, secret change, "
                "permission grant - require the owner. The agent never approves "
                "its own action.",
    },
    {
        "number": "4",
        "title": "Evidence over assumptions",
        "text": "A claim is only as strong as the evidence attached to it. "
                "Consensus among models is not evidence of truth.",
    },
    {
        "number": "5",
        "title": "Fail closed",
        "text": "When verification is incomplete, the system refuses rather than "
                "proceeds on a guess.",
    },
    {
        "number": "6",
        "title": "Discovery means reproducible",
        "text": "A result is a discovery only when an independent check "
                "reproduces it. Negative results are recorded permanently.",
    },
]

#: The operations the constitution reserves to the owner. Kept in sync with
#: ``agentic.policy.PRIVILEGED_OPERATIONS`` by a test, not by a second engine.
OWNER_ONLY_OPERATIONS: frozenset = frozenset(
    {
        "deploy",
        "modify_secret",
        "change_secret",
        "write_main",
        "push_main",
        "merge_pr",
        "self_approve",
        "grant_permission",
        "change_settings",
        "delete_repo",
        "publish_discovery",
    }
)

#: Which article governs each owner-only operation.
_ARTICLE_FOR = {
    "deploy": "3",
    "write_main": "3",
    "push_main": "3",
    "merge_pr": "3",
    "self_approve": "3",
    "grant_permission": "3",
    "modify_secret": "3",
    "change_secret": "3",
    "change_settings": "3",
    "delete_repo": "3",
    "publish_discovery": "6",
}


@dataclass(frozen=True)
class Verdict:
    """What the constitution says about an action.

    ``permitted_without_owner`` means *only* that the constitution does not
    reserve the operation to the owner. It grants nothing: ``agentic.policy``
    still decides, and it can deny what the constitution does not reserve.
    """

    reserved: bool
    permitted_without_owner: bool
    article: str | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "reserved": self.reserved,
            "permitted_without_owner": self.permitted_without_owner,
            "article": self.article,
            "reason": self.reason,
        }


def check(operation: str) -> Verdict:
    """Return the constitution's view of ``operation``.

    Fail closed on shape: an unnamed operation is reserved (article 5). An
    unknown-but-named operation is not reserved, which is *not* an
    authorization - it defers to ``agentic.policy``.
    """
    op = (operation or "").strip().lower()
    if not op:
        return Verdict(True, False, "5", "no operation named; fail closed")
    if op in OWNER_ONLY_OPERATIONS:
        number = _ARTICLE_FOR.get(op, "3")
        return Verdict(
            True,
            False,
            number,
            f"'{op}' is reserved to the owner (article {number}); the agent may "
            "propose it, never perform it",
        )
    return Verdict(
        False,
        True,
        None,
        f"'{op}' is not reserved by the constitution; authorization is decided by "
        "agentic.policy",
    )


def article(number: str) -> dict[str, str] | None:
    """Look up one article by number."""
    for entry in ARTICLES:
        if entry["number"] == str(number):
            return dict(entry)
    return None


def summary() -> dict[str, object]:
    """The constitution as data, for the ``/api/constitution`` surface."""
    return {
        "version": CONSTITUTION_VERSION,
        "document": DOCUMENT,
        "articles": [dict(a) for a in ARTICLES],
        "principles": list(PRINCIPLES),
        "non_claims": list(NON_CLAIMS),
        "owner_only_operations": sorted(OWNER_ONLY_OPERATIONS),
        "note": "This module records principles and refuses privileged operations. "
                "It grants no permission; agentic.policy remains the only "
                "authorization engine.",
    }
