"""Base entities for Garden Assistant."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_LOCATION,
    CONF_PRESET,
    CONF_SPECIES,
    DOMAIN,
    TASK_CUSTOM,
)
from .coordinator import GardenCoordinator, PlantSnapshot, TaskSnapshot
from .plant_library import TASK_LABELS


def task_label(task: TaskSnapshot) -> str:
    """Return the English display label of a task (custom name for custom tasks)."""
    if task.task == TASK_CUSTOM:
        return task.name
    return TASK_LABELS.get(task.task, task.task)


class GardenEntity(CoordinatorEntity[GardenCoordinator]):
    """Base class for garden-wide entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GardenCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Garden",
            entry_type=DeviceEntryType.SERVICE,
        )


class GardenPlantEntity(CoordinatorEntity[GardenCoordinator]):
    """Base class for entities that belong to one plant."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GardenCoordinator, subentry_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._subentry_id = subentry_id
        plant = (coordinator.data or {}).get(subentry_id)
        data = plant.data if plant else {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=plant.name if plant else subentry_id,
            model=data.get(CONF_SPECIES) or data.get(CONF_PRESET) or None,
            suggested_area=data.get(CONF_LOCATION) or None,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def plant(self) -> PlantSnapshot | None:
        """Return the current plant snapshot."""
        return (self.coordinator.data or {}).get(self._subentry_id)

    @property
    def available(self) -> bool:
        """Return False when the plant vanished from the coordinator data."""
        return super().available and self.plant is not None


class GardenTaskEntity(GardenPlantEntity):
    """Base class for entities that belong to one task of one plant."""

    def __init__(
        self, coordinator: GardenCoordinator, subentry_id: str, task: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, subentry_id)
        self._task = task
        plant = self.plant
        snapshot = plant.tasks.get(task) if plant else None
        if task == TASK_CUSTOM and snapshot is not None:
            self._attr_translation_placeholders = {"name": snapshot.name}

    @property
    def task_snapshot(self) -> TaskSnapshot | None:
        """Return the current task snapshot."""
        plant = self.plant
        return plant.tasks.get(self._task) if plant else None

    @property
    def available(self) -> bool:
        """Return False when the task vanished."""
        return super().available and self.task_snapshot is not None
