"""Decision table for auto-review re-check and history management (spec §4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NamedTuple


class RevisionKey(NamedTuple):
    revision: int
    oracle_fp: str
    docs_fp: str | None


@dataclass(frozen=True, slots=True)
class Decision:
    action: Literal["check", "skip_unchanged", "skip_same_as_rev", "skip_not_eligible"]
    changed: str | None = None
    same_as_rev: int | None = None


def decide(
    pending_reason: str | None,
    prev: list[RevisionKey],
    oracle_fp: str,
    docs_fp: str | None,
    manual: bool = False,
) -> Decision:
    """Decide whether to execute an ELR review check or skip based on history fingerprints.

    Priority order:
    1. manual trigger -> action="check", changed="manual"
    2. pending_reason (not eligible) -> action="skip_not_eligible"
    3. no previous revision -> action="check", changed="new"
    4. equal to latest revision -> action="skip_unchanged"
    5. equal to an older revision -> action="skip_same_as_rev", same_as_rev=N
    6. otherwise -> action="check", changed in ("oracle", "docs", "both")
    """
    if manual:
        return Decision(action="check", changed="manual")

    if pending_reason is not None:
        return Decision(action="skip_not_eligible")

    if not prev:
        return Decision(action="check", changed="new")

    # Sort revisions by revision number ascending; latest is the last element
    sorted_prev = sorted(prev, key=lambda r: r.revision)
    latest = sorted_prev[-1]

    # Cheap-first: if docs_fp is None, check if oracle matches latest
    if docs_fp is None:
        if oracle_fp == latest.oracle_fp:
            return Decision(action="skip_unchanged")
        return Decision(action="check", changed="oracle")

    # Full check with both oracle_fp and docs_fp
    if oracle_fp == latest.oracle_fp and docs_fp == latest.docs_fp:
        return Decision(action="skip_unchanged")

    # Check against older revisions (reverted data check)
    older_revs = [r for r in sorted_prev if r.revision != latest.revision]
    for old in reversed(older_revs):
        if old.oracle_fp == oracle_fp and old.docs_fp == docs_fp:
            return Decision(action="skip_same_as_rev", same_as_rev=old.revision)

    # Determine what changed relative to latest revision
    oracle_changed = (oracle_fp != latest.oracle_fp)
    docs_changed = (docs_fp != latest.docs_fp)

    if oracle_changed and docs_changed:
        changed = "both"
    elif oracle_changed:
        changed = "oracle"
    else:
        changed = "docs"

    return Decision(action="check", changed=changed)
