from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
import openpyxl

EXPECTED_SHA256 = "7858dc405a90b6600389accf32fa257ad23580cd532cda078da2f02cfe74ccb6"

ALIAS = {
    "•": "pin1 dot",
    "<": "pin1 ˂",
    "v": "pin1 ˅",
    "—": "pin1 dash",
    "e3": "e3",
    "ve3^": "e3-rotate ccw 90*",
    "logo": "partial ltc logo",
    "ltc-partial-logo": "ltc-partial-logo",
    "space": None,
    "factorycode": "1 character factory code",
    "cc": "cc",
}


def build_encoder_data(r0_root: Path | None = None, out_dir: Path | None = None) -> None:
    if r0_root is None:
        r0_root = Path(os.environ.get("MARK_R0_ROOT", r"D:\CIM Project\mark"))
    if out_dir is None:
        out_dir = Path(__file__).resolve().parent.parent / "mark_engine" / "encode" / "data"

    out_dir.mkdir(parents=True, exist_ok=True)

    excel_path = r0_root / "Symbol ADI.xlsx"
    if not excel_path.is_file():
        raise FileNotFoundError(f"Symbol ADI.xlsx not found at: {excel_path}")

    with excel_path.open("rb") as f:
        file_sha256 = hashlib.sha256(f.read()).hexdigest()

    if file_sha256 != EXPECTED_SHA256:
        raise ValueError(
            f"Symbol ADI.xlsx sha256 mismatch: got {file_sha256}, expected {EXPECTED_SHA256}"
        )

    wb = openpyxl.load_workbook(str(excel_path), data_only=True)
    sym: dict[str, str] = {}
    for r in wb["Summary"].iter_rows(min_row=3, values_only=True):
        if len(r) > 4 and r[1] == "ADI" and r[3] is not None and r[4] is not None:
            norm_key = re.sub(r"\s+", " ", str(r[3]).strip("{} ")).lower()
            val = str(r[4]).replace(" (UTL)", "")
            sym[norm_key] = val

    # Merge aliases
    for k, target in ALIAS.items():
        if target is None:
            sym[k] = sym.get("space character", " ")
        elif target in sym:
            sym[k] = sym[target]

    json_path = out_dir / "symbol_adi_r0.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(dict(sorted(sym.items())), f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Copy adi1039_tokens.csv
    src_csv = r0_root / "experiments" / "abs_vs_db" / "adi1039_tokens.csv"
    if not src_csv.is_file():
        raise FileNotFoundError(f"adi1039_tokens.csv not found at: {src_csv}")

    dst_csv = out_dir / "adi1039_tokens.csv"
    shutil.copyfile(src_csv, dst_csv)

    with dst_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 42, f"Expected 42 rows in adi1039_tokens.csv, found {len(rows)}"

    print(f"Wrote {len(sym)} symbols to {json_path}")
    print(f"Copied {len(rows)} rows to {dst_csv}")


if __name__ == "__main__":
    build_encoder_data()
