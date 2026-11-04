from dataclasses import FrozenInstanceError
import pytest

from mark_engine.domain.models import (
    ApprovalStatus,
    DocType,
    DocumentRef,
    DocumentResolution,
    ElrMeta,
    ExpectedLine,
    ExpectedMark,
    ExpectedToken,
    Flag,
    InferenceResult,
    JobResult,
    LayoutLine,
    LineComparison,
    LineStatus,
    OracleMark,
    ProcessingStatus,
    Side,
    SlrFacts,
    SlrInstruction,
    VerificationStatus,
)


def test_expected_mark_is_frozen():
    em = ExpectedMark("ADI2601001", (), "RV-2026-11-04-R0", "0.1.0")
    with pytest.raises(FrozenInstanceError):
        em.elr_no = "x"  # type: ignore[misc]


def test_oracle_mark_get_absent_is_empty():
    om = OracleMark("ADI2601001", ((Side.TOP, 1, "@%"),))
    assert om.get(Side.TOP, 1) == "@%"
    assert om.get(Side.BOTTOM, 2) == ""


def test_expected_mark_line_lookup():
    line_top_1 = ExpectedLine(Side.TOP, 1, "TEST", (), frozenset())
    line_bottom_1 = ExpectedLine(Side.BOTTOM, 1, "BOT", (), frozenset())
    em = ExpectedMark("ADI2601001", (line_top_1, line_bottom_1), "RV-2026-11-04-R0", "0.1.0")
    assert em.line(Side.TOP, 1) == line_top_1
    assert em.line(Side.BOTTOM, 1) == line_bottom_1
    assert em.line(Side.TOP, 2) is None


def test_no_pass_in_status_names():
    for enum_cls in (LineStatus, ProcessingStatus, VerificationStatus, ApprovalStatus):
        for member in enum_cls:
            assert "PASS" not in member.name, f"Found 'PASS' in enum name: {member.name}"
            assert "PASS" not in member.value, f"Found 'PASS' in enum value: {member.value}"


def test_enums_values_and_members():
    assert set(Side) == {Side.TOP, Side.BOTTOM}
    assert [s.value for s in Side] == ["TOP", "BOTTOM"]

    assert set(DocType) == {DocType.ABS, DocType.SLR, DocType.TRS, DocType.OTHER}

    expected_line_statuses = {
        "MATCH", "MATCH_SLR", "MATCH_SHIFT", "MATCH_LOT", "DIFF",
        "NEEDS_REVIEW", "DB_EMPTY", "NOT_MARKED", "NOT_COMPARABLE",
        "NOT_MEASURABLE", "NOT_ELIGIBLE"
    }
    assert {s.value for s in LineStatus} == expected_line_statuses

    expected_proc_statuses = {"PENDING", "RUNNING", "DONE", "FAILED", "HOLD"}
    assert {s.value for s in ProcessingStatus} == expected_proc_statuses

    expected_verif_statuses = {"MATCH_ALL", "HAS_DIFF", "NEEDS_REVIEW", "NOT_VERIFIABLE"}
    assert {s.value for s in VerificationStatus} == expected_verif_statuses

    expected_appr_statuses = {"NOT_REVIEWED", "APPROVED", "REJECTED", "STALE"}
    assert {s.value for s in ApprovalStatus} == expected_appr_statuses

    expected_flags = {
        "ORACLE_DERIVED_UNAPPROVED", "RULE_CONFLICT", "SLR_AMBIGUOUS",
        "SLR_UNRESOLVED", "GRAPHIC_REMARK_CONFLICT", "UNMAPPED_TOKEN", "SLR_OVERRIDE"
    }
    assert {f.value for f in Flag} == expected_flags


def test_domain_model_dataclasses_frozen_and_slots():
    meta = ElrMeta(
        elr_no="ADI2601001",
        import_date="2026-01-01",
        status="ACTIVE",
        current_step="GENERATE",
        cust_bom_no="BOM123",
        cust_bom_revision="A",
        cust_req_no="REQ1",
        cust_assy_lot="LOT1",
        product_no="P1",
        package_code="SOIC",
        mark_remark="NONE",
        mark_require="REQ",
        top_type_code="E",
        top_layout_code="STD",
    )
    assert meta.elr_no == "ADI2601001"
    assert hasattr(meta, "__slots__")
    assert not hasattr(meta, "__dict__")
    with pytest.raises(FrozenInstanceError):
        meta.elr_no = "new"  # type: ignore[misc]

    doc_ref = DocumentRef(
        path="/docs/ABS123456A.pdf",
        sha256="abc123",
        doc_type=DocType.ABS,
        number="ABS123456",
        revision="A",
        revision_source="FILENAME",
    )
    assert doc_ref.doc_type == DocType.ABS
    assert hasattr(doc_ref, "__slots__")
    assert not hasattr(doc_ref, "__dict__")
    with pytest.raises(FrozenInstanceError):
        doc_ref.path = "new"  # type: ignore[misc]

    resolution = DocumentResolution(
        elr_no="ADI2601001",
        decision="RESOLVED",
        hold_reason=None,
        abs=doc_ref,
        slr=(doc_ref,),
        rejected=(),
        steps=("MATCH_BOM",),
    )
    assert resolution.decision == "RESOLVED"
    assert hasattr(resolution, "__slots__")
    assert not hasattr(resolution, "__dict__")
    with pytest.raises(FrozenInstanceError):
        resolution.decision = "HOLD"  # type: ignore[misc]

    layout_line = LayoutLine(
        side=Side.TOP,
        line_no=1,
        text="ADI",
        graphics="@%",
        score=0.99,
    )
    assert layout_line.line_no == 1
    assert hasattr(layout_line, "__slots__")
    assert not hasattr(layout_line, "__dict__")
    with pytest.raises(FrozenInstanceError):
        layout_line.line_no = 2  # type: ignore[misc]

    inf = InferenceResult(
        elr_no="ADI2601001",
        lines=(layout_line,),
        layout_source="auto",
    )
    assert inf.layout_source == "auto"
    assert hasattr(inf, "__slots__")
    assert not hasattr(inf, "__dict__")
    with pytest.raises(FrozenInstanceError):
        inf.layout_source = "none"  # type: ignore[misc]

    slr_inst = SlrInstruction(
        side=Side.TOP,
        line_no=1,
        value="TEST",
        quote="Line 1: TEST",
        alternatives=(),
    )
    assert slr_inst.value == "TEST"
    assert hasattr(slr_inst, "__slots__")
    assert not hasattr(slr_inst, "__dict__")
    with pytest.raises(FrozenInstanceError):
        slr_inst.value = "ALT"  # type: ignore[misc]

    slr_facts = SlrFacts(
        text="Special instructions",
        instructions=(slr_inst,),
        scheduled_lots=("7346019",),
        qual_lot=(1, 2),
        unresolved=(),
    )
    assert slr_facts.scheduled_lots == ("7346019",)
    assert hasattr(slr_facts, "__slots__")
    assert not hasattr(slr_facts, "__dict__")
    with pytest.raises(FrozenInstanceError):
        slr_facts.text = ""  # type: ignore[misc]

    token = ExpectedToken(
        text="ADI",
        rule_id="R01-ABS",
        source="ABS",
        lot_slice=None,
    )
    assert token.text == "ADI"
    assert hasattr(token, "__slots__")
    assert not hasattr(token, "__dict__")
    with pytest.raises(FrozenInstanceError):
        token.text = "OTHER"  # type: ignore[misc]

    line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="ADI",
        tokens=(token,),
        flags=frozenset({Flag.SLR_OVERRIDE}),
    )
    assert line.side == Side.TOP
    assert hasattr(line, "__slots__")
    assert not hasattr(line, "__dict__")
    with pytest.raises(FrozenInstanceError):
        line.text = "MOD"  # type: ignore[misc]

    comp = LineComparison(
        side=Side.TOP,
        line_no=1,
        expected="ADI",
        oracle="ADI",
        status=LineStatus.MATCH,
        compare_rules=("R-COMPARE-EXACT",),
        detail="exact match",
    )
    assert comp.status == LineStatus.MATCH
    assert hasattr(comp, "__slots__")
    assert not hasattr(comp, "__dict__")
    with pytest.raises(FrozenInstanceError):
        comp.oracle = "OTHER"  # type: ignore[misc]

    job = JobResult(
        elr_no="ADI2601001",
        processing_status=ProcessingStatus.DONE,
        hold_reason=None,
        verification_status=VerificationStatus.MATCH_ALL,
        approval_status=ApprovalStatus.NOT_REVIEWED,
        resolution=resolution,
        expected=ExpectedMark("ADI2601001", (line,), "RV-2026-11-04-R0", "0.1.0"),
        comparisons=(comp,),
    )
    assert job.processing_status == ProcessingStatus.DONE
    assert hasattr(job, "__slots__")
    assert not hasattr(job, "__dict__")
    with pytest.raises(FrozenInstanceError):
        job.processing_status = ProcessingStatus.FAILED  # type: ignore[misc]
