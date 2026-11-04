from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path
from typing import Callable, Mapping, Sequence
import pymupdf

from mark_engine.compare.engine import compare
from mark_engine.documents.resolve import resolve_documents
from mark_engine.domain.models import (
    ApprovalStatus,
    ElrMeta,
    ExpectedLine,
    ExpectedToken,
    InferenceResult,
    JobResult,
    LineComparison,
    LineStatus,
    OracleMark,
    ProcessingStatus,
    SlrFacts,
    Side,
    VerificationStatus,
)
from mark_engine.encode.remark import is_skip_mark
from mark_engine.generate.generator import generate_expected
from mark_engine.generate.mark_layout import LayoutError, MarkLayout, fill_line_with_conflicts
from mark_engine.rules.ruleset import RuleSet
from mark_engine.slr.parse import parse_slr


def position_differs(expected: str, raw_oracle: str) -> bool:
    grid = raw_oracle[3:21].ljust(18)
    return tuple(not char.isspace() for char in expected.ljust(18)) != tuple(not char.isspace() for char in grid)


def _call_inference_loader(
    loader: Callable[[str, str], InferenceResult] | Callable[[Path, str, str], InferenceResult],
    root: Path,
    elr_no: str,
    abs_stem: str,
) -> InferenceResult:
    try:
        sig = inspect.signature(loader)
        pos_params = [
            p
            for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(pos_params) == 3:
            return loader(root, elr_no, abs_stem)  # type: ignore[call-arg]
        if len(pos_params) == 2:
            return loader(elr_no, abs_stem)  # type: ignore[call-arg]
    except (ValueError, TypeError):
        pass

    try:
        return loader(elr_no, abs_stem)  # type: ignore[call-arg]
    except TypeError:
        return loader(root, elr_no, abs_stem)  # type: ignore[call-arg]


def process_elr(
    meta: ElrMeta,
    oracle: OracleMark,
    root: Path,
    months: Sequence[str],
    work_dir: Path,
    rules: RuleSet,
    inference_loader: (
        Callable[[str, str], InferenceResult]
        | Callable[[Path, str, str], InferenceResult]
    ),
    *,
    layouts: Mapping[int, MarkLayout] | None = None,
    folder_index: dict[str, tuple[Path, ...]] | None = None,
    inference_validator: Callable[[str, Path, str], None] | None = None,
) -> JobResult:
    """Run full mark verification pipeline for a single ELR.

    Pipeline phases:
      1. Eligibility Gate (status, top_type_code, top_layout_code)
      2. Document Resolution Gate (resolve_documents)
      3. Skip Mark Gate (is_skip_mark)
      4. SLR Extraction (parse_slr)
      5. Inference Loading (inference_loader)
      6. Expected-Mark Generation (generate_expected) - strictly BEFORE reading oracle
      7. Comparison Engine (compare)
      8. Three-axis Status Synthesis
    """
    # 1. Eligibility Gate
    status_is_c = (meta.status or "").strip().upper() == "C"
    type_not_e = (meta.top_type_code or "").strip().upper() != "E"
    layout_is_zy = (meta.top_layout_code or "").strip().upper() == "ZY"

    if status_is_c or type_not_e or layout_is_zy:
        comparisons = tuple(
            LineComparison(
                side=s,
                line_no=n,
                expected=None,
                oracle=text,
                status=LineStatus.NOT_ELIGIBLE,
                compare_rules=(),
                detail="NOT_ELIGIBLE",
            )
            for s, n, text in oracle.lines
        )
        return JobResult(
            elr_no=meta.elr_no,
            processing_status=ProcessingStatus.DONE,
            hold_reason=None,
            verification_status=VerificationStatus.NOT_VERIFIABLE,
            approval_status=ApprovalStatus.NOT_REVIEWED,
            resolution=None,
            expected=None,
            comparisons=comparisons,
        )

    # 2. Document Resolution Gate
    resolution = (resolve_documents(meta, root, months, work_dir, folder_index=folder_index)
                  if folder_index is not None else resolve_documents(meta, root, months, work_dir))
    if resolution.decision == "HOLD":
        comparisons = tuple(
            LineComparison(
                side=s,
                line_no=n,
                expected=None,
                oracle=text,
                status=LineStatus.NOT_MEASURABLE,
                compare_rules=(),
                detail=resolution.hold_reason or "",
            )
            for s, n, text in oracle.lines
        )
        return JobResult(
            elr_no=meta.elr_no,
            processing_status=ProcessingStatus.HOLD,
            hold_reason=resolution.hold_reason,
            verification_status=None,
            approval_status=ApprovalStatus.NOT_REVIEWED,
            resolution=resolution,
            expected=None,
            comparisons=comparisons,
        )

    # 3. Skip Mark Gate
    if is_skip_mark(meta.mark_remark, meta.mark_require):
        comparisons = tuple(
            LineComparison(
                side=s,
                line_no=n,
                expected=None,
                oracle=text,
                status=LineStatus.NOT_MARKED,
                compare_rules=(),
                detail="SKIP_MARK",
            )
            for s, n, text in oracle.lines
        )
        return JobResult(
            elr_no=meta.elr_no,
            processing_status=ProcessingStatus.DONE,
            hold_reason=None,
            verification_status=VerificationStatus.NOT_VERIFIABLE,
            approval_status=ApprovalStatus.NOT_REVIEWED,
            resolution=resolution,
            expected=None,
            comparisons=comparisons,
            layout_source="none",
        )
    if layouts is not None and meta.top_mark_id not in layouts:
        return JobResult(elr_no=meta.elr_no, processing_status=ProcessingStatus.FAILED,
                         hold_reason=f'LAYOUT_ERROR: MARK_ID {meta.top_mark_id}: layout missing',
                         resolution=resolution, verification_status=VerificationStatus.NOT_VERIFIABLE)

    # 4. SLR Extraction
    slr_texts: list[str] = []
    for ref in resolution.slr:
        pdf_path = Path(ref.path)
        if pdf_path.is_file():
            doc = pymupdf.open(pdf_path)
            try:
                full_text = "\n".join(page.get_text() for page in doc)
                if full_text.strip():
                    slr_texts.append(full_text)
            finally:
                doc.close()

    if slr_texts:
        joined_text = "\n".join(slr_texts)
        slr_facts = parse_slr(joined_text)
    else:
        slr_facts = SlrFacts(
            text="",
            instructions=(),
            scheduled_lots=(),
            qual_lot=None,
            unresolved=(),
        )

    # 5. Inference Loading
    abs_stem = Path(resolution.abs.path).stem if resolution.abs else ""
    if inference_validator and resolution.abs:
        inference_validator(meta.elr_no, Path(resolution.abs.path), resolution.abs.sha256)
    inference = _call_inference_loader(inference_loader, root, meta.elr_no, abs_stem)

    if inference.layout_source == "none" or not inference.lines:
        comparisons = tuple(
            LineComparison(
                side=s,
                line_no=n,
                expected=None,
                oracle=text,
                status=LineStatus.NOT_COMPARABLE,
                compare_rules=(),
                detail="NO_LAYOUT",
            )
            for s, n, text in oracle.lines
        )
        return JobResult(
            elr_no=meta.elr_no,
            processing_status=ProcessingStatus.DONE,
            hold_reason=None,
            verification_status=VerificationStatus.NOT_VERIFIABLE,
            approval_status=ApprovalStatus.NOT_REVIEWED,
            resolution=resolution,
            expected=None,
            comparisons=comparisons,
            layout_source=inference.layout_source,
        )

    # 6. Generate Expected Mark
    # CRITICAL INVARIANT: must run before touching oracle
    expected = generate_expected(meta, resolution, slr_facts, inference, rules)
    if inference_validator and resolution.abs:
        inference_validator(meta.elr_no, Path(resolution.abs.path), resolution.abs.sha256)

    layout_conflicts = {}
    if layouts is not None:
        try:
            layout = layouts.get(meta.top_mark_id)
            if layout is None:
                raise LayoutError(f'MARK_ID {meta.top_mark_id}: layout missing')
            top_lines = {line.line_no: line for line in expected.lines if line.side == Side.TOP}
            formatted = []
            for number in range(1, 6):
                line = top_lines.get(number)
                generated = line.text or '' if line else ''
                if line:
                    prefix = ''.join(token.text for token in line.tokens if token.source == 'REMARK')
                    if prefix and generated.startswith(prefix + ' '):
                        generated = prefix + generated[len(prefix) + 1:]
                text, conflicts = fill_line_with_conflicts(layout, number, generated)
                if conflicts:
                    layout_conflicts[number] = conflicts
                fixed_tokens = tuple(ExpectedToken(text=value, rule_id=f'LAYOUT:{layout.mark_id}:{number}:{col}',
                                                   source='LAYOUT')
                                     for (row, col), value in sorted(layout.cells.items())
                                     if row == number and value != ' ')
                if line is not None:
                    formatted.append(replace(line, text=text, tokens=line.tokens + fixed_tokens))
                elif text.strip():
                    formatted.append(ExpectedLine(side=Side.TOP, line_no=number, text=text, tokens=fixed_tokens))
            formatted.extend(line for line in expected.lines if line.side != Side.TOP)
            expected = replace(expected, lines=tuple(formatted))
        except LayoutError as exc:
            return JobResult(
                elr_no=meta.elr_no, processing_status=ProcessingStatus.FAILED,
                hold_reason=f'LAYOUT_ERROR: {exc}', resolution=resolution,
                verification_status=VerificationStatus.NOT_VERIFIABLE,
                layout_source=inference.layout_source,
            )

    # 7. Compare with Oracle
    comparisons = compare(expected, oracle, slr_facts, meta, rules)
    if layouts is not None:
        comparisons = tuple(
            replace(item, warning='; '.join(filter(None, [item.warning,
                    'LAYOUT_LINE_SHIFT' if item.status == LineStatus.MATCH_SHIFT else 'LAYOUT_POSITION'])))
            if item.side == Side.TOP and (item.status == LineStatus.MATCH_SHIFT or
               (item.status in (LineStatus.MATCH, LineStatus.MATCH_SLR, LineStatus.MATCH_LOT)
                and item.expected is not None and oracle.get_raw(Side.TOP, item.line_no) is not None
                and position_differs(item.expected, oracle.get_raw(Side.TOP, item.line_no))))
            else item for item in comparisons
        )
    if layout_conflicts:
        comparisons = tuple(
            replace(item, warning='; '.join(filter(None, [item.warning,
                'LAYOUT_FIXED_CONFLICT: ' + ', '.join(
                    f'col {col}: {old} -> {new}' for col, old, new in layout_conflicts[item.line_no])])) )
            if item.side == Side.TOP and item.line_no in layout_conflicts else item
            for item in comparisons
        )

    # 8. Status Synthesis
    processing_status = ProcessingStatus.DONE
    approval_status = ApprovalStatus.NOT_REVIEWED

    if any(c.status == LineStatus.NEEDS_REVIEW for c in comparisons):
        verification_status = VerificationStatus.NEEDS_REVIEW
    elif any(c.status == LineStatus.DIFF for c in comparisons):
        verification_status = VerificationStatus.HAS_DIFF
    elif comparisons and all(
        c.status in (
            LineStatus.MATCH,
            LineStatus.MATCH_SLR,
            LineStatus.MATCH_SHIFT,
            LineStatus.MATCH_LOT,
        )
        for c in comparisons
    ):
        verification_status = VerificationStatus.MATCH_ALL
    else:
        verification_status = VerificationStatus.NOT_VERIFIABLE

    return JobResult(
        elr_no=meta.elr_no,
        processing_status=processing_status,
        hold_reason=None,
        verification_status=verification_status,
        approval_status=approval_status,
        resolution=resolution,
        expected=expected,
        comparisons=comparisons if isinstance(comparisons, tuple) else tuple(comparisons),
        layout_source=inference.layout_source,
    )
