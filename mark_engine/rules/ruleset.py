from __future__ import annotations

import importlib.resources as pkg_resources
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mark_engine.domain.models import Flag

_ALLOWED_STAGES = frozenset({"generate", "compare", "gate"})


class RuleSet:
    """Versioned mark ruleset loaded from frozen JSON definition."""

    def __init__(
        self,
        version: str,
        rules: Sequence[Mapping[str, Any]],
        approvals: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self._version = version
        self._rules: tuple[dict[str, Any], ...] = tuple(dict(r) for r in rules)
        self._rules_by_id: dict[str, dict[str, Any]] = {
            r["rule_id"]: r for r in self._rules
        }
        self._approvals: tuple[dict[str, Any], ...] = tuple(dict(a) for a in approvals)
        self._approvals_by_id: dict[str, dict[str, Any]] = {
            a["rule_id"]: a for a in self._approvals
        }

    @property
    def version(self) -> str:
        return self._version

    @property
    def rules(self) -> tuple[dict[str, Any], ...]:
        return self._rules

    @property
    def approvals(self) -> tuple[dict[str, Any], ...]:
        return self._approvals

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuleSet:
        version = str(data.get("rule_version", ""))
        rules = data.get("rules", [])
        approvals = data.get("approvals", [])
        return cls(version=version, rules=rules, approvals=approvals)

    @classmethod
    def load(cls, version: str = "RV-2026-11-04-R0") -> RuleSet:
        """Load a RuleSet version from package resources or local data directory."""
        try:
            ref = pkg_resources.files("mark_engine.rules").joinpath("data", f"{version}.json")
            with ref.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            path = Path(__file__).resolve().parent / "data" / f"{version}.json"
            if not path.is_file():
                raise FileNotFoundError(f"Rule version file not found: {path}")
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        return cls.from_dict(data)

    def rule(self, rule_id: str) -> dict[str, Any]:
        """Lookup a rule dict by its rule_id. Raises KeyError if not found."""
        if rule_id not in self._rules_by_id:
            raise KeyError(f"Rule {rule_id!r} not found in RuleSet {self._version!r}")
        return self._rules_by_id[rule_id]

    def condition(self, rule_id: str) -> str | None:
        """Return the condition string for an approved rule, or None."""
        self.rule(rule_id)  # verifies rule exists
        approval = self._approvals_by_id.get(rule_id)
        if approval:
            cond = approval.get("condition")
            return str(cond) if cond else None
        return None

    def usable(self, rule_id: str) -> tuple[bool, frozenset[Flag]]:
        """Determine if a rule is usable and return any associated flags.

        Rules with decision == 'REJECTED' or stage not in (generate, compare, gate)
        are not usable -> (False, frozenset()).
        Rules with provenance_class == 'ORACLE_DERIVED' without an 'APPROVED*' decision
        are usable with flag ORACLE_DERIVED_UNAPPROVED -> (True, {Flag.ORACLE_DERIVED_UNAPPROVED}).
        Otherwise usable -> (True, frozenset()).
        """
        rule = self.rule(rule_id)
        approval = self._approvals_by_id.get(rule_id)
        decision = approval.get("decision") if approval else None

        if decision == "REJECTED":
            return (False, frozenset())

        rule_stage = rule.get("rule_stage")
        if rule_stage not in _ALLOWED_STAGES:
            return (False, frozenset())

        provenance_class = rule.get("provenance_class")
        if provenance_class == "ORACLE_DERIVED":
            is_approved = decision is not None and decision.startswith("APPROVED")
            if not is_approved:
                return (True, frozenset({Flag.ORACLE_DERIVED_UNAPPROVED}))

        return (True, frozenset())
