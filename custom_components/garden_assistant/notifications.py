"""Daily due-task notifications for Garden Assistant."""

from __future__ import annotations

from datetime import date, time
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTIONABLE,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_PERSISTENT,
    CONF_NOTIFY_SERVICES,
    CONF_NOTIFY_TIME,
    CONF_REPEAT_DAILY,
    EVENT_TASK_DUE,
    NOTIFY_ACTION_DONE,
    NOTIFY_ACTION_SNOOZE,
    STATUS_DUE,
    STATUS_UPCOMING,
    TASK_CUSTOM,
)
from .coordinator import GardenCoordinator, TaskSnapshot
from .plant_library import TASK_LABELS

_LOGGER = logging.getLogger(__name__)

MOBILE_APP_ACTION_EVENT = "mobile_app_notification_action"
PERSISTENT_NOTIFICATION_ID = "garden_assistant_due"
NOTIFICATION_TITLE = "Garden Assistant"
MAX_ACTIONABLE_MESSAGES = 10
DEFAULT_NOTIFY_TIME = time(8, 0, 0)


def _plural_days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def describe_due(days_until: int | None) -> str:
    """Return a human readable due phrase."""
    if days_until is None:
        return "scheduled"
    if days_until == 0:
        return "due today"
    if days_until > 0:
        return f"due in {_plural_days(days_until)}"
    return f"overdue by {_plural_days(-days_until)}"


class GardenNotifier:
    """Sends events and notifications for due tasks once per day."""

    def __init__(self, hass: HomeAssistant, coordinator: GardenCoordinator) -> None:
        """Initialize the notifier."""
        self.hass = hass
        self.coordinator = coordinator
        self._unsub_time: CALLBACK_TYPE | None = None
        self._unsub_action: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Start the daily timer and the mobile action listener."""
        notify_time = self._notify_time()
        self._unsub_time = async_track_time_change(
            self.hass,
            self._handle_time,
            hour=notify_time.hour,
            minute=notify_time.minute,
            second=notify_time.second,
        )
        self._unsub_action = self.hass.bus.async_listen(
            MOBILE_APP_ACTION_EVENT, self._handle_action
        )

    @callback
    def async_stop(self) -> None:
        """Stop timers and listeners."""
        if self._unsub_time:
            self._unsub_time()
            self._unsub_time = None
        if self._unsub_action:
            self._unsub_action()
            self._unsub_action = None

    def _notify_time(self) -> time:
        raw = self.coordinator.options.get(CONF_NOTIFY_TIME)
        parsed = dt_util.parse_time(raw) if isinstance(raw, str) else None
        if parsed is None:
            _LOGGER.warning(
                "Invalid notify time %r, using %s", raw, DEFAULT_NOTIFY_TIME
            )
            return DEFAULT_NOTIFY_TIME
        return parsed

    @callback
    def _handle_time(self, now: Any) -> None:
        self.hass.async_create_task(
            self.async_run(now), name="garden_assistant daily notification"
        )

    # ------------------------------------------------------------------ run

    def _task_label(self, snap: TaskSnapshot) -> str:
        if snap.task == TASK_CUSTOM:
            return snap.name
        return TASK_LABELS.get(snap.task, snap.task)

    def _plant_name(self, subentry_id: str) -> str:
        plant = (self.coordinator.data or {}).get(subentry_id)
        return plant.name if plant else subentry_id

    def _line(self, snap: TaskSnapshot) -> str:
        return (
            f"{self._plant_name(snap.subentry_id)}: {self._task_label(snap)} "
            f"({describe_due(snap.days_until)})"
        )

    def _pending_tasks(self) -> list[TaskSnapshot]:
        tasks = [
            snap
            for plant in (self.coordinator.data or {}).values()
            for snap in plant.tasks.values()
            if snap.status in (STATUS_DUE, STATUS_UPCOMING) and snap.due is not None
        ]
        tasks.sort(key=lambda t: (t.due or date.max, self._plant_name(t.subentry_id)))
        return tasks

    async def async_run(self, now: Any = None) -> None:
        """Evaluate tasks, fire events and send notifications."""
        await self.coordinator.async_refresh()
        options = self.coordinator.options
        repeat_daily = bool(options.get(CONF_REPEAT_DAILY))

        pending = self._pending_tasks()
        if not pending:
            self._dismiss_persistent()
            return

        to_notify: list[TaskSnapshot] = []
        for snap in pending:
            assert snap.due is not None
            state = self.coordinator.raw_task_state(snap.subentry_id, snap.task)
            due_iso = snap.due.isoformat()
            if not repeat_daily and state.get("notified_due") == due_iso:
                continue
            state["notified_due"] = due_iso
            to_notify.append(snap)
            self.hass.bus.async_fire(
                EVENT_TASK_DUE,
                {
                    "entry_id": self.coordinator.config_entry.entry_id,
                    "subentry_id": snap.subentry_id,
                    "plant": self._plant_name(snap.subentry_id),
                    "task": snap.task,
                    "task_name": self._task_label(snap),
                    "due": due_iso,
                    "days_until": snap.days_until,
                    "status": snap.status,
                },
            )

        if to_notify:
            await self.coordinator.async_save()
            if options.get(CONF_NOTIFY_ENABLED):
                await self._async_send(to_notify)

    def _dismiss_persistent(self) -> None:
        persistent_notification.async_dismiss(self.hass, PERSISTENT_NOTIFICATION_ID)

    # ----------------------------------------------------------------- send

    async def _async_send(self, tasks: list[TaskSnapshot]) -> None:
        options = self.coordinator.options
        combined = "\n".join(self._line(t) for t in tasks)

        if options.get(CONF_NOTIFY_PERSISTENT):
            persistent_notification.async_create(
                self.hass,
                combined,
                title=NOTIFICATION_TITLE,
                notification_id=PERSISTENT_NOTIFICATION_ID,
            )

        actionable = bool(options.get(CONF_ACTIONABLE))
        for raw in options.get(CONF_NOTIFY_SERVICES) or []:
            service = str(raw).strip().removeprefix("notify.")
            if not service:
                continue
            if actionable and service.startswith("mobile_app_"):
                for snap in tasks[:MAX_ACTIONABLE_MESSAGES]:
                    await self._async_call_notify(
                        service,
                        self._line(snap),
                        {
                            "tag": f"garden_assistant_{snap.subentry_id}_{snap.task}",
                            "actions": [
                                {
                                    "action": "|".join(
                                        (
                                            NOTIFY_ACTION_DONE,
                                            snap.subentry_id,
                                            snap.task,
                                        )
                                    ),
                                    "title": "Done",
                                },
                                {
                                    "action": "|".join(
                                        (
                                            NOTIFY_ACTION_SNOOZE,
                                            snap.subentry_id,
                                            snap.task,
                                        )
                                    ),
                                    "title": "Snooze 1 day",
                                },
                            ],
                        },
                    )
                rest = tasks[MAX_ACTIONABLE_MESSAGES:]
                if rest:
                    await self._async_call_notify(
                        service, "\n".join(self._line(t) for t in rest), {}
                    )
            else:
                await self._async_call_notify(service, combined, {})

    async def _async_call_notify(
        self, service: str, message: str, data: dict[str, Any]
    ) -> None:
        if not self.hass.services.has_service("notify", service):
            _LOGGER.warning("Notify service notify.%s not found", service)
            return
        try:
            await self.hass.services.async_call(
                "notify",
                service,
                {"title": NOTIFICATION_TITLE, "message": message, "data": data},
                blocking=True,
            )
        except Exception:  # noqa: BLE001 - one broken service must not stop the rest
            _LOGGER.exception("Sending notification via notify.%s failed", service)

    # -------------------------------------------------------------- actions

    async def _handle_action(self, event: Event) -> None:
        """Handle Done/Snooze buttons of actionable notifications."""
        action = event.data.get("action")
        if not isinstance(action, str):
            return
        parts = action.split("|")
        if len(parts) != 3 or parts[0] not in (
            NOTIFY_ACTION_DONE,
            NOTIFY_ACTION_SNOOZE,
        ):
            return
        kind, subentry_id, task = parts
        if self.coordinator.get_task(subentry_id, task) is None:
            _LOGGER.debug("Ignoring notification action for unknown task %s", action)
            return
        try:
            if kind == NOTIFY_ACTION_DONE:
                await self.coordinator.async_complete_task(subentry_id, task)
            else:
                await self.coordinator.async_snooze_task(subentry_id, task, 1)
        except KeyError:
            _LOGGER.debug("Ignoring notification action for unknown task %s", action)
            return
        if not self._pending_tasks():
            self._dismiss_persistent()
