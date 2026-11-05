"""Mark domain endpoints: runs, ELRs, ELR detail, and images."""
from pathlib import Path
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from mark_api.deps import current_user, get_repo, require
from mark_api.files import safe_file
from mark_api.grouping import classify_line, classify_job
from mark_api.repo import Repo

router = APIRouter(tags=["mark"])


@router.get("/runs")
def list_runs(user: dict[str, Any] = Depends(require("read")), repo: Repo = Depends(get_repo)):
    return repo.runs()


@router.get("/elrs")
def list_elrs(
    run: int = Query(...),
    month: str | None = None,
    result: str | None = None,
    cause: str | None = None,
    q: str | None = None,
    page: int = 1,
    user: dict[str, Any] = Depends(require("read")),
    repo: Repo = Depends(get_repo),
):
    jobs = repo.jobs(run)
    lines = repo.lines(run)

    # Group lines by elr_no
    lines_by_elr: dict[str, list[dict[str, Any]]] = {}
    for l in lines:
        lines_by_elr.setdefault(l["elr_no"], []).append(l)

    rows: list[dict[str, Any]] = []
    q_lower = q.strip().lower() if q else ""

    for j in jobs:
        elr_no = j["elr_no"]
        elr_month = f"20{elr_no[3:5]}-{elr_no[5:7]}" if len(elr_no) >= 7 and elr_no.startswith("ADI") else ""
        elr_lines = lines_by_elr.get(elr_no, [])

        ps = classify_job(j.get("processing_status", ""))
        true_lines = 0
        total_lines = len(elr_lines)
        has_error = False
        has_warning = False
        line_cause = ""

        for l in elr_lines:
            grp = classify_line(l.get("status") or "", l.get("warning") or "")
            if grp == "TRUE":
                true_lines += 1
            elif grp == "WARNING":
                has_warning = True
                if not line_cause:
                    line_cause = l.get("warning", "").split(":")[0].strip()
            elif grp == "ERROR":
                has_error = True
                if not line_cause:
                    line_cause = l.get("detail", "").split(";")[0].split(":")[0].strip()

        if ps == "HOLD":
            res_val = "HOLD"
            cause_val = j.get("hold_reason", "").split(":")[0].strip() or "HOLD"
        elif ps == "FAILED" or has_error:
            res_val = "ERROR"
            cause_val = line_cause or j.get("hold_reason", "").split(":")[0].strip() or "ERROR"
        elif has_warning:
            res_val = "WARNING"
            cause_val = line_cause or "WARNING"
        elif true_lines > 0 and true_lines == total_lines:
            res_val = "TRUE"
            cause_val = ""
        else:
            res_val = "UNMEASURED"
            cause_val = ""

        # Filters
        if month and elr_month != month:
            continue
        if result and res_val != result:
            continue
        if cause and cause_val != cause:
            continue
        if q_lower:
            abs_file = (j.get("abs_no") or "").lower()
            if q_lower not in elr_no.lower() and q_lower not in abs_file:
                continue

        rows.append(
            {
                "elr_no": elr_no,
                "month": elr_month,
                "abs_file": j.get("abs_no") or "",
                "result": res_val,
                "true_lines": true_lines,
                "total_lines": total_lines,
                "cause": cause_val,
            }
        )

    total = len(rows)
    page_size = 50
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]

    return {
        "total": total,
        "page": page,
        "rows": page_rows,
    }


@router.get("/elrs/{elr}")
def get_elr(elr: str, run: int = Query(...), user: dict[str, Any] = Depends(require("read")), repo: Repo = Depends(get_repo)):
    # 4 queries max
    snapshot = repo.snapshot(run, elr)
    lines_raw = repo.lines_for_elr(run, elr)
    reviews = repo.latest_reviews(run, elr)
    approval = repo.latest_approval(run, elr)

    # job info from snapshot or lines
    if snapshot and "processing_status" in snapshot:
        job = {
            "processing_status": snapshot.get("processing_status", "DONE"),
            "hold_reason": snapshot.get("hold_reason", ""),
            "hold_detail": snapshot.get("hold_detail", ""),
        }
    elif lines_raw and "processing_status" in lines_raw[0]:
        job = {
            "processing_status": lines_raw[0].get("processing_status", "DONE"),
            "hold_reason": lines_raw[0].get("hold_reason", ""),
            "hold_detail": lines_raw[0].get("hold_detail", ""),
        }
    else:
        # fallback if not merged in test fake
        job_direct = repo.job(run, elr) if hasattr(repo, "job") else None
        job = job_direct or {"processing_status": "DONE", "hold_reason": ""}

    lines = [
        {
            "line_no": l["line_no"],
            "expected": l.get("expected", ""),
            "oracle": l.get("oracle", ""),
            "status": l.get("status", ""),
            "group": classify_line(l.get("status", ""), l.get("warning", "")),
            "warning": l.get("warning", ""),
            "detail": l.get("detail", ""),
            "compare_rules": l.get("compare_rules", ""),
        }
        for l in lines_raw
    ]

    files_root = Path(os.getenv("MARK_FILES_ROOT", "data/files"))
    image_avail = False
    if snapshot and snapshot.get("image_path"):
        img_p = safe_file(files_root, snapshot["image_path"])
        image_avail = img_p is not None

    return {
        "snapshot": snapshot,
        "job": job,
        "lines": lines,
        "reviews": reviews,
        "approval": approval,
        "image_available": image_avail,
    }


@router.get("/files/abs/{run}/{elr}")
def get_abs_file(
    run: int,
    elr: str,
    if_none_match: str | None = Header(None),
    user: dict[str, Any] = Depends(require("read")),
    repo: Repo = Depends(get_repo),
):
    snapshot = repo.snapshot(run, elr)
    if not snapshot or not snapshot.get("image_path"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    files_root = Path(os.getenv("MARK_FILES_ROOT", "data/files"))
    resolved = safe_file(files_root, snapshot["image_path"])
    if not resolved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image path invalid or outside root")

    etag = snapshot.get("abs_sha256") or ""
    if if_none_match and if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    headers = {
        "ETag": etag,
        "Cache-Control": "private, max-age=86400",
    }
    return FileResponse(path=resolved, media_type="image/png", headers=headers)
