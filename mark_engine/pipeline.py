from __future__ import annotations

import inspect
import re
from dataclasses import replace
from pathlib import Path
from typing import Callable, Mapping, Sequence
import pymupdf

from mark_engine.compare.engine import compare
from mark_engine.documents.resolve import resolve_documents
from mark_engine.domain.models import (
    ApprovalStatus,
    DocumentResolution,
    ElrMeta,
    ExpectedLine,
    ExpectedToken,
    Flag,
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


_COO_SHORT_FORMS = ('THAI', 'THAILAN', 'THAILA', 'THAIL', 'THA', 'TH')
_LAYOUT_SYMBOLS = frozenset('@%^*{<!#?')


def _place_line(layout: MarkLayout, row: int, generated: str, raw_abs: str, line: ExpectedLine | None):
    """Fill one layout row; on overflow try the reviewed fallbacks. Returns (text, conflicts, warning)."""
    try:
        return (*fill_line_with_conflicts(layout, row, generated), '')
    except LayoutError as first:
        error = first
    # No room for the full country name (ADI1039 5.5.3: full name only when space allows). Use
    # the short form ACTL history uses most (ADI ELRs 2019-2026: THAI 304, THAIL 40, TH 2,
    # THAILA 2; queried 2026-11-05), then any other prefix. Compare reads every prefix as THAILAND.
    if re.search(r'\bTHAILAND\b', generated):
        for short in _COO_SHORT_FORMS:
            try:
                return (*fill_line_with_conflicts(layout, row, re.sub(r'\bTHAILAND\b', short, generated)),
                        'LAYOUT_COO_ABBREVIATED: THAILAND does not fit the layout')
            except LayoutError:
                continue
    # A literal character drawn after the last {token} on the ABS ("{ADI-PARTIAL-LOGO}{YW}X",
    # MARK_ID 22801): the reviewer reads the mark as the braced tokens only.
    from_abs = line is not None and Flag.SLR_OVERRIDE not in line.flags
    tail = re.search(r'\}([A-Za-z0-9])\s*$', raw_abs or '')
    if from_abs and tail and generated.rstrip().endswith(tail.group(1)):
        try:
            return (*fill_line_with_conflicts(layout, row, generated.rstrip()[:-1]),
                    f'LAYOUT_TRAILING_LITERAL_DROPPED: {tail.group(1)} after the last ABS token')
        except LayoutError:
            pass
    raise error


def _fits(layout: MarkLayout, row: int, text: str) -> bool:
    try:
        fill_line_with_conflicts(layout, row, text)
        return True
    except LayoutError:
        return False


def _reflow_pin_row(layout: MarkLayout, rows):
    """Split a line whose second part the layout starts on the next row with a fixed symbol.

    MARK_ID 25203/24711/22686: layout row 1 holds only '@' and row 2 starts with '%', but the ABS
    draws '@% XXX' on one line. Oracle writes '@' / '%XXX' / next line. Lines below shift down one
    row. Applied only when every resulting row fits and nothing is pushed past row 5.
    """
    for row in range(1, 5):
        line, generated, source_no = rows[row]
        if line is None or _fits(layout, row, generated):
            continue
        symbol = layout.cells.get((row + 1, 1))
        if symbol not in _LAYOUT_SYMBOLS:
            return None
        cut = generated.find(symbol)
        if cut <= 0:
            return None
        head, tail = generated[:cut].rstrip(), generated[cut:]
        if rows[5][0] is not None and rows[5][1].strip():
            return None
        new = dict(rows)
        new[row] = (line, head, source_no)
        new[row + 1] = (replace(line, line_no=row + 1, text=tail), tail, -1)
        for number in range(row + 1, 5):
            new[number + 1] = rows[number]
        if all(_fits(layout, n, new[n][1]) for n in range(row, 6)):
            return new, tuple(range(row, 6))
        return None
    return None


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
    resolution: DocumentResolution | None = None,
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
    # 1. Closed ELR Gate
    if (meta.status or "").strip().upper() == "C":
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

    # 2. Cust Assy TBD Gate (G1)
    if (meta.cust_assy_lot or "").strip().upper() == "TBD":
        comparisons = tuple(
            LineComparison(
                side=s,
                line_no=n,
                expected=None,
                oracle=text,
                status=LineStatus.NOT_MEASURABLE,
                compare_rules=(),
                detail="CUST_ASSY_TBD",
            )
            for s, n, text in oracle.lines
        )
        return JobResult(
            elr_no=meta.elr_no,
            processing_status=ProcessingStatus.HOLD,
            hold_reason="CUST_ASSY_TBD",
            verification_status=None,
            approval_status=ApprovalStatus.NOT_REVIEWED,
            resolution=None,
            expected=None,
            comparisons=comparisons,
        )

    # 3. Type / Layout Eligibility Gate
    type_not_e = (meta.top_type_code or "").strip().upper() != "E"
    layout_is_zy = (meta.top_layout_code or "").strip().upper() == "ZY"

    if type_not_e or layout_is_zy:
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
    if resolution is None:
        resolution = (
            resolve_documents(meta, root, months, work_dir, folder_index=folder_index)
            if folder_index is not None
            else resolve_documents(meta, root, months, work_dir)
        )
    

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
        if not slr_facts.special:
            slr_facts = replace(slr_facts, instructions=(), unresolved=())
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

    # G5: Content beyond TOP row 5 holds the job
    over_5_lines = [l for l in expected.lines if l.side == Side.TOP and l.line_no > 5 and (l.text or "").strip()]
    if over_5_lines:
        comparisons = tuple(
            LineComparison(
                side=s,
                line_no=n,
                expected=None,
                oracle=text,
                status=LineStatus.NOT_MEASURABLE,
                compare_rules=(),
                detail="ROW_OVER_5",
            )
            for s, n, text in oracle.lines
        )
        res = (
            replace(resolution, hold_detail=f"{len(over_5_lines)} TOP rows with content beyond row 5")
            if resolution
            else None
        )
        return JobResult(
            elr_no=meta.elr_no,
            processing_status=ProcessingStatus.HOLD,
            hold_reason="ROW_OVER_5",
            verification_status=None,
            approval_status=ApprovalStatus.NOT_REVIEWED,
            resolution=res,
            expected=None,
            comparisons=comparisons,
            layout_source=inference.layout_source,
        )

    layout_conflicts = {}
    layout_overflows: dict[int, str] = {}
    layout_notes: dict[int, list[str]] = {}
    if layouts is not None:
        try:
            layout = layouts.get(meta.top_mark_id)
            if layout is None:
                raise LayoutError(f'MARK_ID {meta.top_mark_id}: layout missing')
            top_lines = {line.line_no: line for line in expected.lines if line.side == Side.TOP}
            rows: dict[int, tuple[ExpectedLine | None, str, int]] = {}
            for number in range(1, 6):
                line = top_lines.get(number)
                generated = line.text or '' if line else ''
                if line:
                    prefix = ''.join(token.text for token in line.tokens if token.source == 'REMARK')
                    if prefix and generated.startswith(prefix + ' '):
                        generated = prefix + generated[len(prefix) + 1:]
                rows[number] = (line, generated, number)
            reflowed = _reflow_pin_row(layout, rows)
            if reflowed is not None:
                rows, moved = reflowed
                for number in moved:
                    layout_notes.setdefault(number, []).append('LAYOUT_REFLOW: line split to fit the layout rows')
            raw_abs = {item.line_no: item.text or '' for item in inference.lines if item.side == Side.TOP}
            formatted = []
            for number in range(1, 6):
                line, generated, source_no = rows[number]
                if line is not None and line.line_no != number:
                    line = replace(line, line_no=number)
                try:
                    text, conflicts, note = _place_line(layout, number, generated, raw_abs.get(source_no, ''), line)
                    if note:
                        layout_notes.setdefault(number, []).append(note)
                except LayoutError as exc:
                    # One line that cannot be placed is a review item; the other lines are still
                    # compared (overflow review 2026-11-05: "แจ้งเป็น warning เพราะมีส่วนที่ถูก").
                    layout_overflows[number] = str(exc)
                    if line is not None:
                        formatted.append(line)
                    continue
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
    if layout_notes:
        comparisons = tuple(
            replace(item, warning='; '.join(filter(None, [item.warning, *layout_notes[item.line_no]])))
            if item.side == Side.TOP and item.line_no in layout_notes else item
            for item in comparisons
        )
    if layout_overflows:
        comparisons = tuple(
            replace(item, status=LineStatus.NEEDS_REVIEW,
                    warning='; '.join(filter(None, [item.warning, f'LAYOUT_OVERFLOW: {layout_overflows[item.line_no]}'])))
            if item.side == Side.TOP and item.line_no in layout_overflows else item
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
