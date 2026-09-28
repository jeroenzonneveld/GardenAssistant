"""Sensors for Garden Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUS_DUE
from .coordinator import GardenConfigEntry, GardenCoordinator
from .entity import GardenEntity, GardenPlantEntity, GardenTaskEntity, task_label

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    for subentry_id in coordinator.plant_subentries():
        plant = (coordinator.data or {}).get(subentry_id)
        entities: list[SensorEntity] = [NextTaskSensor(coordinator, subentry_id)]
        if plant:
            entities.extend(
                TaskDueSensor(coordinator, subentry_id, task) for task in plant.tasks
            )
        async_add_entities(entities, config_subentry_id=subentry_id)
    async_add_entities([TasksDueSensor(coordinator)])


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


class TaskDueSensor(GardenTaskEntity, SensorEntity):
    """Due date of one task."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self, coordinator: GardenCoordinator, subentry_id: str, task: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, subentry_id, task)
        self._attr_unique_id = f"{subentry_id}_{task}_due"
        self._attr_translation_key = f"task_due_{task}"

    @property
    def native_value(self) -> date | None:
        """Return the due date."""
        snap = self.task_snapshot
        return snap.due if snap else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return task details."""
        snap = self.task_snapshot
        if snap is None:
            return None
        return {
            "task": snap.task,
            "status": snap.status,
            "days_until": snap.days_until,
            "last_done": _iso(snap.last_done),
            "snoozed_until": _iso(snap.snoozed_until),
            "months": sorted(snap.schedule.months),
            "interval_days": snap.schedule.interval_days,
        }


class NextTaskSensor(GardenPlantEntity, SensorEntity):
    """Name of the next task of a plant."""

    _attr_translation_key = "next_task"

    def __init__(self, coordinator: GardenCoordinator, subentry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, subentry_id)
        self._attr_unique_id = f"{subentry_id}_next_task"

    @property
    def native_value(self) -> str | None:
        """Return the display name of the next task."""
        plant = self.plant
        nxt = plant.next_task if plant else None
        return task_label(nxt) if nxt else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return next task details."""
        plant = self.plant
        nxt = plant.next_task if plant else None
        if nxt is None:
            return {"task": None, "due": None, "days_until": None}
        return {
            "task": nxt.task,
            "due": _iso(nxt.due),
            "days_until": nxt.days_until,
        }


class TasksDueSensor(GardenEntity, SensorEntity):
    """Number of tasks currently due in the whole garden."""

    _attr_translation_key = "tasks_due"
    _attr_native_unit_of_measurement = "tasks"

    def __init__(self, coordinator: GardenCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_tasks_due"

    def _due(self) -> list[dict[str, Any]]:
        return [
            {"plant": plant.name, "task": task_label(t), "due": _iso(t.due)}
            for plant in (self.coordinator.data or {}).values()
            for t in plant.tasks.values()
            if t.status == STATUS_DUE
        ]

    @property
    def native_value(self) -> int:
        """Return the number of due tasks."""
        return len(self._due())

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the due tasks."""
        return {"tasks": self._due()}
