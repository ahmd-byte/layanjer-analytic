from datetime import datetime, timezone

from layan_engine.platforms.base import ExtractionResult
from layan_engine.storage.runs import INTERRUPTED, close_interrupted_runs, run_error_message


class TestRunErrorMessage:
    def test_errors_win(self):
        r = ExtractionResult(errors=["Challenge detected: captcha"], warnings=["slow"])
        assert run_error_message(r) == "Challenge detected: captcha"

    def test_failed_without_errors_uses_warnings(self):
        r = ExtractionResult(success=False, warnings=["No overview metrics could be extracted"])
        assert run_error_message(r) == "No overview metrics could be extracted"

    def test_failed_with_nothing_still_explains(self):
        assert run_error_message(ExtractionResult(success=False)) == "No numbers could be read from the dashboard"

    def test_success_has_no_error(self):
        assert run_error_message(ExtractionResult(success=True, warnings=["note"])) is None


def test_startup_closes_runs_left_running():
    from layan_engine.storage.database import get_session_factory, init_db
    from layan_engine.storage.models import ExtractionRun

    init_db()  # conftest points DB_PATH at a throwaway database
    db = get_session_factory()()
    try:
        now = datetime.now(timezone.utc)
        db.add_all([
            ExtractionRun(run_id="stuck-1", platform="youtube", account_id="default", job_type="full",
                          status="running", started_at=now),
            ExtractionRun(run_id="done-1", platform="youtube", account_id="default", job_type="full",
                          status="completed", started_at=now, completed_at=now),
        ])
        db.commit()
    finally:
        db.close()

    assert close_interrupted_runs() >= 1

    db = get_session_factory()()
    try:
        stuck = db.query(ExtractionRun).filter_by(run_id="stuck-1").one()
        assert stuck.status == "failed" and stuck.error_message == INTERRUPTED and stuck.completed_at
        assert db.query(ExtractionRun).filter_by(run_id="done-1").one().status == "completed"
    finally:
        db.close()
