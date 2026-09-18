"""The ledger files every run by folder and never loses one."""

from inspect_ai import eval as inspect_eval

from analysis.tidy import status_for, tidy
from caretaker.mock import mock_model
from caretaker.task import caretaker


def test_status_by_folder():
    assert status_for("pilot") == "kept"
    assert status_for("full") == "kept"
    assert status_for("pilot-discarded-2026-09-18") == "discarded"
    assert status_for("trial") == "trial"
    assert status_for("mock") is None


def test_tidy_tables(tmp_path):
    for folder in ("pilot", "pilot-discarded-2026-01-01", "mock"):
        inspect_eval(caretaker("pilot", "control", seeds="11", max_days=8), model=mock_model(),
                     log_dir=str(tmp_path / folder), display="none")
    ledger, runs, days = tidy(tmp_path)
    assert sorted(ledger["status"]) == ["discarded", "kept"]  # mock is skipped
    assert (ledger["days_run"] == 8).all() and (ledger["model_calls"] == 9).all()  # 8 days + 1 summary
    assert len(runs) == 2 and len(days) == 16
    assert {"proxy_gap", "harmful_compliance_rate", "question_rate", "final_health"} <= set(runs.columns)
    assert days["health_before"].notna().all()
