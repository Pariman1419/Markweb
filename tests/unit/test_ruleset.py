import pytest

from mark_engine.domain.models import Flag
from mark_engine.rules.ruleset import RuleSet


def test_r0_has_44_rules_and_4_classes():
    rs = RuleSet.load()
    assert rs.version == "RV-2026-11-04-R0"
    assert len(rs.rules) == 44
    assert isinstance(rs.rules, tuple)
    assert {r["provenance_class"] for r in rs.rules} == {
        "SPEC_DERIVED",
        "ORACLE_DERIVED",
        "EXPERIMENTAL",
        "PENDING_VERIFICATION",
    }


@pytest.mark.parametrize("rid", ["R07-PIN-NOTE", "R04-SLR-LITERAL", "R03-ONE-ABS"])
def test_rejected_rules_not_usable(rid):
    assert RuleSet.load().usable(rid) == (False, frozenset())


def test_remark_caret_usable_with_condition():
    rs = RuleSet.load()
    assert rs.usable("R07-REMARK-CARET") == (True, frozenset())
    condition = rs.condition("R07-REMARK-CARET")
    assert condition is not None
    assert "NEEDS_REVIEW" in condition


def test_unapproved_oracle_derived_flags(tmp_path):
    rs = RuleSet.from_dict({
        "rule_version": "T",
        "rules": [
            {
                "rule_id": "X",
                "rule_stage": "generate",
                "provenance_class": "ORACLE_DERIVED",
            }
        ],
        "approvals": [],
    })
    assert rs.usable("X") == (True, frozenset({Flag.ORACLE_DERIVED_UNAPPROVED}))


def test_rule_lookup_and_missing():
    rs = RuleSet.load()
    rule_data = rs.rule("R01-ORACLE")
    assert rule_data["rule_id"] == "R01-ORACLE"
    assert rule_data["provenance_class"] == "SPEC_DERIVED"

    with pytest.raises(KeyError):
        rs.rule("NONEXISTENT_RULE")

    with pytest.raises(KeyError):
        rs.condition("NONEXISTENT_RULE")

    with pytest.raises(KeyError):
        rs.usable("NONEXISTENT_RULE")


def test_condition_helper():
    rs = RuleSet.load()
    assert rs.condition("R01-ORACLE") is None
    assert rs.condition("R06-SHIFT") is None
    cond = rs.condition("R07-REMARK-CARET")
    assert isinstance(cond, str)
    assert len(cond) > 0


def test_stage_not_in_scope_not_usable():
    rs = RuleSet.load()
    # R01-ORACLE has rule_stage == "process"
    assert rs.usable("R01-ORACLE") == (False, frozenset())
