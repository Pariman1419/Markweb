from scripts.diff_runs import diff_jobs, job_state


def test_job_state():
    assert job_state({"processing_status": "DONE", "hold_reason": "", "verification_status": "MATCH_ALL"}) == "DONE:MATCH_ALL"
    assert job_state({"processing_status": "HOLD", "hold_reason": "CUST_ASSY_TBD", "verification_status": ""}) == "HOLD:CUST_ASSY_TBD"
    assert job_state({"processing_status": "FAILED", "hold_reason": "TIMEOUT", "verification_status": ""}) == "FAILED:TIMEOUT"


def test_diff_jobs_groups_changed_elrs():
    base = [
        {"elr_no": "A1", "processing_status": "DONE", "hold_reason": "", "verification_status": "MATCH_ALL"},
        {"elr_no": "A2", "processing_status": "DONE", "hold_reason": "", "verification_status": "HAS_DIFF"},
    ]
    new = [
        {"elr_no": "A1", "processing_status": "DONE", "hold_reason": "", "verification_status": "MATCH_ALL"},
        {"elr_no": "A2", "processing_status": "HOLD", "hold_reason": "CUST_ASSY_TBD", "verification_status": ""},
    ]
    assert diff_jobs(base, new) == {("DONE:HAS_DIFF", "HOLD:CUST_ASSY_TBD"): ["A2"]}
