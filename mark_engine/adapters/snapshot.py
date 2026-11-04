import csv
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from mark_engine.abs.layout import layout_lines
from mark_engine.abs.symbols_to_lines import assign_graphics
from mark_engine.domain.models import ElrMeta, InferenceResult, LayoutLine, OracleMark, Side


def _clean_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def load_elr_snapshot(path: Path) -> dict[str, tuple[ElrMeta, OracleMark]]:
    """Loads ELR snapshot rows from a JSON file into (ElrMeta, OracleMark) tuples.
    
    Returns a dict mapping ELR number (str) to (ElrMeta, OracleMark).
    """
    with open(path, "r", encoding="utf-8") as f:
        rows: list[dict[str, Any]] = json.load(f)

    result: dict[str, tuple[ElrMeta, OracleMark]] = {}

    for row in rows:
        # Standardize keys to uppercase for robust lookup
        upper_row = {k.upper(): v for k, v in row.items()}

        raw_elr_no = upper_row.get("ELR_NO")
        if raw_elr_no is None:
            continue
        elr_no = str(raw_elr_no).strip()

        meta = ElrMeta(
            elr_no=elr_no,
            import_date=_clean_str(upper_row.get("IMPORT_DATE")),
            status=_clean_str(upper_row.get("STATUS")),
            current_step=_clean_str(upper_row.get("CURRENT_STEP")),
            cust_bom_no=_clean_str(upper_row.get("CUST_BOM_NO")),
            cust_bom_revision=_clean_str(upper_row.get("CUST_BOM_REVISION")),
            cust_req_no=_clean_str(upper_row.get("CUST_REQ_NO")),
            cust_assy_lot=_clean_str(upper_row.get("CUST_ASSY_LOT")),
            product_no=_clean_str(upper_row.get("PRODUCT_NO")),
            package_code=_clean_str(upper_row.get("PACKAGE_CODE")),
            mark_remark=_clean_str(upper_row.get("MARK_REMARK")),
            mark_require=_clean_str(upper_row.get("MARK_REQUIRE")),
            top_type_code=_clean_str(upper_row.get("TOP_TYPE_CODE")),
            top_layout_code=_clean_str(upper_row.get("TOP_LAYOUT_CODE")),
        )

        lines: list[tuple[Side, int, str]] = []
        for i in range(1, 6):
            val = upper_row.get(f"TOP_MARK{i}")
            if val is not None:
                cleaned = str(val).strip()
                if cleaned:
                    lines.append((Side.TOP, i, cleaned))

        for i in range(1, 6):
            val = upper_row.get(f"BACK_MARK{i}")
            if val is not None:
                cleaned = str(val).strip()
                if cleaned:
                    lines.append((Side.BOTTOM, i, cleaned))

        oracle_mark = OracleMark(elr_no=elr_no, lines=tuple(lines))
        result[elr_no] = (meta, oracle_mark)

    return result


def r0_root() -> Path:
    """Returns the R0 root path from MARK_R0_ROOT or default D:/CIM Project/mark."""
    env = os.environ.get("MARK_R0_ROOT")
    if env:
        return Path(env)
    return Path("D:/CIM Project/mark")


def verify_r0_root(root: Path) -> None:
    """Verifies that R0 root exists and has no uncommitted changes on experiments."""
    if not root.is_dir():
        raise RuntimeError(f"R0 root directory does not exist: {root}")

    cmd = ["git", "-C", str(root), "diff", "--quiet", "regression-r0-2026-11-04", "--", "experiments"]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"R0 root {root} has git diff against regression-r0-2026-11-04 on experiments (exit code {proc.returncode})"
        )


def load_inference(root: Path, elr_no: str, abs_file_stem: str) -> InferenceResult:
    """Loads inference result (OCR layout + graphic tokens) for an ELR and ABS drawing.

    Supports May-Jun (auto layout from h1_det_rec + YOLO detections_h1)
    and Jan-Apr (human-crop annotation + ocr_preds + graphics_by_line).
    Returns InferenceResult with layout_source 'auto', 'human_crop', or 'none'.
    """
    clean_elr = elr_no.strip()
    abs_clean = abs_file_stem.strip().removesuffix(".pdf").removesuffix(".PDF")

    # 1. May-Jun check
    eval_h1_idx = root / "dataset" / "eval_h1" / "images_index.csv"
    if eval_h1_idx.is_file():
        matched_image: str | None = None
        with open(eval_h1_idx, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("elr", "").strip().upper() == clean_elr.upper():
                    r_abs = r.get("abs_file", "").strip()
                    if not abs_clean or r_abs == abs_clean or r_abs.startswith(abs_clean) or abs_clean.startswith(r_abs):
                        matched_image = r.get("image", "").strip()
                        break

        if matched_image:
            img_stem = Path(matched_image).stem
            det_rec_path = root / "experiments" / "abs_vs_db" / "out" / "h1_det_rec.json"
            detections_path = root / "experiments" / "symbol_det" / "detections_h1.json"

            items: list[Any] = []
            if det_rec_path.is_file():
                with open(det_rec_path, encoding="utf-8") as f:
                    dr_data = json.load(f)
                    items = dr_data.get(matched_image) or dr_data.get(f"{img_stem}.png") or dr_data.get(img_stem) or []

            detections: list[Any] = []
            if detections_path.is_file():
                with open(detections_path, encoding="utf-8") as f:
                    det_data = json.load(f)
                    detections = det_data.get(img_stem) or det_data.get(matched_image) or []

            lines = layout_lines(items)
            gfx = assign_graphics(lines, detections)

            lines_by_key = {(s, n): (txt, sc) for s, n, txt, sc, bb in lines}
            all_keys = sorted(
                set(lines_by_key.keys()) | set(gfx.keys()),
                key=lambda k: (0 if k[0] == Side.TOP else 1, k[1]),
            )
            layout_lines_result = tuple(
                LayoutLine(
                    side=s,
                    line_no=n,
                    text=lines_by_key.get((s, n), ("", None))[0],
                    graphics=gfx.get((s, n), ""),
                    score=lines_by_key.get((s, n), ("", None))[1],
                )
                for s, n in all_keys
            )
            return InferenceResult(elr_no=clean_elr, lines=layout_lines_result, layout_source="auto")

    # 2. Jan-Apr check
    jan_apr_files = [
        root / "dataset" / "full_images" / "images_index.csv",
        root / "dataset" / "eval_4_apr" / "images_index.csv",
    ]
    matched_image_id: str | None = None
    matched_image_stem: str | None = None

    for idx_path in jan_apr_files:
        if not idx_path.is_file():
            continue
        with open(idx_path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                candidates: list[str] = []
                if "source_pdfs" in r:
                    candidates.extend(s.strip() for s in r["source_pdfs"].split(";") if s.strip())
                for col in ["source_test_file", "source_train_file"]:
                    val = r.get(col, "").strip()
                    if val and val != "NO":
                        candidates.append(val)

                for c in candidates:
                    c_elr = c.split("__")[0].strip() if "__" in c else ""
                    if c_elr.upper() == clean_elr.upper():
                        matched_image_id = r.get("image_id", "").strip()
                        matched_image_stem = Path(r.get("file", "").strip()).stem
                        if not abs_clean or abs_clean in c or abs_clean in r.get("abs_revisions", ""):
                            break
                if matched_image_id and (
                    not abs_clean or abs_clean in str(candidates) or abs_clean in r.get("abs_revisions", "")
                ):
                    break
        if matched_image_id:
            break

    if matched_image_id and matched_image_stem:
        annotation_paths = [
            root / "dataset" / "annotation.csv",
            root / "dataset" / "eval_4_apr" / "annotation_v1.1.csv",
        ]
        ann_rows: list[dict[str, str]] = []
        for ap in annotation_paths:
            if ap.is_file():
                with open(ap, encoding="utf-8-sig") as f:
                    for r in csv.DictReader(f):
                        if r.get("image_id", "").strip() == matched_image_id:
                            ann_rows.append(r)

        ocr_preds: dict[str, dict[str, Any]] = {}
        ocr_preds_path = root / "experiments" / "abs_vs_db" / "out" / "ocr_preds.csv"
        if ocr_preds_path.is_file():
            with open(ocr_preds_path, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    ocr_preds[r["sample_id"]] = r

        graphics_map: dict[tuple[Side, int], str] = {}
        graphics_path = root / "experiments" / "symbol_det" / "graphics_by_line.csv"
        if graphics_path.is_file():
            with open(graphics_path, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    img_key = r.get("image", "").strip()
                    if img_key in (matched_image_stem, matched_image_id):
                        s = Side.TOP if r.get("side", "").strip().upper() == "TOP" else Side.BOTTOM
                        try:
                            ln = int(r.get("line", "0"))
                        except ValueError:
                            ln = 0
                        if ln >= 1:
                            graphics_map[(s, ln)] = r.get("tokens", "")

        lines_dict: dict[tuple[Side, int], dict[str, Any]] = {}
        for r in ann_rows:
            side_str = r.get("side", "").strip().upper()
            s = Side.TOP if side_str == "TOP" else Side.BOTTOM
            raw_ln = re.sub(r"\D", "", r.get("line_index", ""))
            try:
                line_no = int(raw_ln) if raw_ln else 0
            except ValueError:
                line_no = 0
            if line_no < 1:
                continue

            sid = r.get("sample_id", "")
            ocr_info = ocr_preds.get(sid, {})
            text = ocr_info.get("ocr_text", "")
            sc_raw = ocr_info.get("ocr_score")
            score = float(sc_raw) if sc_raw else None

            lines_dict[(s, line_no)] = {
                "text": text,
                "score": score,
                "graphics": graphics_map.get((s, line_no), ""),
            }

        for (s, ln), toks in graphics_map.items():
            if (s, ln) not in lines_dict:
                lines_dict[(s, ln)] = {
                    "text": "",
                    "score": None,
                    "graphics": toks,
                }

        sorted_lines = tuple(
            LayoutLine(
                side=s,
                line_no=n,
                text=info["text"],
                graphics=info["graphics"],
                score=info["score"],
            )
            for (s, n), info in sorted(
                lines_dict.items(),
                key=lambda k: (0 if k[0][0] == Side.TOP else 1, k[0][1]),
            )
        )
        return InferenceResult(elr_no=clean_elr, lines=sorted_lines, layout_source="human_crop")

    return InferenceResult(elr_no=clean_elr, lines=(), layout_source="none")
