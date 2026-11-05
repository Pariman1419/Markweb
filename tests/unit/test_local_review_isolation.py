from services.engine.build_review import isolate_review
import pytest


def test_local_review_gets_run_specific_storage_and_no_cloud():
    source = 'LKEY="r1-review-v1"; const c=window.claude;'
    result = isolate_review(source, 'a' * 64)
    assert 'LKEY="mark-review-aaaaaaaaaaaaaaaa"' in result
    assert 'const c=null;' in result
    assert 'window.claude' not in result


def test_review_isolation_fails_closed_when_template_changes():
    with pytest.raises(ValueError, match='cannot safely isolate'):
        isolate_review('unexpected template', 'b' * 64)
