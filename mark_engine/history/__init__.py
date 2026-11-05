"""History, fingerprinting, and re-check decision logic for Mark Automation."""

from mark_engine.history.fingerprint import (
    ORACLE_FP_FIELDS,
    oracle_fp,
    docs_fp,
    version_fp,
    result_fp,
    changed_oracle_fields,
)
from mark_engine.history.decide import Decision, RevisionKey, decide

__all__ = [
    "ORACLE_FP_FIELDS",
    "oracle_fp",
    "docs_fp",
    "version_fp",
    "result_fp",
    "changed_oracle_fields",
    "Decision",
    "RevisionKey",
    "decide",
]
