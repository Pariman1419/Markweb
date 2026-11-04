from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Side(StrEnum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"


class DocType(StrEnum):
    ABS = "ABS"
    SLR = "SLR"
    TRS = "TRS"
    OTHER = "OTHER"


class LineStatus(StrEnum):
    MATCH = "MATCH"
    MATCH_SLR = "MATCH_SLR"
    MATCH_SHIFT = "MATCH_SHIFT"
    MATCH_LOT = "MATCH_LOT"
    DIFF = "DIFF"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DB_EMPTY = "DB_EMPTY"
    NOT_MARKED = "NOT_MARKED"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    NOT_MEASURABLE = "NOT_MEASURABLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    HOLD = "HOLD"


class VerificationStatus(StrEnum):
    MATCH_ALL = "MATCH_ALL"
    HAS_DIFF = "HAS_DIFF"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"


class ApprovalStatus(StrEnum):
    NOT_REVIEWED = "NOT_REVIEWED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class Flag(StrEnum):
    ORACLE_DERIVED_UNAPPROVED = "ORACLE_DERIVED_UNAPPROVED"
    RULE_CONFLICT = "RULE_CONFLICT"
    SLR_AMBIGUOUS = "SLR_AMBIGUOUS"
    SLR_UNRESOLVED = "SLR_UNRESOLVED"
    GRAPHIC_REMARK_CONFLICT = "GRAPHIC_REMARK_CONFLICT"
    UNMAPPED_TOKEN = "UNMAPPED_TOKEN"
    SLR_OVERRIDE = "SLR_OVERRIDE"


@dataclass(frozen=True, slots=True)
class ElrMeta:
    elr_no: str
    import_date: str | None = None
    status: str | None = None
    current_step: str | None = None
    cust_bom_no: str | None = None
    cust_bom_revision: str | None = None
    cust_req_no: str | None = None
    cust_assy_lot: str | None = None
    product_no: str | None = None
    package_code: str | None = None
    mark_remark: str | None = None
    mark_require: str | None = None
    top_type_code: str | None = None
    top_layout_code: str | None = None


@dataclass(frozen=True, slots=True)
class OracleMark:
    elr_no: str
    lines: tuple[tuple[Side, int, str], ...] = ()

    def get(self, side: Side, n: int) -> str:
        for s, line_no, text in self.lines:
            if s == side and line_no == n:
                return text
        return ""


@dataclass(frozen=True, slots=True)
class DocumentRef:
    path: str
    sha256: str
    doc_type: DocType
    number: str | None = None
    revision: str | None = None
    revision_source: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentResolution:
    elr_no: str
    decision: Literal["RESOLVED", "HOLD"]
    hold_reason: str | None = None
    abs: DocumentRef | None = None
    slr: tuple[DocumentRef, ...] = ()
    rejected: tuple[tuple[DocumentRef, str], ...] = ()
    steps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LayoutLine:
    side: Side
    line_no: int
    text: str
    graphics: str
    score: float | None = None


@dataclass(frozen=True, slots=True)
class InferenceResult:
    elr_no: str
    lines: tuple[LayoutLine, ...] = ()
    layout_source: Literal["auto", "human_crop", "none"] = "auto"


@dataclass(frozen=True, slots=True)
class SlrInstruction:
    side: Side
    line_no: int
    value: str | None = None
    quote: str = ""
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SlrFacts:
    text: str
    instructions: tuple[SlrInstruction, ...] = ()
    scheduled_lots: tuple[str, ...] = ()
    qual_lot: tuple[int, int] | None = None
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpectedToken:
    text: str
    rule_id: str
    source: Literal["ABS", "SLR", "REMARK", "ADI1039", "SYMBOL_ADI", "OCR_FIX", "YOLO"]
    lot_slice: str | None = None


@dataclass(frozen=True, slots=True)
class ExpectedLine:
    side: Side
    line_no: int
    text: str | None = None
    tokens: tuple[ExpectedToken, ...] = ()
    flags: frozenset[Flag] = frozenset()


@dataclass(frozen=True, slots=True)
class ExpectedMark:
    elr_no: str
    lines: tuple[ExpectedLine, ...]
    rule_version: str
    engine_version: str

    def line(self, side: Side, n: int) -> ExpectedLine | None:
        for l in self.lines:
            if l.side == side and l.line_no == n:
                return l
        return None


@dataclass(frozen=True, slots=True)
class LineComparison:
    side: Side
    line_no: int
    expected: str | None
    oracle: str
    status: LineStatus
    compare_rules: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class JobResult:
    elr_no: str
    processing_status: ProcessingStatus
    hold_reason: str | None = None
    verification_status: VerificationStatus | None = None
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REVIEWED
    resolution: DocumentResolution | None = None
    expected: ExpectedMark | None = None
    comparisons: tuple[LineComparison, ...] = ()
