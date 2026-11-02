import unittest
import uuid

from routes.tasks import _terminal_event
from task_manager import create_task_once, fail_task, finish_task, get_task
from tests.support import ROOT


class TaskRecoveryTests(unittest.TestCase):
    def test_retried_start_request_reuses_one_task(self):
        request_id = f"test-{uuid.uuid4()}"

        first_id, first_created = create_task_once(
            "summary",
            cohort="kpredict",
            request_id=request_id,
        )
        second_id, second_created = create_task_once(
            "summary",
            cohort="kpredict",
            request_id=request_id,
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(second_id, first_id)

    def test_completed_and_failed_results_remain_replayable(self):
        complete_id, _ = create_task_once("summary")
        finish_task(complete_id, {"summary": "ready"})
        self.assertEqual(
            _terminal_event(get_task(complete_id)),
            {"event": "complete", "data": {"summary": "ready"}},
        )

        failed_id, _ = create_task_once("chat")
        fail_task(failed_id, "upstream error")
        self.assertEqual(
            _terminal_event(get_task(failed_id)),
            {"event": "failed", "data": {"message": "upstream error"}},
        )

    def test_dashboard_recovers_instead_of_failing_on_first_stream_error(self):
        script = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn('headers: { "X-XPRS-Request-ID": requestId }', script)
        self.assertIn("startTaskWithRecovery", script)
        self.assertIn("pollTaskStatus", script)
        self.assertIn("recovering the running task automatically", script)
        self.assertNotIn('finish(reject, new Error("Task stream connection lost"))', script)


if __name__ == "__main__":
    unittest.main()
