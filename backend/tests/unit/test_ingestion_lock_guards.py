"""A confirmed candidate cannot be reopened for editing after a later state change."""

import pytest

from rpb.adapters import paper_analysis, paper_deduplication, paper_processing, paper_screening
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.paper_analysis_worker import AnalysisWorker
from rpb.adapters.paper_scoring_worker import ScoreWorker
from rpb.adapters.pdf_cleanup_worker import CleanupWorker
from rpb.modules.account_config.application.ports import AccountError


@pytest.mark.parametrize("phase", ["ingestion_preview", "analysis", "screening"])
def test_confirmed_candidate_rejects_content_writes_even_if_waiting_again(phase):
    run = {
        "status": "waiting_user",
        "phase": phase,
        "candidate_version": {"content_locked": True, "state": "preparing"},
        "ingestion_confirmation": None,
    }
    with pytest.raises(AccountError) as screening_error:
        paper_screening.writable(run)
    assert screening_error.value.code == "STATE_OPERATION_NOT_ALLOWED"
    with pytest.raises(AccountError) as analysis_error:
        paper_analysis.writable(run, {})
    assert analysis_error.value.code == "STATE_OPERATION_NOT_ALLOWED"
    with pytest.raises(AccountError) as dedup_error:
        paper_deduplication.correct(run, {}, "actor")
    assert dedup_error.value.code == "STATE_OPERATION_NOT_ALLOWED"
    for confirm in (paper_processing.confirm, paper_analysis.confirm):
        with pytest.raises(AccountError) as confirmation_error:
            confirm(run, "actor")
        assert confirmation_error.value.code == "STATE_OPERATION_NOT_ALLOWED"


def test_locked_candidate_rejects_late_worker_boundaries():
    run = {"candidate_version": {"content_locked": True}, "ingestion_confirmation": None}
    checks = [
        lambda: AnalysisWorker.__new__(AnalysisWorker).check(None, None, run, {}, "commit"),
        lambda: ScoreWorker.__new__(ScoreWorker).check(None, None, run, {}, "commit"),
        lambda: CleanupWorker.__new__(CleanupWorker).check(None, None, run, "job"),
        lambda: paper_processing.ProcessingWorker.__new__(paper_processing.ProcessingWorker).check(
            None, None, run, "job"
        ),
    ]
    for check in checks:
        with pytest.raises(ProviderFailure) as error:
            check()
        assert error.value.code == "STATE_REVISION_CONFLICT"
