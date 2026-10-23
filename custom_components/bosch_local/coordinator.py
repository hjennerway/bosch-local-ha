"""Store local schedules and publish a single immediate start when due."""
import asyncio
import json
import logging
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time, async_track_state_change_event, async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .schedule import program_payload, validate_start
from .explanations import explain_automation, source_explanation

_LOGGER = logging.getLogger(__name__)


class Dishwasher:
    """Shared state; all mutation is serialized with a lock."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.programs = entry.data["programs"]
        self.program = next(iter(self.programs))
        self.start = None
        self.armed = False
        self.last_run = None
        self.error = None
        self.automatic = False
        self.pending = False
        self.listeners = set()
        self._timer = None
        self._unsubs = []
        self._lock = asyncio.Lock()
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    async def async_load(self):
        data = await self._store.async_load() or {}
        self.program = data.get("program", self.program)
        self.start = dt_util.parse_datetime(data.get("start") or "")
        self.last_run = dt_util.parse_datetime(data.get("last_run") or "")
        self.armed = bool(data.get("armed"))
        self.error = data.get("error")
        self.automatic = bool(data.get("automatic", False))
        self.pending = bool(data.get("pending", False))
        if self.program not in self.programs or (self.start and self.start.tzinfo is None):
            self.start = None
            self.armed = False
            self.error = "Stored schedule is invalid; set it again."

    @callback
    def async_listen(self):
        self._unsubs.append(async_track_state_change_event(
            self.hass, [self.entry.data["operation_state_entity"], self.entry.data["door_entity"]], self._state_changed))
        self._unsubs.append(async_track_time_change(self.hass, self._auto_check, minute=[0, 30], second=0))
        self._unsubs.append(async_at_started(self.hass, self._started))

    async def _started(self, _hass):
        async with self._lock:
            if self.last_run is None:
                old = self.hass.states.get(self.entry.data.get("last_run_entity", ""))
                if old:
                    parsed = dt_util.parse_datetime(old.state)
                    if parsed:
                        self.last_run = dt_util.as_utc(parsed)
                        await self._save()
            if self.armed:
                if not self.start or self.start <= dt_util.utcnow():
                    self.armed = False
                    self.automatic = False
                    self.error = "Schedule elapsed while Home Assistant was offline; set a new start time."
                    await self._save()
                else:
                    self._schedule()
        await self._auto_check()

    @callback
    def async_close(self):
        self._cancel_timer()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _cancel_timer(self):
        if self._timer:
            self._timer()
            self._timer = None

    @callback
    def _schedule(self):
        self._cancel_timer()
        if self.armed and self.start:
            self._timer = async_track_point_in_utc_time(self.hass, self._due, self.start)

    async def _save(self):
        await self._store.async_save({
            "program": self.program, "start": self.start.isoformat() if self.start else None,
            "armed": self.armed, "last_run": self.last_run.isoformat() if self.last_run else None,
            "error": self.error,
            "automatic": self.automatic,
            "pending": self.pending,
        })
        self._notify()

    @callback
    def _notify(self):
        for listener in tuple(self.listeners):
            listener()

    def automation_diagnostics(self):
        """Describe the exact scheduling prerequisites using current HA states."""
        checks = {}
        for key, config_key, expected in (
            ("door", "door_entity", ["Closed"]),
            ("operation", "operation_state_entity", ["Ready", "Inactive", "Finished"]),
        ):
            entity_id = self.entry.data[config_key]
            state = self.hass.states.get(entity_id)
            current = state.state if state else None
            checks[key] = {
                "entity_id": entity_id,
                "current": current,
                "expected": expected,
                "matches": current in expected,
                "availability": "missing" if state is None else (
                    current if current in ("unknown", "unavailable") else "available"),
            }
        now = dt_util.utcnow()
        age = (now - self.last_run).total_seconds() if self.last_run else None
        checks["last_completed_wash"] = {
            "current": self.last_run.isoformat() if self.last_run else None,
            "expected": "A recorded completion at least 48 hours ago",
            "age_hours": round(age / 3600, 2) if age is not None else None,
            "eligible_at": (self.last_run + timedelta(hours=48)).isoformat() if self.last_run else None,
            "matches": age is not None and age >= 172800,
            "import_entity_id": self.entry.data.get("last_run_entity"),
        }
        for key, current, expected in (
            ("automatic_enabled", self.automatic, True),
            ("schedule_armed", self.armed, False),
            ("start_pending", self.pending, False),
            ("nightwash_configured", "NightWash" in self.programs, True),
        ):
            checks[key] = {"current": current, "expected": expected, "matches": current == expected}
        for key in ("door", "operation"):
            checks[key]["explanation"] = source_explanation(key, checks[key])
        summary, reasons = explain_automation(checks)
        return {
            "summary": summary,
            "reasons": reasons,
            "meaning": "Whether a new automatic NightWash schedule can be created",
            "ready": all(check["matches"] for check in checks.values()),
            "blocking_reasons": [key for key, check in checks.items() if not check["matches"]],
            "checks": checks,
            "evaluated_at": now.isoformat(),
        }

    async def async_select(self, program):
        async with self._lock:
            if program not in self.programs:
                raise HomeAssistantError("Unknown dishwasher program")
            self.program = program
            await self._save()

    async def async_set_start(self, value):
        async with self._lock:
            try:
                value = validate_start(value)
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err
            self.start = value
            self.error = None
            await self._save()
            self._schedule()

    async def async_arm(self, armed):
        async with self._lock:
            if armed:
                try:
                    if self.start is None:
                        raise ValueError("Set a future start time first")
                    validate_start(self.start)
                    program_payload(self.program, self.programs)
                except ValueError as err:
                    raise HomeAssistantError(str(err)) from err
            self.armed = armed
            if armed:
                self.pending = False
            else:
                self.automatic = False
            self.error = None
            await self._save()
            self._schedule()

    async def async_clear(self):
        """Cancel only our local timer. Never write program=0 or abort a wash."""
        async with self._lock:
            self._cancel_timer()
            self.armed = False
            self.start = None
            self.automatic = False
            # A sent start cannot be withdrawn by clearing a local timer.
            self.error = None
            await self._save()

    def _ready(self):
        operation = self.hass.states.get(self.entry.data["operation_state_entity"])
        door = self.hass.states.get(self.entry.data["door_entity"])
        return bool(operation and operation.state in ("Ready", "Inactive", "Finished")
                    and door and door.state == "Closed")

    async def async_set_automatic(self, enabled):
        async with self._lock:
            self.automatic = enabled
            await self._save()
        await self._auto_check()

    async def _auto_check(self, _now=None):
        # Refresh diagnostics even when a changed source state blocks scheduling.
        # This is an in-memory notification, not a persistent storage write.
        try:
            await self._evaluate_automatic()
        finally:
            self._notify()

    async def _evaluate_automatic(self):
        async with self._lock:
            if not self.automatic or self.armed or self.pending or not self.last_run or not self._ready():
                return
            if dt_util.utcnow() - self.last_run < timedelta(hours=48):
                return
            # Home Assistant's configured timezone determines the next local 01:00.
            now = dt_util.now()
            target = now.replace(hour=1, minute=0, second=0, microsecond=0, fold=0)
            if target <= now:
                target = (now + timedelta(days=1)).replace(hour=1, minute=0, second=0, microsecond=0, fold=0)
            self.program = "NightWash"
            if self.program not in self.programs:
                self.error = "Configure NightWash before enabling automatic scheduling."
                await self._save()
                return
            self.start = dt_util.as_utc(target)
            self.armed = True
            self.error = None
            await self._save()
            self._schedule()

    async def _due(self, _now):
        async with self._lock:
            if not self.armed or not self.start:
                return
            # An old callback may already be queued when the user reschedules.
            if self.start > dt_util.utcnow():
                self._schedule()
                return
            self._timer = None
            self.armed = False
            self.error = None
            # Persist disarming BEFORE publication to prevent replay after a restart.
            await self._save()
            if not self._ready():
                self.error = "Start skipped: dishwasher must be idle with its door closed."
                self.automatic = False
            elif dt_util.utcnow() - self.start > timedelta(minutes=5):
                self.error = "Start skipped: schedule was more than five minutes late."
                self.automatic = False
            else:
                try:
                    self.pending = True
                    await self._save()
                    await mqtt.async_publish(
                        self.hass, self.entry.data["topic"] + "/activeProgram",
                        json.dumps(program_payload(self.program, self.programs)), qos=0, retain=False,
                    )
                except Exception:
                    _LOGGER.exception("Unable to publish dishwasher start")
                    self.error = "Start could not be published; check MQTT and re-arm manually."
                    self.automatic = False
                    self.pending = False
            await self._save()

    async def _state_changed(self, event):
        old = event.data.get("old_state")
        new = event.data.get("new_state")
        if event.data.get("entity_id") != self.entry.data["operation_state_entity"]:
            await self._auto_check()
            return
        # Restoring a retained Finished state is not evidence of a completed wash.
        if old and old.state not in ("unknown", "unavailable", "Finished") and new and new.state == "Finished":
            async with self._lock:
                self.last_run = dt_util.utcnow()
                self._cancel_timer()
                self.armed = False
                self.start = None
                self.pending = False
                await self._save()
        elif new and new.state == "Run":
            async with self._lock:
                self._cancel_timer()
                self.armed = False
                self.pending = False
                await self._save()
        await self._auto_check()
