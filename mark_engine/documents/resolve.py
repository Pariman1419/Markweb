import re
import zipfile
from pathlib import Path
from typing import Sequence
import pymupdf

from mark_engine.domain.models import DocType, DocumentRef, DocumentResolution, ElrMeta
from mark_engine.documents.classify import classify
from mark_engine.documents.fingerprint import fingerprint_folder
from mark_engine.documents.locate import find_elr_folders
from mark_engine.slr.parse import parse_slr


def extract_abs_revision(filename_stem: str) -> str | None:
    """Extract revision suffix from an ABS filename stem.

    Examples:
      ABS066973-ENG-1 -> ENG-1
      ABS067185B -> B
      ABS067185-A -> A
      ABS067185_ENG-2 -> ENG-2
      ABS067185 -> None
    """
    m = re.search(r"ABS\d{6}[-_]?(.*)$", filename_stem, re.IGNORECASE)
    if not m:
        return None
    suffix = m.group(1).strip().lstrip("-_ ")
    return suffix if suffix else None


def _norm_rev(rev: str | None) -> str | None:
    if not rev:
        return None
    r = rev.strip().lstrip("-_ ").upper()
    return r if r else None


_LETTER_REV_RE = re.compile(r"[A-Z]{1,2}")


def _oracle_revision(bom_no: str | None, bom_rev: str | None) -> str | None:
    """Full ABS revision as Oracle records it.

    Oracle may split it: CUST_BOM_NO 'ABS034529D' + CUST_BOM_REVISION 'ENG-1' = 'D-ENG-1', the
    same revision as the file ABS034529D-ENG-1 (user-confirmed 2026-11-04, ADI2602100).
    """
    rev = _norm_rev(bom_rev)
    m = re.search(r"\d{6}([A-Z]{1,2})$", (bom_no or "").strip().upper())
    if m and rev and not rev.startswith(m.group(1) + "-"):
        return f"{m.group(1)}-{rev}"
    return rev


def _product_no_revision(product_no: str | None, bom: str) -> str | None:
    """Letter revision written after the ABS number in PRODUCT_NO (…-ABS068387C-A -> C)."""
    m6 = re.search(r"\d{6}", bom or "")
    if not product_no or not m6:
        return None
    m = re.search(rf"ABS{m6.group(0)}([A-Z]{{1,2}})(?=-|$)", product_no.strip().upper())
    return m.group(1) if m else None


def _matches_bom(ref: DocumentRef, bom_str: str) -> bool:
    clean = bom_str.strip().upper()
    m = re.search(r"\d{6}", clean)
    if m:
        digits = m.group(0)
        target = f"ABS{digits}"
        if ref.number and ref.number.upper() == target:
            return True
        p_name = Path(ref.path).name.upper()
        if target in p_name:
            return True
        return False
    return bool(ref.number and ref.number.upper() == clean)


def _matches_req_no(ref: DocumentRef, req_no: str) -> bool:
    r = req_no.strip().upper()
    if ref.number and ref.number.upper() == r:
        return True
    p_name = Path(ref.path).name.upper()
    if r in p_name:
        return True
    return False


def resolve_documents(
    meta: ElrMeta,
    root: Path,
    months: Sequence[str],
    work_dir: Path,
) -> DocumentResolution:
    """Resolve ABS and SLR documents for a given ELR metadata from NAS storage.

    Pure deterministic resolver with zero OracleMark dependency.
    """
    steps: list[str] = []
    rejected: list[tuple[DocumentRef, str]] = []

    # 1. Locate folder
    folders = find_elr_folders(root, meta.elr_no, months)
    if not folders:
        return DocumentResolution(
            elr_no=meta.elr_no,
            decision="HOLD",
            hold_reason="NO_FOLDER",
            abs=None,
            slr=(),
            rejected=(),
            steps=tuple(steps),
        )

    # Sort deterministically: exact match first, then alphabetically
    folders_sorted = sorted(folders, key=lambda f: (0 if f[1] == "exact" else 1, str(f[0])))
    target_folder, kind = folders_sorted[0]
    if kind == "annotated":
        steps.append("FOLDER_ANNOTATED")

    # 2. Fingerprint
    extract_dir = work_dir / meta.elr_no / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        fingerprinted = fingerprint_folder(target_folder, extract_dir)
    except (ValueError, zipfile.BadZipFile, OSError):
        return DocumentResolution(
            elr_no=meta.elr_no,
            decision="HOLD",
            hold_reason="ARCHIVE_ERROR",
            abs=None,
            slr=(),
            rejected=(),
            steps=tuple(steps),
        )

    # Sort candidates deterministically by sha256 and path
    fingerprinted = sorted(fingerprinted, key=lambda item: (item[1], str(item[0])))

    # 3. Classify each document
    abs_docs: list[DocumentRef] = []
    slr_docs: list[DocumentRef] = []

    for pdf_path, sha in fingerprinted:
        try:
            doc_type, doc_number = classify(pdf_path)
        except Exception:
            doc_type, doc_number = DocType.OTHER, None

        if doc_number == "AMBIGUOUS" or (doc_type == DocType.OTHER and doc_number == "AMBIGUOUS"):
            return DocumentResolution(
                elr_no=meta.elr_no,
                decision="HOLD",
                hold_reason="DOC_TYPE_AMBIGUOUS",
                abs=None,
                slr=(),
                rejected=(),
                steps=tuple(steps),
            )

        if doc_type == DocType.TRS:
            return DocumentResolution(
                elr_no=meta.elr_no,
                decision="HOLD",
                hold_reason="TRS_OUT_OF_SCOPE",
                abs=None,
                slr=(),
                rejected=(),
                steps=tuple(steps),
            )

        if doc_type == DocType.ABS:
            rev = extract_abs_revision(pdf_path.stem)
            abs_docs.append(
                DocumentRef(
                    path=str(pdf_path),
                    sha256=sha,
                    doc_type=DocType.ABS,
                    number=doc_number,
                    revision=rev,
                    revision_source="filename" if rev is not None else None,
                )
            )
        elif doc_type == DocType.SLR:
            slr_docs.append(
                DocumentRef(
                    path=str(pdf_path),
                    sha256=sha,
                    doc_type=DocType.SLR,
                    number=doc_number,
                    revision=None,
                    revision_source=None,
                )
            )
        else:
            other_ref = DocumentRef(
                path=str(pdf_path),
                sha256=sha,
                doc_type=doc_type,
                number=doc_number,
                revision=None,
                revision_source=None,
            )
            rejected.append((other_ref, "OTHER_DOC_TYPE"))

    # 4. Check BOM in Oracle metadata
    bom_clean = meta.cust_bom_no.strip() if meta.cust_bom_no else ""
    if not bom_clean or bom_clean.upper() in ("N/A", "NONE"):
        return DocumentResolution(
            elr_no=meta.elr_no,
            decision="HOLD",
            hold_reason="BOM_MISSING_IN_ORACLE",
            abs=None,
            slr=(),
            rejected=tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1]))),
            steps=tuple(steps),
        )

    # Filter ABS docs matching cust_bom_no
    matching_abs: list[DocumentRef] = []
    for ref in abs_docs:
        if _matches_bom(ref, bom_clean):
            matching_abs.append(ref)
        else:
            rejected.append((ref, "BOM_MISMATCH"))

    if not matching_abs:
        return DocumentResolution(
            elr_no=meta.elr_no,
            decision="HOLD",
            hold_reason="BOM_NOT_FOUND",
            abs=None,
            slr=(),
            rejected=tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1]))),
            steps=tuple(steps),
        )

    # 5. Revision Resolution for ABS
    oracle_rev = _oracle_revision(meta.cust_bom_no, meta.cust_bom_revision)

    # 5a. REVISION_CONFLICT (Mark Eng 2026-11-04, 09 Q2): PRODUCT_NO carries the ABS revision
    #     (ADMFS7201-ABS068387C-A). If it is a plain letter revision that differs from
    #     CUST_BOM_REVISION, do not guess which one is right: hold for review with the cause.
    pn_rev = _product_no_revision(meta.product_no, bom_clean)
    if (
        pn_rev is not None
        and oracle_rev is not None
        and _LETTER_REV_RE.fullmatch(oracle_rev)
        and pn_rev != oracle_rev
    ):
        return DocumentResolution(
            elr_no=meta.elr_no,
            decision="HOLD",
            hold_reason="REVISION_CONFLICT",
            abs=None,
            slr=(),
            rejected=tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1]))),
            steps=tuple(steps),
            hold_detail=(
                f"CUST_BOM_REVISION={oracle_rev} but PRODUCT_NO {meta.product_no.strip()} has rev {pn_rev}"
            ),
        )

    # Check for SAME_REV_DIFFERENT_CONTENT: multiple ABS with same revision but different sha256
    rev_groups: dict[str | None, list[DocumentRef]] = {}
    for ref in matching_abs:
        nr = _norm_rev(ref.revision)
        rev_groups.setdefault(nr, []).append(ref)

    for rev_key, group in rev_groups.items():
        if len({ref.sha256 for ref in group}) > 1:
            return DocumentResolution(
                elr_no=meta.elr_no,
                decision="HOLD",
                hold_reason="SAME_REV_DIFFERENT_CONTENT",
                abs=None,
                slr=(),
                rejected=tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1]))),
                steps=tuple(steps),
            )

    chosen_abs: DocumentRef | None = None
    if oracle_rev is not None:
        matching_rev = [ref for ref in matching_abs if _norm_rev(ref.revision) == oracle_rev]
        if matching_rev:
            chosen_abs = matching_rev[0]
            for ref in matching_abs:
                if ref != chosen_abs:
                    rejected.append((ref, "REVISION_SUPERSEDED"))

    if chosen_abs is None:
        if len(matching_abs) == 1:
            chosen_abs = matching_abs[0]
            steps.append("REVISION_NAME_MISMATCH")
        else:
            # > 1 ABS found for BOM, none matches cust_bom_revision
            return DocumentResolution(
                elr_no=meta.elr_no,
                decision="HOLD",
                hold_reason="REVISION_UNREADABLE",
                abs=None,
                slr=(),
                rejected=tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1]))),
                steps=tuple(steps),
            )

    # 6. SLR Resolution
    req_no_clean = meta.cust_req_no.strip() if meta.cust_req_no else ""
    if req_no_clean.upper() in ("N/A", "NONE"):
        req_no_clean = ""

    matching_slrs: list[DocumentRef] = []
    if req_no_clean:
        for ref in slr_docs:
            if _matches_req_no(ref, req_no_clean):
                matching_slrs.append(ref)
            else:
                rejected.append((ref, "REQ_NO_MISMATCH"))
    else:
        matching_slrs = list(slr_docs)

    if not matching_slrs:
        return DocumentResolution(
            elr_no=meta.elr_no,
            decision="HOLD",
            hold_reason="SLR_NOT_FOUND",
            abs=None,
            slr=(),
            rejected=tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1]))),
            steps=tuple(steps),
        )

    if len(matching_slrs) > 1:
        # Check conflict across SLRs
        slr_facts_list = []
        for ref in matching_slrs:
            doc = pymupdf.open(ref.path)
            full_text = "\n".join(page.get_text() for page in doc)
            doc.close()
            facts = parse_slr(full_text)
            slr_facts_list.append((ref, full_text, facts))

        has_conflict = False
        first_facts = slr_facts_list[0][2]
        first_text = slr_facts_list[0][1]

        for _, text_i, facts_i in slr_facts_list[1:]:
            if facts_i.instructions != first_facts.instructions:
                has_conflict = True
                break

        if has_conflict:
            return DocumentResolution(
                elr_no=meta.elr_no,
                decision="HOLD",
                hold_reason="SLR_CONFLICT",
                abs=None,
                slr=(),
                rejected=tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1]))),
                steps=tuple(steps),
            )
        else:
            steps.append("MERGED_IDENTICAL")

    # Sort final collections deterministically
    slr_tuple = tuple(sorted(matching_slrs, key=lambda r: (r.sha256, r.path)))
    rejected_tuple = tuple(sorted(rejected, key=lambda item: (item[0].sha256, item[0].path, item[1])))

    return DocumentResolution(
        elr_no=meta.elr_no,
        decision="RESOLVED",
        hold_reason=None,
        abs=chosen_abs,
        slr=slr_tuple,
        rejected=rejected_tuple,
        steps=tuple(steps),
    )
