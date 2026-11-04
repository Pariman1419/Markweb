from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from mark_engine.adapters.snapshot import (
    load_elr_snapshot,
    load_inference,
    r0_root,
    verify_r0_root,
)
from mark_engine.domain.models import JobResult, LineStatus, OracleMark, ProcessingStatus
from mark_engine.pipeline import process_elr
from mark_engine.regression.metrics import COMPARED_STATUSES, MATCH_ALL_STATUSES, compute
from mark_engine.regression.parity import classify
from mark_engine.rules.ruleset import RuleSet


def load_r0_csv(path: Path) -> dict[tuple[str, str, int], dict[str, str]]:
    """Loads R0 CSV file into a dict keyed by (elr_no, side, line_no)."""
    result: dict[tuple[str, str, int], dict[str, str]] = {}
    if not path.is_file():
        return result
    with open(path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            elr = r.get("elr_no", "").strip()
            side = r.get("side", "").strip().upper()
            try:
                line_no = int(r.get("line_no", 0))
            except ValueError:
                line_no = 0
            if elr and side and line_no:
                result[(elr, side, line_no)] = r
    return result


def load_r0_reocr(root: Path) -> set[tuple[str, str, int]]:
    """(elr_no, side, line_no) whose R0 text came from ocr_reocr.csv (kept == 'Y').

    Keys are either ``<image stem>|<SIDE>|<line>`` (May-Jun, images in dataset/eval_h1) or
    ``<image_id>_TL<n>`` / ``_BL<n>`` (Jan-Apr, images in full_images / eval_4_apr).
    """
    out: set[tuple[str, str, int]] = set()
    reocr = root / "experiments" / "abs_vs_db" / "out" / "ocr_reocr.csv"
    if not reocr.is_file():
        return out
    img_to_elrs: dict[str, set[str]] = {}
    h1 = root / "dataset" / "eval_h1" / "images_index.csv"
    if h1.is_file():
        for r in csv.DictReader(open(h1, encoding="utf-8-sig")):
            img_to_elrs.setdefault(Path(r["image"]).stem, set()).add(r["elr"].strip().upper())
    for idx in (root / "dataset" / "full_images" / "images_index.csv", root / "dataset" / "eval_4_apr" / "images_index.csv"):
        if not idx.is_file():
            continue
        for r in csv.DictReader(open(idx, encoding="utf-8-sig")):
            srcs = [x for x in (r.get("source_pdfs", "") or "").split(";")]
            srcs += [r.get("source_test_file", ""), r.get("source_train_file", "")]
            for src in srcs:
                if "__" in src:
                    img_to_elrs.setdefault(r["image_id"].strip(), set()).add(src.split("__")[0].strip().upper())
    for r in csv.DictReader(open(reocr, encoding="utf-8-sig")):
        if (r.get("kept") or "").strip().upper() != "Y":
            continue
        key = r["key"].strip()
        if "|" in key:
            img, side, line = key.split("|")
        else:
            m = re.match(r"^(.*)_([TB])L(\d+)$", key)
            if not m:
                continue
            img, side, line = m.group(1), "TOP" if m.group(2) == "T" else "BOTTOM", m.group(3)
        for elr in img_to_elrs.get(img, ()):
            out.add((elr, side.upper(), int(line)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run R1 regression and parity check vs R0")
    parser.add_argument(
        "--r0-root",
        type=Path,
        default=None,
        help="Path to R0 root repo (defaults to MARK_R0_ROOT or D:/CIM Project/mark)",
    )
    parser.add_argument(
        "--months",
        nargs="+",
        default=["1_JAN", "2_FEB", "3_MAR", "4_APR", "5_MAY", "6_JUN"],
        help="Month directories to scan",
    )
    parser.add_argument(
        "--elr-prefix",
        nargs="+",
        default=["ADI2601", "ADI2602", "ADI2603", "ADI2604", "ADI2605", "ADI2606"],
        help="ELR prefixes in scope",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/regression-r1"),
        help="Output directory for regression artifacts",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of worker threads",
    )

    args = parser.parse_args()

    root = args.r0_root if args.r0_root is not None else r0_root()
    print(f"[*] Verifying R0 root: {root}")
    verify_r0_root(root)

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    print("[*] Loading ruleset...")
    rules = RuleSet.load()

    meta_json_path = root / "experiments" / "abs_vs_db" / "out" / "elr_meta_2026.json"
    print(f"[*] Loading ELR snapshot: {meta_json_path}")
    snapshot = load_elr_snapshot(meta_json_path)

    r0_line_result_path = WORKSPACE_ROOT / "artifacts" / "regression-r0" / "mark_logic" / "line_result.csv"
    r0legacy_path = WORKSPACE_ROOT / "artifacts" / "regression-r0" / "line_result_run2_529elr.csv"

    print(f"[*] Loading R0 run 3: {r0_line_result_path}")
    r0_data = load_r0_csv(r0_line_result_path)

    print(f"[*] Loading R0 run 2: {r0legacy_path}")
    r0legacy_data = load_r0_csv(r0legacy_path)
    r0_reocr = load_r0_reocr(root)
    print(f"[*] R0 re-OCR lines (kept=Y): {len(r0_reocr)}")

    prefixes = tuple(args.elr_prefix)
    in_scope_items = [
        (meta, oracle)
        for elr, (meta, oracle) in snapshot.items()
        if any(elr.startswith(p) for p in prefixes)
    ]
    print(f"[*] Total in-scope ELRs to process: {len(in_scope_items)}")

    def run_one(item: tuple) -> tuple[JobResult, JobResult]:
        meta, oracle = item
        job_work = work_dir / meta.elr_no
        job = process_elr(meta, oracle, root, args.months, job_work, rules, load_inference)
        # Independence check (D-03): same ELR again with a blank OracleMark. The ExpectedMark
        # must be identical, otherwise generate depends on Oracle TOP/BACK_MARK.
        blank = process_elr(
            meta, OracleMark(meta.elr_no, ()), root, args.months, job_work, rules, load_inference
        )
        return job, blank

    print(f"[*] Running pipeline (+ blank-Oracle re-run) with {args.workers} workers...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pairs = list(executor.map(run_one, in_scope_items))
    jobs = [p[0] for p in pairs]
    blank_jobs = [p[1] for p in pairs]
    leaks = sorted(j.elr_no for j, b in pairs if j.expected != b.expected)
    if leaks:
        print(f"[!] Independence leak in {len(leaks)} ELR(s): {', '.join(leaks[:20])}")

    # Sort jobs by elr_no
    jobs.sort(key=lambda j: j.elr_no)
    print(f"[*] Finished processing {len(jobs)} jobs.")

    # 1. Compute Metrics
    print("[*] Computing regression metrics...")
    metrics = compute(jobs, snapshot, prefixes, blank_jobs=blank_jobs)

    # 2. Write metrics.json
    metrics_path = out_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"[+] Wrote metrics to {metrics_path}")

    # 3. Write lines.csv and build parity data
    lines_csv_path = out_dir / "lines.csv"
    parity_csv_path = out_dir / "parity.csv"
    parity_summary: dict[str, int] = {}

    lines_rows: list[dict[str, Any]] = []
    parity_rows: list[dict[str, Any]] = []

    for job in jobs:
        layout_source = job.layout_source
        abs_no = ""
        abs_other_revisions = ""
        hold_detail = (job.resolution.hold_detail or "") if job.resolution else ""
        if job.resolution and job.resolution.abs:
            abs_no = Path(job.resolution.abs.path).stem
            abs_other_revisions = ";".join(
                sorted(Path(ref.path).stem for ref, why in job.resolution.rejected if why == "REVISION_SUPERSEDED")
            )

        for c in job.comparisons:
            expected_str = c.expected or ""
            oracle_str = c.oracle or ""
            exp_line = job.expected.line(c.side, c.line_no) if job.expected else None
            c_flags = ";".join(sorted(f.value for f in exp_line.flags)) if exp_line and exp_line.flags else ""
            c_rules = ";".join(c.compare_rules)

            r1_line_dict = {
                "elr_no": job.elr_no,
                "side": c.side.value if hasattr(c.side, "value") else str(c.side),
                "line_no": c.line_no,
                "layout_source": layout_source,
                "expected_mark": expected_str,
                "oracle_mark": oracle_str,
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "flags": c_flags,
                "compare_rules": c_rules,
                "detail": c.detail,
                "warning": c.warning,
                "processing_status": job.processing_status.value,
                "hold_reason": job.hold_reason or "",
                "hold_detail": hold_detail,
                "abs_no": abs_no,
                "abs_other_revisions": abs_other_revisions,
                "r0_reocr": "Y" if (job.elr_no, c.side.value, c.line_no) in r0_reocr else "",
            }
            lines_rows.append(r1_line_dict)

            # Parity check against R0
            k = (job.elr_no, r1_line_dict["side"], c.line_no)
            r0_row = r0_data.get(k)
            r0legacy_row = r0legacy_data.get(k)

            reason = classify(r1_line_dict, r0_row, r0legacy_row)
            parity_summary[reason] = parity_summary.get(reason, 0) + 1

            parity_rows.append({
                "elr_no": job.elr_no,
                "side": r1_line_dict["side"],
                "line_no": c.line_no,
                "r1_status": r1_line_dict["status"],
                "r1_expected": expected_str,
                "r0_status": r0_row.get("status", "") if r0_row else "",
                "r0_final": r0_row.get("final_mark", "") if r0_row else "",
                "r0_cause": r0_row.get("cause", "") if r0_row else "",
                "reason": reason,
                "detail": c.detail,
            })

    # Write lines.csv
    lines_fieldnames = [
        "elr_no",
        "side",
        "line_no",
        "layout_source",
        "expected_mark",
        "oracle_mark",
        "status",
        "flags",
        "compare_rules",
        "detail",
        "warning",
        "processing_status",
        "hold_reason",
        "hold_detail",
    ]
    with open(lines_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=lines_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(lines_rows)
    print(f"[+] Wrote {len(lines_rows)} line comparisons to {lines_csv_path}")

    # Write parity.csv
    parity_fieldnames = [
        "elr_no",
        "side",
        "line_no",
        "r1_status",
        "r1_expected",
        "r0_status",
        "r0_final",
        "r0_cause",
        "reason",
        "detail",
    ]
    with open(parity_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=parity_fieldnames)
        writer.writeheader()
        writer.writerows(parity_rows)
    print(f"[+] Wrote {len(parity_rows)} parity rows to {parity_csv_path}")

    # Write parity_summary.json
    parity_summary_path = out_dir / "parity_summary.json"
    with open(parity_summary_path, "w", encoding="utf-8") as f:
        json.dump(parity_summary, f, indent=2)
    print(f"[+] Wrote parity summary to {parity_summary_path}")

    # 4. Write jobs.csv
    jobs_csv_path = out_dir / "jobs.csv"
    jobs_rows: list[dict[str, Any]] = []
    for job in jobs:
        layout_source = job.layout_source
        abs_no = ""
        if job.resolution and job.resolution.abs:
            abs_no = Path(job.resolution.abs.path).stem

        total_lines = len(job.comparisons)
        compared = sum(1 for c in job.comparisons if c.status in COMPARED_STATUSES)
        match_l = sum(1 for c in job.comparisons if c.status in MATCH_ALL_STATUSES)
        diff_l = sum(1 for c in job.comparisons if c.status == LineStatus.DIFF)
        review_l = sum(1 for c in job.comparisons if c.status == LineStatus.NEEDS_REVIEW)

        jobs_rows.append({
            "elr_no": job.elr_no,
            "processing_status": job.processing_status.value,
            "hold_reason": job.hold_reason or "",
            "hold_detail": (job.resolution.hold_detail or "") if job.resolution else "",
            "verification_status": job.verification_status.value if job.verification_status else "",
            "approval_status": job.approval_status.value,
            "layout_source": layout_source,
            "abs_no": abs_no,
            "total_lines": total_lines,
            "compared_lines": compared,
            "match_lines": match_l,
            "diff_lines": diff_l,
            "needs_review_lines": review_l,
        })

    jobs_fieldnames = [
        "elr_no",
        "processing_status",
        "hold_reason",
        "hold_detail",
        "verification_status",
        "approval_status",
        "layout_source",
        "abs_no",
        "total_lines",
        "compared_lines",
        "match_lines",
        "diff_lines",
        "needs_review_lines",
    ]
    with open(jobs_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=jobs_fieldnames)
        writer.writeheader()
        writer.writerows(jobs_rows)
    print(f"[+] Wrote {len(jobs_rows)} jobs to {jobs_csv_path}")

    # Print summary
    print("\n=================== REGRESSION R1 SUMMARY ===================")
    print(f"Total ELRs:             {metrics['total_jobs']}")
    print(f"Coverage ELR:           {metrics['coverage_elr']:.2%} ({metrics['coverage_elr_num']}/{metrics['coverage_elr_denom']})")
    print(f"Coverage Line:          {metrics['coverage_line']:.2%} ({metrics['coverage_line_num']}/{metrics['coverage_line_denom']})")
    print(f"Hold Rate:              {metrics['hold_rate']:.2%} ({metrics['hold_count']}/{metrics['total_jobs']})")
    print(f"Oracle Agreement:       {metrics['oracle_agreement']:.2%} ({metrics['oracle_agreement_num']}/{metrics['oracle_agreement_denom']})")
    ind = metrics["independence"]
    print(f"Independence:           {'NOT MEASURED' if ind is None else f'{ind:.2%}'}")
    print(f"Needs Review Lines:     {metrics['needs_review_lines']}")
    print(f"Warning Lines (MATCH):  {metrics['warning_lines']}")
    print("Status counts:")
    for st, cnt in metrics["status_counts"].items():
        if cnt > 0:
            print(f"  {st:16s}: {cnt}")
    print("\nParity breakdown vs R0:")
    for reason, count in sorted(parity_summary.items(), key=lambda x: -x[1]):
        print(f"  {reason:26s}: {count}")
    print("============================================================\n")


if __name__ == "__main__":
    main()
