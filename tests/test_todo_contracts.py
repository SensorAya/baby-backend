import asyncio
import os
import unittest
from uuid import uuid4

from pydantic import ValidationError

for key, value in {
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_DB": "test",
    "LLM_API_KEY": "test",
    "LLM_BASE_URL": "https://example.invalid/v1",
    "LLM_MODEL": "test",
}.items():
    os.environ.setdefault(key, value)

from app.alarms.broker import AlarmBroker  # noqa: E402
from app.main import app  # noqa: E402
from app.monitoring.periods import AggregationPeriod  # noqa: E402
from app.monitoring.query import _history_item  # noqa: E402
from app.monitoring.schemas import MonitoringRecordCreate  # noqa: E402
from app.reports.query import REPORT_ANALYSIS_VERSION, _COMMON_CTE  # noqa: E402
from app.reports.routes import MonitoringReportRequest, ReportPeriod  # noqa: E402


class HeartbeatContractTests(unittest.TestCase):
    def test_exact_heartbeat_contract_accepts_nullable_event(self) -> None:
        heartbeat = MonitoringRecordCreate.model_validate(
            {
                "timestamp": 1752001234,
                "face_ratio": 85,
                "face_center_x": 640,
                "face_center_y": 360,
                "event": None,
                "baby_center_x": 640,
                "baby_center_y": 360,
                "baby_ratio": 85,
                "activity_level": 30,
            }
        )
        self.assertIsNone(heartbeat.event)
        self.assertEqual(heartbeat.activity_level, 30)

    def test_negative_one_center_sentinel_is_accepted(self) -> None:
        payload = {
            "timestamp": 1752001234,
            "face_ratio": 0,
            "face_center_x": -1,
            "face_center_y": -1,
            "event": None,
            "baby_center_x": -1,
            "baby_center_y": -1,
            "baby_ratio": 0,
            "activity_level": 0,
        }
        heartbeat = MonitoringRecordCreate.model_validate(payload)
        self.assertEqual(heartbeat.face_center_x, -1)
        self.assertEqual(heartbeat.face_center_y, -1)
        self.assertEqual(heartbeat.baby_center_x, -1)
        self.assertEqual(heartbeat.baby_center_y, -1)

        for field in (
            "face_center_x",
            "face_center_y",
            "baby_center_x",
            "baby_center_y",
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                MonitoringRecordCreate.model_validate({**payload, field: -2})

    def test_event_is_required_and_activity_is_bounded(self) -> None:
        base = {
            "timestamp": 1,
            "face_ratio": 85,
            "face_center_x": 1,
            "face_center_y": 1,
            "baby_center_x": 1,
            "baby_center_y": 1,
            "baby_ratio": 85,
            "activity_level": 0,
        }
        with self.assertRaises(ValidationError):
            MonitoringRecordCreate.model_validate(base)
        with self.assertRaises(ValidationError):
            MonitoringRecordCreate.model_validate(
                {**base, "event": "start", "activity_level": 101}
            )

    def test_history_mapping_preserves_activity_bands(self) -> None:
        session_id = uuid4()
        item = _history_item(
            {
                "unit_key": str(session_id),
                "session_id": session_id,
                "started_at": 100,
                "ended_at": 140,
                "duration_seconds": 40,
                "session_count": 1,
                "sample_count": 4,
                "average_face_ratio": 80,
                "average_baby_ratio": 75,
                "average_activity_level": 20.75,
                "stationary_sample_count": 1,
                "minor_activity_sample_count": 2,
                "major_activity_sample_count": 1,
                "alarm_event_count": 1,
            },
            AggregationPeriod.SESSION,
        )
        self.assertEqual(item.session_id, session_id)
        self.assertEqual(item.sample_count, 4)
        self.assertEqual(item.average_activity_level, 20.75)


class ReportContractTests(unittest.TestCase):
    def test_report_supports_all_four_periods(self) -> None:
        for period in ReportPeriod:
            request = MonitoringReportRequest(period=period)
            self.assertEqual(request.period, period)

    def test_session_id_is_rejected_for_calendar_report(self) -> None:
        with self.assertRaises(ValidationError):
            MonitoringReportRequest(period="daily", session_id=uuid4())

    def test_openapi_exposes_new_http_contracts(self) -> None:
        schema = app.openapi()
        self.assertIn("/api/alarms", schema["paths"])
        self.assertIn("/api/alarms/active", schema["paths"])
        heartbeat = schema["components"]["schemas"]["MonitoringRecordCreate"]
        self.assertTrue({"event", "activity_level"} <= set(heartbeat["required"]))
        for field in (
            "face_center_x",
            "face_center_y",
            "baby_center_x",
            "baby_center_y",
        ):
            self.assertEqual(heartbeat["properties"][field]["minimum"], -1)
        periods = schema["components"]["schemas"]["ReportPeriod"]["enum"]
        self.assertEqual(periods, ["session", "daily", "weekly", "monthly"])

    def test_report_center_aggregation_uses_negative_one_as_missing(self) -> None:
        self.assertEqual(REPORT_ANALYSIS_VERSION, "2.2")
        self.assertIn(
            "face_center_x >= 0\n            AND face_center_y >= 0",
            _COMMON_CTE,
        )
        self.assertIn(
            "baby_center_x >= 0\n            AND baby_center_y >= 0",
            _COMMON_CTE,
        )
        self.assertNotIn("face_center_x <> 0", _COMMON_CTE)
        self.assertNotIn("baby_center_x <> 0", _COMMON_CTE)


class AlarmBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_alarm_messages_are_isolated_by_user(self) -> None:
        broker = AlarmBroker()
        first_user = uuid4()
        second_user = uuid4()
        async with broker.subscribe(first_user) as first_queue:
            async with broker.subscribe(second_user) as second_queue:
                await broker.publish(first_user, {"type": "alarm", "active": True})
                self.assertTrue((await first_queue.get())["active"])
                with self.assertRaises(TimeoutError):
                    await asyncio.wait_for(second_queue.get(), timeout=0.01)


if __name__ == "__main__":
    unittest.main()
