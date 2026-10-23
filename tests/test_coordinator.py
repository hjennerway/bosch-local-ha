"""Exercise scheduler behaviour with a small HA API boundary double.

These are not Home Assistant runtime integration tests.
"""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parents[1] / "custom_components/bosch_local"


def load_coordinator():
    modules = {}
    for name in ("homeassistant", "homeassistant.components", "homeassistant.components.mqtt",
                 "homeassistant.core", "homeassistant.exceptions", "homeassistant.helpers",
                 "homeassistant.helpers.event", "homeassistant.helpers.start",
                 "homeassistant.helpers.storage", "homeassistant.util", "homeassistant.util.dt"):
        modules[name] = ModuleType(name)
    modules["homeassistant.core"].callback = lambda function: function
    modules["homeassistant.exceptions"].HomeAssistantError = RuntimeError
    modules["homeassistant.helpers.storage"].Store = Mock
    for function in ("async_track_point_in_utc_time", "async_track_state_change_event", "async_track_time_change"):
        setattr(modules["homeassistant.helpers.event"], function, Mock(return_value=Mock()))
    modules["homeassistant.helpers.start"].async_at_started = Mock(return_value=Mock())
    package = ModuleType("bosch_test")
    package.__path__ = [str(ROOT)]
    modules["bosch_test"] = package
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("bosch_test.coordinator", ROOT / "coordinator.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


coordinator = load_coordinator()


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
        self.states = {
            "sensor.operation": SimpleNamespace(state="Ready"),
            "sensor.door": SimpleNamespace(state="Closed"),
        }
        hass = SimpleNamespace(states=SimpleNamespace(get=self.states.get))
        entry = SimpleNamespace(entry_id="test", data={
            "programs": {"NightWash": 8202}, "topic": "bosch_local/dishwasher",
            "operation_state_entity": "sensor.operation", "door_entity": "sensor.door",
        })
        self.device = coordinator.Dishwasher(hass, entry)
        self.device._store = SimpleNamespace(async_save=AsyncMock(), async_load=AsyncMock(return_value=None))
        coordinator.dt_util.utcnow = lambda: self.now
        coordinator.dt_util.now = lambda: self.now.astimezone(ZoneInfo("Europe/London"))
        coordinator.dt_util.as_utc = lambda value: value.astimezone(timezone.utc)
        coordinator.dt_util.parse_datetime = lambda value: datetime.fromisoformat(value) if value else None
        coordinator.mqtt.async_publish = AsyncMock()

    async def test_auto_schedules_next_one_am_after_48_hours(self):
        self.device.last_run = self.now - timedelta(hours=48)
        await self.device.async_set_automatic(True)
        self.assertTrue(self.device.armed)
        self.assertEqual(self.device.start, datetime(2026, 10, 24, 0, tzinfo=timezone.utc))
        coordinator.mqtt.async_publish.assert_not_awaited()

    async def test_auto_requires_history_idle_and_closed_door(self):
        await self.device.async_set_automatic(True)
        self.assertFalse(self.device.armed)
        self.device.last_run = self.now - timedelta(hours=47)
        await self.device._auto_check()
        self.assertFalse(self.device.armed)
        self.device.last_run = self.now - timedelta(hours=49)
        for entity, state in (("sensor.door", "Open"), ("sensor.operation", "DelayedStart")):
            old = self.states[entity]
            self.states[entity] = SimpleNamespace(state=state)
            await self.device._auto_check()
            self.assertFalse(self.device.armed)
            self.states[entity] = old

    async def test_clear_cancels_and_does_not_recreate_or_publish(self):
        self.device.last_run = self.now - timedelta(days=3)
        await self.device.async_set_automatic(True)
        cancel = self.device._timer
        await self.device.async_clear()
        cancel.assert_called_once()
        await self.device._auto_check()
        await self.device._due(self.now)
        self.assertIsNone(self.device.start)
        self.assertFalse(self.device.armed)
        self.assertFalse(self.device.automatic)
        coordinator.mqtt.async_publish.assert_not_awaited()

    async def test_due_publishes_once_without_delay_or_invalid_program(self):
        self.device.start = self.now
        self.device.armed = True
        await self.device._due(self.now)
        await self.device._due(self.now)
        coordinator.mqtt.async_publish.assert_awaited_once()
        args = coordinator.mqtt.async_publish.call_args
        self.assertEqual(args.args[1], "bosch_local/dishwasher/activeProgram")
        self.assertEqual(json.loads(args.args[2]), [{"program": 8202}])
        self.assertFalse(args.kwargs["retain"])
        self.assertTrue(self.device.pending)
        self.assertFalse(self.device.armed)
        self.assertFalse(self.device._store.async_save.await_args_list[0].args[0]["armed"])

    async def test_pending_start_cannot_be_automatically_repeated(self):
        self.device.start = self.now
        self.device.armed = self.device.automatic = True
        self.device.last_run = self.now - timedelta(days=3)
        await self.device._due(self.now)
        await self.device._auto_check()
        self.assertFalse(self.device.armed)
        coordinator.mqtt.async_publish.assert_awaited_once()

    async def test_future_reschedule_ignores_queued_old_callback(self):
        self.device.start = self.now + timedelta(hours=1)
        self.device.armed = True
        await self.device._due(self.now)
        self.assertTrue(self.device.armed)
        coordinator.mqtt.async_publish.assert_not_awaited()

    async def test_open_door_or_busy_does_not_start(self):
        for entity, state in (("sensor.door", "Open"), ("sensor.operation", "Run")):
            old = self.states[entity]
            self.states[entity] = SimpleNamespace(state=state)
            self.device.start = self.now
            self.device.armed = True
            await self.device._due(self.now)
            self.assertIsNotNone(self.device.error)
            self.assertFalse(self.device.armed)
            self.states[entity] = old
        coordinator.mqtt.async_publish.assert_not_awaited()

    async def test_finished_records_completion_but_not_retained_restore(self):
        def event(old):
            return SimpleNamespace(data={"entity_id": "sensor.operation",
                "old_state": SimpleNamespace(state=old) if old else None,
                "new_state": SimpleNamespace(state="Finished")})
        for old in (None, "unavailable", "unknown", "Finished"):
            await self.device._state_changed(event(old))
            self.assertIsNone(self.device.last_run)
        await self.device._state_changed(event("Run"))
        self.assertEqual(self.device.last_run, self.now)

    async def test_expired_restore_does_not_start_or_reschedule(self):
        self.device.armed = self.device.automatic = True
        self.device.last_run = self.now - timedelta(days=3)
        self.device.start = self.now - timedelta(minutes=1)
        await self.device._started(None)
        self.assertFalse(self.device.armed)
        self.assertFalse(self.device.automatic)
        self.assertIn("offline", self.device.error)
        coordinator.mqtt.async_publish.assert_not_awaited()

    async def test_publish_failure_disarms_and_surfaces_error(self):
        coordinator.mqtt.async_publish.side_effect = RuntimeError("offline")
        self.device.start = self.now
        self.device.armed = True
        with self.assertLogs(coordinator.__name__, level="ERROR"):
            await self.device._due(self.now)
        self.assertFalse(self.device.armed)
        self.assertFalse(self.device.pending)
        self.assertIn("MQTT", self.device.error)

    async def test_dst_uses_local_one_am_once(self):
        self.now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        self.device.last_run = self.now - timedelta(days=3)
        await self.device.async_set_automatic(True)
        self.assertEqual(self.device.start, datetime(2026, 10, 25, 0, tzinfo=timezone.utc))

    def test_diagnostics_explain_current_and_expected_source_states(self):
        self.states["sensor.door"].state = "Open"
        self.states["sensor.operation"].state = "DelayedStart"
        data = self.device.automation_diagnostics()
        door = data["checks"]["door"]
        self.assertEqual(door["entity_id"], "sensor.door")
        self.assertEqual(door["current"], "Open")
        self.assertEqual(door["expected"], ["Closed"])
        self.assertFalse(door["matches"])
        self.assertIn("door", data["blocking_reasons"])
        self.assertIn("operation", data["blocking_reasons"])

    def test_explanations_show_all_reasons_and_normal_scheduled_state(self):
        self.states["sensor.door"].state = "Open"
        self.states["sensor.operation"].state = "Run"
        data = self.device.automation_diagnostics()
        self.assertEqual(data["summary"], "Automatic NightWash is off")
        self.assertIn("Close the dishwasher door", data["reasons"])
        self.assertIn("Wash in progress", data["reasons"])
        self.assertTrue(any("No completed wash date" in reason for reason in data["reasons"]))
        self.device.armed = True
        self.assertEqual(self.device.automation_diagnostics()["summary"], "A wash is already scheduled")
        self.device.pending = True
        self.assertEqual(self.device.automation_diagnostics()["summary"], "Waiting for dishwasher to start")

    def test_explanations_distinguish_waiting_and_ready(self):
        self.device.automatic = True
        self.device.last_run = self.now - timedelta(hours=47)
        self.assertEqual(self.device.automation_diagnostics()["summary"],
                         "Waiting until 48 hours after the last completed wash")
        self.device.last_run = self.now - timedelta(hours=48)
        self.assertEqual(self.device.automation_diagnostics()["summary"],
                         "Ready to schedule the next 01:00 wash")

    def test_diagnostics_distinguish_missing_unknown_and_unavailable(self):
        for value, availability in ((None, "missing"), ("unknown", "unknown"),
                                    ("unavailable", "unavailable")):
            if value is None:
                self.states.pop("sensor.door", None)
            else:
                self.states["sensor.door"] = SimpleNamespace(state=value)
            check = self.device.automation_diagnostics()["checks"]["door"]
            self.assertEqual(check["availability"], availability)
            self.assertFalse(check["matches"])

    def test_diagnostics_cover_history_threshold_and_schedule_gates(self):
        self.device.automatic = True
        self.assertIn("last_completed_wash", self.device.automation_diagnostics()["blocking_reasons"])
        self.device.last_run = self.now - timedelta(hours=48) + timedelta(seconds=1)
        self.assertFalse(self.device.automation_diagnostics()["ready"])
        self.device.last_run = self.now - timedelta(hours=48)
        data = self.device.automation_diagnostics()
        self.assertTrue(data["ready"])
        self.assertEqual(data["checks"]["last_completed_wash"]["eligible_at"], self.now.isoformat())
        self.device.armed = self.device.pending = True
        self.device.programs = {}
        self.assertEqual(self.device.automation_diagnostics()["blocking_reasons"],
                         ["schedule_armed", "start_pending", "nightwash_configured"])

    async def test_blocked_source_update_refreshes_diagnostics_without_storage_write(self):
        listener = Mock()
        self.device.listeners.add(listener)
        self.states["sensor.door"].state = "Open"
        await self.device._state_changed(SimpleNamespace(data={
            "entity_id": "sensor.door", "old_state": SimpleNamespace(state="Closed"),
            "new_state": self.states["sensor.door"],
        }))
        listener.assert_called_once()
        self.device._store.async_save.assert_not_awaited()
        coordinator.mqtt.async_publish.assert_not_awaited()
