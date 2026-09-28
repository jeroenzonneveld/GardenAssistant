"""To-do list for Garden Assistant."""

from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUS_DUE, STATUS_UPCOMING
from .coordinator import GardenConfigEntry, GardenCoordinator
from .entity import GardenEntity, task_label

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the to-do list."""
    async_add_entities([GardenTodoList(entry.runtime_data)])


class GardenTodoList(GardenEntity, TodoListEntity):
    """To-do list of due and upcoming garden tasks."""

    _attr_translation_key = "garden_tasks"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, coordinator: GardenCoordinator) -> None:
        """Initialize the list."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_todo"

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return due and upcoming tasks."""
        items: list[TodoItem] = []
        for plant in (self.coordinator.data or {}).values():
            for snap in plant.tasks.values():
                if snap.status not in (STATUS_DUE, STATUS_UPCOMING):
                    continue
                parts = []
                if snap.due:
                    parts.append(f"Due: {snap.due.isoformat()}")
                if location := plant.data.get("location"):
                    parts.append(f"Location: {location}")
                items.append(
                    TodoItem(
                        summary=f"{task_label(snap)}: {plant.name}",
                        uid=f"{plant.subentry_id}:{snap.task}",
                        status=TodoItemStatus.NEEDS_ACTION,
                        due=snap.due,
                        description="\n".join(parts) or None,
                    )
                )
        items.sort(key=lambda i: (i.due is None, i.due, i.summary or ""))
        return items

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Complete a task; other edits are not supported."""
        if not item.uid or ":" not in item.uid:
            raise ServiceValidationError("Unknown to-do item")
        if item.status != TodoItemStatus.COMPLETED:
            raise ServiceValidationError("Garden tasks can only be marked as completed")
        subentry_id, _, task = item.uid.rpartition(":")
        if self.coordinator.get_task(subentry_id, task) is None:
            raise ServiceValidationError("This task no longer exists")
        try:
            await self.coordinator.async_complete_task(subentry_id, task)
        except KeyError as err:
            raise HomeAssistantError(str(err)) from err
