"""Input fingerprints for Oracle rows, documents, versions, and job results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePath, PureWindowsPath, PurePosixPath
from typing import Any, Mapping, Sequence

from mark_engine.domain.models import DocumentResolution, JobResult

ORACLE_FP_FIELDS: tuple[str, ...] = (
    "PRODUCT_NO",
    "CUST_ASSY_LOT",
    "TOP_MARK1",
    "TOP_MARK2",
    "TOP_MARK3",
    "TOP_MARK4",
    "TOP_MARK5",
    "TOP_MARK_ID",
    "TOP_TYPE_CODE",
    "TOP_LAYOUT_CODE",
    "MARK_REMARK",
    "MARK_REQUIRE",
    "CUST_REQ_NO",
    "CURRENT_STEP",
    "STATUS",
)


def _clean_oracle_val(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.rstrip()
    return str(val).rstrip()


def _extract_oracle_canonical_dict(row: Mapping[str, Any]) -> dict[str, str]:
    upper_map = {k.upper(): v for k, v in row.items()}
    canonical: dict[str, str] = {}
    for field in ORACLE_FP_FIELDS:
        val = upper_map.get(field)
        canonical[field] = _clean_oracle_val(val)
    return canonical


def oracle_fp(row: Mapping[str, Any]) -> str:
    """Compute sha256 hex digest of canonical Oracle row fields."""
    canonical = _extract_oracle_canonical_dict(row)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def changed_oracle_fields(old_row: Mapping[str, Any], new_row: Mapping[str, Any]) -> list[str]:
    """Return names of fields in ORACLE_FP_FIELDS whose canonical values changed."""
    old_c = _extract_oracle_canonical_dict(old_row)
    new_c = _extract_oracle_canonical_dict(new_row)
    return [f for f in ORACLE_FP_FIELDS if old_c[f] != new_c[f]]


def _relativize_path(path_str: str | Path | PurePath, roots: Sequence[Path | PurePath | str]) -> str:
    path_raw = str(path_str)
    for idx, root in enumerate(roots):
        root_str = str(root)
        is_windows = (
            isinstance(root, PureWindowsPath)
            or "\\" in root_str
            or (len(root_str) >= 2 and root_str[1] == ":")
            or root_str.startswith(r"\\")
        )
        if is_windows:
            p_pure = PureWindowsPath(path_raw)
            root_pure = PureWindowsPath(root_str)
        else:
            p_pure = PurePosixPath(path_raw)
            root_pure = PurePosixPath(root_str)

        try:
            rel = p_pure.relative_to(root_pure)
            return f"{idx}:{rel.as_posix()}"
        except (ValueError, TypeError):
            continue
    return path_raw


def docs_fp(resolution: DocumentResolution | None, roots: Sequence[Path | PurePath | str] = ()) -> str:
    """Compute sha256 hex digest of sorted (role, path, sha256) of resolved ABS and SLR documents.

    If roots are provided, any path under one of roots is relativized to '<root index>:<relative path>'.
    If resolution is None or resolution contains no files (e.g. HOLD with no files),
    returns sha256 of "none".
    """
    if resolution is None:
        return hashlib.sha256(b"none").hexdigest()

    entries: list[tuple[str, str, str]] = []
    if resolution.abs is not None:
        entries.append(("abs", _relativize_path(resolution.abs.path, roots), resolution.abs.sha256))
    for slr_ref in resolution.slr:
        entries.append(("slr", _relativize_path(slr_ref.path, roots), slr_ref.sha256))

    if not entries:
        return hashlib.sha256(b"none").hexdigest()

    # Sort entries by role, path, sha256 for deterministic ordering
    entries.sort(key=lambda x: (x[0], x[1], x[2]))
    payload = json.dumps(entries, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def version_fp(engine_version: str, model_version: str) -> str:
    """Compute sha256 hex digest of engine and model version identifiers."""
    payload = f"{engine_version}:{model_version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def result_fp(job: JobResult) -> str:
    """Compute sha256 hex digest of expected mark lines plus line comparison statuses."""
    expected_lines: list[tuple[str, int, str]] = []
    if job.expected is not None:
        expected_lines = [(line.side.value, line.line_no, line.text) for line in job.expected.lines]

    line_statuses: list[tuple[str, int, str]] = [
        (c.side.value, c.line_no, c.status.value) for c in job.comparisons
    ]

    data = {
        "processing_status": job.processing_status.value,
        "hold_reason": job.hold_reason or "",
        "expected": expected_lines,
        "statuses": line_statuses,
    }
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
