"""State storage and coordinator for Garden Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CREATED,
    CONF_CUSTOM_TASK_NAME,
    CONF_INTERVAL_DAYS,
    CONF_LEAD_DAYS,
    CONF_MONTHS,
    CONF_NAME,
    CONF_TASKS,
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_TASK_COMPLETED,
    STATUS_DUE,
    STATUS_INACTIVE,
    STATUS_SCHEDULED,
    STATUS_UPCOMING,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_TYPE_PLANT,
    TASK_CUSTOM,
    TASK_TYPES,
)
from .scheduler import TaskSchedule, TaskState, next_due

_LOGGER = logging.getLogger(__name__)

type GardenConfigEntry = ConfigEntry[GardenCoordinator]


@dataclass(slots=True)
class TaskSnapshot:
    """Computed view of one task of one plant."""

    subentry_id: str
    task: str
    name: str  # display name for custom tasks, else the task type
    schedule: TaskSchedule
    last_done: date | None
    snoozed_until: date | None
    due: date | None
    days_until: int | None
    status: str


@dataclass(slots=True)
class PlantSnapshot:
    """Computed view of one plant."""

    subentry_id: str
    name: str
    data: dict[str, Any]
    created: date
    tasks: dict[str, TaskSnapshot] = field(default_factory=dict)

    @property
    def needs_attention(self) -> bool:
        """Return True if any task is due."""
        return any(t.status == STATUS_DUE for t in self.tasks.values())

    @property
    def next_task(self) -> TaskSnapshot | None:
        """Return the task with the earliest due date."""
        dated = [t for t in self.tasks.values() if t.due is not None]
        return min(dated, key=lambda t: t.due) if dated else None  # type: ignore[arg-type, return-value]


type GardenData = dict[str, PlantSnapshot]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def plant_created(subentry: ConfigSubentry) -> date:
    """Return the date the plant was added (falls back to today)."""
    return _parse_date(subentry.data.get(CONF_CREATED)) or dt_util.now().date()


class GardenCoordinator(DataUpdateCoordinator[GardenData]):
    """Holds task progress and computes due dates for all plants.

    Plant definitions live in config subentries (type ``plant``). Progress
    (last done, snoozes, notification bookkeeping) lives in a Store keyed by
    subentry id and task type::

        {"plants": {"<subentry_id>": {"<task>": {"last_done": "2026-03-01",
                                                  "snoozed_until": None,
                                                  "notified_due": None}}}}
    """

    config_entry: GardenConfigEntry

    def __init__(self, hass: HomeAssistant, entry: GardenConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self._state: dict[str, Any] = {"plants": {}}
        self._unsub_midnight: CALLBACK_TYPE | None = None

    @property
    def options(self) -> dict[str, Any]:
        """Return entry options merged over defaults."""
        return {**DEFAULT_OPTIONS, **self.config_entry.options}

    async def async_load(self) -> None:
        """Load persisted state and start the daily refresh."""
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("plants"), dict):
            self._state = stored
        if self._prune_removed_plants():
            await self._store.async_save(self._state)
        self._unsub_midnight = async_track_time_change(
            self.hass, self._handle_midnight, hour=0, minute=0, second=5
        )

    @callback
    def async_unload(self) -> None:
        """Stop timers."""
        if self._unsub_midnight:
            self._unsub_midnight()
            self._unsub_midnight = None

    @callback
    def _handle_midnight(self, _now: Any) -> None:
        self.async_set_updated_data(self._compute())

    def plant_subentries(self) -> dict[str, ConfigSubentry]:
        """Return the plant subentries of this entry."""
        return {
            sid: sub
            for sid, sub in self.config_entry.subentries.items()
            if sub.subentry_type == SUBENTRY_TYPE_PLANT
        }

    def _prune_removed_plants(self) -> bool:
        """Drop progress of plants that no longer exist; return True if changed."""
        known = set(self.plant_subentries())
        plants: dict[str, Any] = self._state["plants"]
        removed = [sid for sid in plants if sid not in known]
        for sid in removed:
            plants.pop(sid)
        return bool(removed)

    def _task_state(self, subentry_id: str, task: str) -> dict[str, Any]:
        plant = self._state["plants"].setdefault(subentry_id, {})
        return plant.setdefault(task, {})

    def raw_task_state(self, subentry_id: str, task: str) -> dict[str, Any]:
        """Return the mutable stored state for a task (for notification bookkeeping)."""
        return self._task_state(subentry_id, task)

    async def _async_update_data(self) -> GardenData:
        return self._compute()

    def _compute(self) -> GardenData:
        today = dt_util.now().date()
        lead_days = int(self.options.get(CONF_LEAD_DAYS, 0))
        data: GardenData = {}
        for sid, sub in self.plant_subentries().items():
            created = plant_created(sub)
            plant = PlantSnapshot(
                subentry_id=sid,
                name=sub.data.get(CONF_NAME) or sub.title,
                data=dict(sub.data),
                created=created,
            )
            tasks_cfg: dict[str, Any] = sub.data.get(CONF_TASKS, {})
            for task in TASK_TYPES:
                cfg = tasks_cfg.get(task)
                if not cfg:
                    continue
                schedule = TaskSchedule.from_parts(
                    cfg.get(CONF_MONTHS), cfg.get(CONF_INTERVAL_DAYS)
                )
                if not schedule.active:
                    continue
                stored = self._state["plants"].get(sid, {}).get(task, {})
                state = TaskState(
                    last_done=_parse_date(stored.get("last_done")),
                    snoozed_until=_parse_date(stored.get("snoozed_until")),
                )
                due = next_due(schedule, state, today, created)
                days_until = (due - today).days if due else None
                if due is None:
                    status = STATUS_INACTIVE
                elif days_until is not None and days_until <= 0:
                    status = STATUS_DUE
                elif days_until is not None and days_until <= lead_days:
                    status = STATUS_UPCOMING
                else:
                    status = STATUS_SCHEDULED
                name = task
                if task == TASK_CUSTOM:
                    name = cfg.get(CONF_CUSTOM_TASK_NAME) or task
                plant.tasks[task] = TaskSnapshot(
                    subentry_id=sid,
                    task=task,
                    name=name,
                    schedule=schedule,
                    last_done=state.last_done,
                    snoozed_until=state.snoozed_until,
                    due=due,
                    days_until=days_until,
                    status=status,
                )
            data[sid] = plant
        return data

    def get_task(self, subentry_id: str, task: str) -> TaskSnapshot | None:
        """Return a task snapshot if it exists."""
        plant = (self.data or {}).get(subentry_id)
        return plant.tasks.get(task) if plant else None

    async def async_complete_task(
        self, subentry_id: str, task: str, when: date | None = None
    ) -> None:
        """Mark a task as done."""
        self._require_task(subentry_id, task)
        when = when or dt_util.now().date()
        state = self._task_state(subentry_id, task)
        state["last_done"] = when.isoformat()
        state["snoozed_until"] = None
        state["notified_due"] = None
        await self._async_save_and_refresh()
        plant = self.data.get(subentry_id)
        self.hass.bus.async_fire(
            EVENT_TASK_COMPLETED,
            {
                "entry_id": self.config_entry.entry_id,
                "subentry_id": subentry_id,
                "plant": plant.name if plant else None,
                "task": task,
                "date": when.isoformat(),
            },
        )

    async def async_snooze_task(self, subentry_id: str, task: str, days: int) -> None:
        """Postpone a task by a number of days from today."""
        self._require_task(subentry_id, task)
        until = dt_util.now().date() + timedelta(days=max(1, int(days)))
        state = self._task_state(subentry_id, task)
        state["snoozed_until"] = until.isoformat()
        await self._async_save_and_refresh()

    async def async_save(self) -> None:
        """Persist state without recomputing (used for notification bookkeeping)."""
        await self._store.async_save(self._state)

    async def _async_save_and_refresh(self) -> None:
        await self._store.async_save(self._state)
        self.async_set_updated_data(self._compute())

    def _require_task(self, subentry_id: str, task: str) -> None:
        if subentry_id not in self.plant_subentries():
            raise KeyError(f"Unknown plant {subentry_id}")
        if task not in TASK_TYPES:
            raise KeyError(f"Unknown task {task}")

    async def async_remove_store(self) -> None:
        """Delete the store (entry removed)."""
        await self._store.async_remove()
