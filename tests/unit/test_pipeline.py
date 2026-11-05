from pathlib import Path
from typing import Sequence
import pytest

from mark_engine.domain.models import (
    ApprovalStatus,
    ElrMeta,
    InferenceResult,
    LayoutLine,
    LineStatus,
    OracleMark,
    ProcessingStatus,
    Side,
    VerificationStatus,
)
from mark_engine.pipeline import process_elr
from mark_engine.rules.ruleset import RuleSet
from tests.fixtures.make_pdfs import make_pdf


def _rules() -> RuleSet:
    return RuleSet.load()


def _setup_elr(
    month_tree: Path,
    elr_no: str,
    include_slr: bool = True,
    slr_instruction: str = "",
) -> tuple[Path, ElrMeta]:
    elr_folder = month_tree / "1_JAN" / elr_no
    elr_folder.mkdir(parents=True, exist_ok=True)

    abs_pdf = elr_folder / "ABS066854-ENG-1.pdf"
    make_pdf(abs_pdf, ["ABS066854 cover", "Brand/Marking diagram"])

    if include_slr:
        slr_pdf = elr_folder / "SLR232022.pdf"
        inst = f"{slr_instruction}\n" if slr_instruction else "None.\n"
        slr_body = (
            f"HEADER INFO\n"
            f"SPECIAL INSTRUCTIONS\n"
            f"{inst}"
            f"ANALOG\n"
            f"DEVICES\n"
            f"Scheduled Lot ID\n"
            f"7284173.1\n"
        )
        make_pdf(slr_pdf, [slr_body])

    meta = ElrMeta(
        elr_no=elr_no,
        status="A",
        top_type_code="E",
        top_layout_code="STD",
        cust_bom_no="ABS066854",
        cust_bom_revision="ENG-1",
        cust_req_no="SLR232022" if include_slr else None,
    )
    return elr_folder, meta


def test_cancelled_not_eligible(tmp_path: Path):
    meta = ElrMeta(elr_no="ADI2601001", status="C", top_type_code="E", top_layout_code="STD")
    oracle = OracleMark(elr_no="ADI2601001", lines=((Side.TOP, 1, "ADW"),))
    loader = lambda elr, stem: InferenceResult(elr)

    job = process_elr(meta, oracle, tmp_path, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.NOT_VERIFIABLE
    assert job.approval_status == ApprovalStatus.NOT_REVIEWED
    assert job.expected is None
    assert job.resolution is None
    assert len(job.comparisons) == 1
    assert job.comparisons[0].status == LineStatus.NOT_ELIGIBLE
    assert job.comparisons[0].detail == "NOT_ELIGIBLE"


def test_type_code_p_not_eligible(tmp_path: Path):
    meta = ElrMeta(elr_no="ADI2601002", status="A", top_type_code="P", top_layout_code="STD")
    oracle = OracleMark(elr_no="ADI2601002", lines=((Side.TOP, 1, "ADW"),))
    loader = lambda elr, stem: InferenceResult(elr)

    job = process_elr(meta, oracle, tmp_path, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.NOT_VERIFIABLE
    assert job.comparisons[0].status == LineStatus.NOT_ELIGIBLE


def test_layout_code_zy_not_eligible(tmp_path: Path):
    meta = ElrMeta(elr_no="ADI2601003", status="A", top_type_code="E", top_layout_code="ZY")
    oracle = OracleMark(elr_no="ADI2601003", lines=((Side.TOP, 1, "ADW"),))
    loader = lambda elr, stem: InferenceResult(elr)

    job = process_elr(meta, oracle, tmp_path, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.NOT_VERIFIABLE
    assert job.comparisons[0].status == LineStatus.NOT_ELIGIBLE


def test_missing_slr_hold(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601004", include_slr=False)
    oracle = OracleMark(elr_no="ADI2601004", lines=((Side.TOP, 1, "ADW"),))
    loader = lambda elr, stem: InferenceResult(elr)

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.HOLD
    assert job.hold_reason == "SLR_NOT_FOUND"
    assert job.verification_status is None
    assert job.approval_status == ApprovalStatus.NOT_REVIEWED
    assert job.expected is None
    assert job.resolution is not None
    assert job.resolution.decision == "HOLD"
    assert len(job.comparisons) == 1
    assert job.comparisons[0].status == LineStatus.NOT_MEASURABLE
    assert job.comparisons[0].detail == "SLR_NOT_FOUND"


def test_skip_mark_not_marked(month_tree: Path, tmp_path: Path):
    _, base_meta = _setup_elr(month_tree, "ADI2601005", include_slr=True)
    meta = ElrMeta(
        elr_no=base_meta.elr_no,
        status=base_meta.status,
        top_type_code=base_meta.top_type_code,
        top_layout_code=base_meta.top_layout_code,
        cust_bom_no=base_meta.cust_bom_no,
        cust_bom_revision=base_meta.cust_bom_revision,
        cust_req_no=base_meta.cust_req_no,
        mark_remark="Please SKIP MARK for this run",
    )
    oracle = OracleMark(elr_no="ADI2601005", lines=((Side.TOP, 1, "ADW"),))
    loader = lambda elr, stem: InferenceResult(elr)

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.NOT_VERIFIABLE
    assert job.approval_status == ApprovalStatus.NOT_REVIEWED
    assert job.expected is None
    assert len(job.comparisons) == 1
    assert job.comparisons[0].status == LineStatus.NOT_MARKED
    assert job.comparisons[0].detail == "SKIP_MARK"


def test_no_layout_not_comparable(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601006", include_slr=True)
    oracle = OracleMark(elr_no="ADI2601006", lines=((Side.TOP, 1, "ADW"),))
    loader = lambda elr, stem: InferenceResult(elr, lines=(), layout_source="none")

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.NOT_VERIFIABLE
    assert job.approval_status == ApprovalStatus.NOT_REVIEWED
    assert job.expected is None
    assert len(job.comparisons) == 1
    assert job.comparisons[0].status == LineStatus.NOT_COMPARABLE
    assert job.comparisons[0].detail == "NO_LAYOUT"


def test_empty_inference_lines_not_comparable(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601007", include_slr=True)
    oracle = OracleMark(elr_no="ADI2601007", lines=((Side.TOP, 1, "ADW"),))
    # Even if layout_source is auto, empty lines should be NOT_COMPARABLE
    loader = lambda elr, stem: InferenceResult(elr, lines=(), layout_source="auto")

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.NOT_VERIFIABLE
    assert job.comparisons[0].status == LineStatus.NOT_COMPARABLE
    assert job.comparisons[0].detail == "NO_LAYOUT"


def test_match_all_still_not_reviewed(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601008", include_slr=True)
    oracle = OracleMark(elr_no="ADI2601008", lines=((Side.TOP, 1, "ADW"),))
    loader = lambda elr, stem: InferenceResult(
        elr,
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics=""),),
        layout_source="auto",
    )

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.MATCH_ALL
    assert job.approval_status == ApprovalStatus.NOT_REVIEWED
    assert job.expected is not None
    assert job.resolution is not None
    assert len(job.comparisons) == 1
    assert job.comparisons[0].status == LineStatus.MATCH


def test_oracle_untouched_before_compare(month_tree: Path, tmp_path: Path, monkeypatch):
    _, meta = _setup_elr(month_tree, "ADI2601009", include_slr=True)
    real_oracle = OracleMark(elr_no="ADI2601009", lines=((Side.TOP, 1, "ADW"),))

    import mark_engine.pipeline as pipeline_mod

    generate_finished = False
    original_generate = pipeline_mod.generate_expected

    def spy_generate(*args, **kwargs):
        nonlocal generate_finished
        res = original_generate(*args, **kwargs)
        generate_finished = True
        return res

    monkeypatch.setattr(pipeline_mod, "generate_expected", spy_generate)

    access_log: list[str] = []

    class OracleProxy:
        def __init__(self, target):
            self._target = target

        def __getattr__(self, name):
            access_log.append(name)
            assert generate_finished, (
                f"Oracle attribute '{name}' was accessed BEFORE generate_expected completed!"
            )
            return getattr(self._target, name)

    oracle_proxy = OracleProxy(real_oracle)
    loader = lambda elr, stem: InferenceResult(
        elr,
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics=""),),
        layout_source="auto",
    )

    job = pipeline_mod.process_elr(
        meta, oracle_proxy, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader
    )

    assert generate_finished is True
    assert len(access_log) > 0, "Oracle was never accessed at all"
    assert job.verification_status == VerificationStatus.MATCH_ALL


def test_status_synthesis_needs_review(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601010", include_slr=True)
    # Line with unmapped token produces NEEDS_REVIEW
    oracle = OracleMark(elr_no="ADI2601010", lines=((Side.TOP, 1, "UNKNOWN"),))
    loader = lambda elr, stem: InferenceResult(
        elr,
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="{UNKNOWN_TOKEN}", graphics=""),),
        layout_source="auto",
    )

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.NEEDS_REVIEW
    assert job.approval_status == ApprovalStatus.NOT_REVIEWED


def test_status_synthesis_diff(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601011", include_slr=True)
    oracle = OracleMark(elr_no="ADI2601011", lines=((Side.TOP, 1, "ORACLE_VAL"),))
    loader = lambda elr, stem: InferenceResult(
        elr,
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="EXP_VAL", graphics=""),),
        layout_source="auto",
    )

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.HAS_DIFF
    assert job.approval_status == ApprovalStatus.NOT_REVIEWED


def test_three_arg_inference_loader(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601012", include_slr=True)
    oracle = OracleMark(elr_no="ADI2601012", lines=((Side.TOP, 1, "ADW"),))

    called_with = []

    def loader_3args(root: Path, elr_no: str, abs_stem: str) -> InferenceResult:
        called_with.append((root, elr_no, abs_stem))
        return InferenceResult(
            elr_no,
            lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics=""),),
            layout_source="auto",
        )

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader_3args)

    assert len(called_with) == 1
    assert called_with[0][0] == month_tree
    assert called_with[0][1] == "ADI2601012"
    assert "ABS066854" in called_with[0][2]
    assert job.verification_status == VerificationStatus.MATCH_ALL


def test_match_slr_match_all(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601013", include_slr=True, slr_instruction="Line 1: Q1")
    oracle = OracleMark(elr_no="ADI2601013", lines=((Side.TOP, 1, "Q1"),))
    loader = lambda elr, stem: InferenceResult(
        elr,
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics=""),),
        layout_source="auto",
    )

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.MATCH_ALL
    assert job.comparisons[0].status == LineStatus.MATCH_SLR


def test_shift_match_all(month_tree: Path, tmp_path: Path):
    _, meta = _setup_elr(month_tree, "ADI2601014", include_slr=True)
    # Oracle line 1 is graphic %, line 2 is ADW
    oracle = OracleMark(
        elr_no="ADI2601014",
        lines=(
            (Side.TOP, 1, "%"),
            (Side.TOP, 2, "ADW"),
        ),
    )
    # Expected line 1 has graphic % and text ADW
    loader = lambda elr, stem: InferenceResult(
        elr,
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics="%"),),
        layout_source="auto",
    )

    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)

    assert job.processing_status == ProcessingStatus.DONE
    assert job.verification_status == VerificationStatus.MATCH_ALL
    assert all(c.status == LineStatus.MATCH_SHIFT for c in job.comparisons)


@pytest.mark.parametrize("lot, status, layout, expect_hold", [
    (" tbd ", "A", "ZY", True),      # TBD wins over the ZY layout gate (user order)
    ("Tbd", "A", "STD", True),
    ("TBD", "C", "STD", False),      # closed ELR stays NOT_ELIGIBLE
    ("1STBOND", "A", "ZY", False),   # contains "TB" but is not TBD
    (None, "A", "ZY", False),
])
def test_cust_assy_tbd_gate(tmp_path: Path, lot, status, layout, expect_hold):
    meta = ElrMeta(elr_no="ADI2601020", status=status, top_type_code="E",
                   top_layout_code=layout, cust_assy_lot=lot)
    oracle = OracleMark(elr_no="ADI2601020", lines=((Side.TOP, 1, "ADW"),))
    job = process_elr(meta, oracle, tmp_path, ["1_JAN"], tmp_path / "work", _rules(),
                      lambda elr, stem: InferenceResult(elr))
    if expect_hold:
        assert (job.processing_status, job.hold_reason) == (ProcessingStatus.HOLD, "CUST_ASSY_TBD")
        assert job.resolution is None and job.verification_status is None
        assert job.comparisons[0].status == LineStatus.NOT_MEASURABLE
        assert job.comparisons[0].detail == "CUST_ASSY_TBD"
    else:
        assert job.comparisons[0].status == LineStatus.NOT_ELIGIBLE


