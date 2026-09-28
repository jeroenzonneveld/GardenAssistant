"""Binary sensors for Garden Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUS_DUE
from .coordinator import GardenConfigEntry, GardenCoordinator
from .entity import GardenPlantEntity, task_label

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    for subentry_id in coordinator.plant_subentries():
        async_add_entities(
            [NeedsAttentionBinarySensor(coordinator, subentry_id)],
            config_subentry_id=subentry_id,
        )


class NeedsAttentionBinarySensor(GardenPlantEntity, BinarySensorEntity):
    """On when any task of the plant is due."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "needs_attention"

    def __init__(self, coordinator: GardenCoordinator, subentry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, subentry_id)
        self._attr_unique_id = f"{subentry_id}_needs_attention"

    @property
    def is_on(self) -> bool:
        """Return True when a task is due."""
        plant = self.plant
        return plant.needs_attention if plant else False

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the due tasks."""
        plant = self.plant
        due = (
            [task_label(t) for t in plant.tasks.values() if t.status == STATUS_DUE]
            if plant
            else []
        )
        return {"due_tasks": due}
