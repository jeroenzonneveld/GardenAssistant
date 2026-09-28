"""Calendar for Garden Assistant."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import GardenConfigEntry, GardenCoordinator, PlantSnapshot
from .entity import GardenEntity, task_label
from .scheduler import TaskState, occurrences

PARALLEL_UPDATES = 0

# Defensive upper bound for the range of events generated.
_MAX_RANGE = timedelta(days=2 * 365)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the calendar."""
    async_add_entities([GardenCalendar(entry.runtime_data)])


class GardenCalendar(GardenEntity, CalendarEntity):
    """Calendar with all projected garden tasks."""

    _attr_translation_key = "garden_calendar"

    def __init__(self, coordinator: GardenCoordinator) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_calendar"

    def _events(self, start: date, end: date) -> list[CalendarEvent]:
        """Return all-day events between start and end (inclusive)."""
        today = dt_util.now().date()
        start = max(start, today - timedelta(days=365))
        end = min(end, start + _MAX_RANGE)
        events: list[CalendarEvent] = []
        plant: PlantSnapshot
        for plant in (self.coordinator.data or {}).values():
            for snap in plant.tasks.values():
                state = TaskState(snap.last_done, snap.snoozed_until)
                label = task_label(snap)
                for due in occurrences(
                    snap.schedule, state, today, plant.created, start, end
                ):
                    description = f"{plant.name}"
                    if location := plant.data.get("location"):
                        description += f" ({location})"
                    events.append(
                        CalendarEvent(
                            start=due,
                            end=due + timedelta(days=1),
                            summary=f"{label}: {plant.name}",
                            description=description,
                            location=plant.data.get("location") or None,
                            uid=f"{plant.subentry_id}:{snap.task}:{due.isoformat()}",
                        )
                    )
        events.sort(key=lambda ev: (ev.start, ev.summary))
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming or current event."""
        today = dt_util.now().date()
        events = self._events(today, today + _MAX_RANGE)
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events in the requested range."""
        local_end = dt_util.as_local(end_date)
        start = dt_util.as_local(start_date).date()
        end = local_end.date()
        if local_end.time() == time.min:
            end -= timedelta(days=1)  # end_date is exclusive
        return self._events(start, end)
