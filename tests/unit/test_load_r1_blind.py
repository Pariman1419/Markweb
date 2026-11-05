from scripts.load_r1_to_pg import is_blind_run


def test_is_blind_run_replay_unfrozen():
    assert is_blind_run("2026-07..2026-11-replay", {"freeze": {"freeze_id": "UNFROZEN"}}) is False


def test_is_blind_run_frozen_r1():
    assert is_blind_run("2026-07..2026-11", {"freeze": {"freeze_id": "FREEZE-R1"}}) is True
