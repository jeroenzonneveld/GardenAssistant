"""Buttons for Garden Assistant."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenConfigEntry, GardenCoordinator
from .entity import GardenTaskEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    for subentry_id in coordinator.plant_subentries():
        plant = (coordinator.data or {}).get(subentry_id)
        if not plant:
            continue
        async_add_entities(
            [MarkDoneButton(coordinator, subentry_id, task) for task in plant.tasks],
            config_subentry_id=subentry_id,
        )


class MarkDoneButton(GardenTaskEntity, ButtonEntity):
    """Mark a task as done."""

    def __init__(
        self, coordinator: GardenCoordinator, subentry_id: str, task: str
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, subentry_id, task)
        self._attr_unique_id = f"{subentry_id}_{task}_done"
        self._attr_translation_key = f"mark_done_{task}"

    async def async_press(self) -> None:
        """Complete the task."""
        try:
            await self.coordinator.async_complete_task(self._subentry_id, self._task)
        except KeyError as err:
            raise HomeAssistantError(str(err)) from err
