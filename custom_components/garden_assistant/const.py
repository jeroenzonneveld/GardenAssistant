"""Constants for the Garden Assistant integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "garden_assistant"

SUBENTRY_TYPE_PLANT: Final = "plant"

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.state"

# Task types. The order here is the order shown in the UI.
TASK_PRUNE: Final = "prune"
TASK_FERTILIZE: Final = "fertilize"
TASK_WATER: Final = "water"
TASK_HARVEST: Final = "harvest"
TASK_SOW: Final = "sow"
TASK_PROTECT: Final = "protect"
TASK_CUSTOM: Final = "custom"

TASK_TYPES: Final = (
    TASK_PRUNE,
    TASK_FERTILIZE,
    TASK_WATER,
    TASK_HARVEST,
    TASK_SOW,
    TASK_PROTECT,
    TASK_CUSTOM,
)

# Plant subentry data keys
CONF_NAME: Final = "name"
CONF_PRESET: Final = "preset"
CONF_SPECIES: Final = "species"
CONF_LOCATION: Final = "location"
CONF_NOTES: Final = "notes"
CONF_TASKS: Final = "tasks"
CONF_MONTHS: Final = "months"
CONF_INTERVAL_DAYS: Final = "interval_days"
CONF_CUSTOM_TASK_NAME: Final = "custom_task_name"
CONF_CREATED: Final = "created"

PRESET_CUSTOM: Final = "custom"

# Main entry option keys
CONF_HEMISPHERE: Final = "hemisphere"
CONF_NOTIFY_ENABLED: Final = "notify_enabled"
CONF_NOTIFY_SERVICES: Final = "notify_services"
CONF_NOTIFY_PERSISTENT: Final = "notify_persistent"
CONF_NOTIFY_TIME: Final = "notify_time"
CONF_LEAD_DAYS: Final = "lead_days"
CONF_REPEAT_DAILY: Final = "repeat_daily"
CONF_ACTIONABLE: Final = "actionable_notifications"

HEMISPHERE_NORTH: Final = "north"
HEMISPHERE_SOUTH: Final = "south"

DEFAULT_OPTIONS: Final = {
    CONF_HEMISPHERE: HEMISPHERE_NORTH,
    CONF_NOTIFY_ENABLED: False,
    CONF_NOTIFY_SERVICES: [],
    CONF_NOTIFY_PERSISTENT: True,
    CONF_NOTIFY_TIME: "08:00:00",
    CONF_LEAD_DAYS: 0,
    CONF_REPEAT_DAILY: False,
    CONF_ACTIONABLE: True,
}

# Task status values
STATUS_DUE: Final = "due"  # due date is today or in the past
STATUS_UPCOMING: Final = "upcoming"  # within the configured lead days
STATUS_SCHEDULED: Final = "scheduled"  # further in the future
STATUS_INACTIVE: Final = "inactive"  # no schedule configured

# Events
EVENT_TASK_DUE: Final = f"{DOMAIN}_task_due"
EVENT_TASK_COMPLETED: Final = f"{DOMAIN}_task_completed"

# Services
SERVICE_COMPLETE_TASK: Final = "complete_task"
SERVICE_SNOOZE_TASK: Final = "snooze_task"
ATTR_TASK: Final = "task"
ATTR_DATE: Final = "date"
ATTR_DAYS: Final = "days"

# Mobile app actionable notification prefix: GARDEN_DONE|<subentry_id>|<task>
NOTIFY_ACTION_DONE: Final = "GARDEN_DONE"
NOTIFY_ACTION_SNOOZE: Final = "GARDEN_SNOOZE"
