from mark_engine.domain.models import ElrMeta
from mark_engine.select import pending_reason, review_step_from_env


def test_pending_reason(monkeypatch):
    m = lambda **kw: ElrMeta(elr_no="ADI2601040", **kw)
    assert pending_reason(m(status="R", current_step=" 6 "), "6") is None
    assert pending_reason(m(status="c", current_step="6"), "6") == "STATUS_C"
    assert pending_reason(m(status="R", current_step="7"), "6") == "NOT_MARK_REVIEW_STEP"
    assert pending_reason(m(status="R", current_step=None), "6") == "NOT_MARK_REVIEW_STEP"
    monkeypatch.delenv("MARK_REVIEW_STEP", raising=False)
    assert review_step_from_env() == "6"
