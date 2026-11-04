import re
from pathlib import Path
import pymupdf

from mark_engine.domain.models import DocType


def classify(pdf: Path) -> tuple[DocType, str | None]:
    """Classify a PDF as ABS, SLR, TRS, or OTHER based on content markers and metadata.

    Returns:
      (DocType, doc_number | "AMBIGUOUS" | None)
    """
    doc = pymupdf.open(str(pdf))
    num_pages = len(doc)

    # Read text of pages 1-2 (0-indexed 0, 1)
    pages_1_2 = [doc[i].get_text() for i in range(min(2, num_pages))]
    text_1_2 = "\n".join(pages_1_2)

    # 1. TRS markers: Test Requirement or \bTRS\d+
    is_trs = bool(re.search(r"Test Requirement|\bTRS\d+", text_1_2, re.IGNORECASE))
    if not is_trs and num_pages > 2:
        for i in range(2, num_pages):
            if re.search(r"Test Requirement|\bTRS\d+", doc[i].get_text(), re.IGNORECASE):
                is_trs = True
                break

    # 2. SLR markers: SPECIAL INSTRUCTIONS or Scheduled Lot ID
    has_slr = bool(re.search(r"SPECIAL INSTRUCTIONS|Scheduled Lot ID", text_1_2, re.IGNORECASE))
    if not has_slr and num_pages > 2:
        for i in range(2, num_pages):
            if re.search(r"SPECIAL INSTRUCTIONS|Scheduled Lot ID", doc[i].get_text(), re.IGNORECASE):
                has_slr = True
                break

    # 3. ABS markers: ABS\d{6} in text AND any page has "Brand/Marking"
    has_abs_num = bool(re.search(r"\bABS\d{6}\b", text_1_2))
    if not has_abs_num and num_pages > 2:
        for i in range(2, num_pages):
            if re.search(r"\bABS\d{6}\b", doc[i].get_text()):
                has_abs_num = True
                break

    has_brand_marking = False
    for page in doc:
        page_text = page.get_text()
        if re.search(r"Brand\s*/\s*Marking", page_text, re.IGNORECASE):
            has_brand_marking = True
            break

    has_abs = has_abs_num and has_brand_marking

    doc.close()

    # Content-based classification
    if is_trs:
        doc_type = DocType.TRS
    elif has_abs and has_slr:
        return (DocType.OTHER, "AMBIGUOUS")
    elif has_abs:
        doc_type = DocType.ABS
    elif has_slr:
        doc_type = DocType.SLR
    else:
        doc_type = DocType.OTHER

    # Doc number: first match of ABS\d{6} or SLR\d{6} in text,
    # fallback to filename stem if matches regex (ABS\d{6}|SLR\d{6})
    num_match = re.search(r"\b(ABS\d{6}|SLR\d{6})\b", text_1_2)
    if not num_match and doc_type == DocType.TRS:
        trs_match = re.search(r"\b(TRS\d+)\b", text_1_2)
        if trs_match:
            return (doc_type, trs_match.group(1))

    if num_match:
        doc_number = num_match.group(1)
    else:
        stem_match = re.search(r"(ABS\d{6}|SLR\d{6})", pdf.stem)
        if stem_match:
            doc_number = stem_match.group(1)
        else:
            doc_number = None

    return (doc_type, doc_number)
