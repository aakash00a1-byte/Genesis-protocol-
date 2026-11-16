"""Reversible changes (V7 P9).

Every change P9 can make is expressed as a :class:`ReversibleChange`: the set of
files it touches, their content before and after, and a full backup of the
originals. Applying is atomic (all-or-nothing, temp file + ``os.replace``) and
``rollback`` restores the exact prior bytes, so any change can be undone.

Safety properties:

* paths are confined to a declared root; a path that escapes it is refused;
* a file that already differs from the recorded ``before`` is refused, so a
  change never clobbers someone else's edit;
* applying requires an explicit owner approval, matching the rest of the system.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChangeRefused(RuntimeError):
    """Raised when a change is unsafe to apply or roll back."""


@dataclass
class ReversibleChange:
    """A change that can be applied and rolled back with byte fidelity."""

    change_id: str
    before: Dict[str, str]  # relative path -> prior content ("" if the file is new)
    after: Dict[str, str]  # relative path -> new content
    created_at: str = field(default_factory=utcnow)
    applied: bool = False
    applied_at: Optional[str] = None
    rolled_back_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def files(self) -> List[str]:
        return sorted(set(self.before) | set(self.after))

    def apply(self, root: str, owner_approved: bool = False) -> Dict[str, Any]:
        """Write ``after`` into ``root`` atomically. Owner approval is required."""
        if not owner_approved:
            raise ChangeRefused("applying a change requires owner approval")
        base = Path(root).resolve()
        if self.applied:
            raise ChangeRefused(f"change {self.change_id} is already applied")

        staged: List[tuple] = []
        try:
            for rel, content in self.after.items():
                target = _resolve(base, rel)
                if target.exists():
                    current = target.read_text(encoding="utf-8")
                    if rel in self.before and current != self.before[rel]:
                        raise ChangeRefused(
                            f"refusing to overwrite '{rel}': it changed since the backup"
                        )
                target.parent.mkdir(parents=True, exist_ok=True)
                staged.append((target, content))

            for target, content in staged:
                _atomic_write(target, content)
        except Exception:
            # Best-effort revert of anything already written in this call.
            for target, _ in staged:
                rel = str(target.relative_to(base))
                if rel in self.before and self.before[rel] != "":
                    _atomic_write(target, self.before[rel])
            raise

        self.applied = True
        self.applied_at = utcnow()
        return {"change_id": self.change_id, "applied": self.files, "at": self.applied_at}

    def rollback(self, root: str) -> Dict[str, Any]:
        """Restore the exact prior bytes; delete files that were newly created."""
        base = Path(root).resolve()
        restored: List[str] = []
        deleted: List[str] = []
        for rel in self.files:
            target = _resolve(base, rel)
            prior = self.before.get(rel)
            if prior is None or prior == "":
                # The change created this file; rollback removes it.
                if target.exists():
                    target.unlink()
                    deleted.append(rel)
            else:
                _atomic_write(target, prior)
                restored.append(rel)
        self.applied = False
        self.rolled_back_at = utcnow()
        return {"change_id": self.change_id, "restored": restored,
                "deleted": deleted, "at": self.rolled_back_at}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReversibleChange":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


def snapshot(root: str, files: List[str]) -> Dict[str, str]:
    """Read the current content of ``files`` (for use as ``before``)."""
    base = Path(root).resolve()
    out: Dict[str, str] = {}
    for rel in files:
        target = _resolve(base, rel)
        out[rel] = target.read_text(encoding="utf-8") if target.exists() else ""
    return out


def _resolve(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    if base != target and base not in target.parents:
        raise ChangeRefused(f"path escapes the change root: {rel}")
    return target


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)
