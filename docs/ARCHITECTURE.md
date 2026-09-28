# Garden Assistant – architecture

Home Assistant custom integration (domain `garden_assistant`), installable via HACS.
Min HA version: **2025.4.0** (config subentries). Python 3.13, no external requirements.

## Concepts

* **One config entry** (`single_config_entry`) = the garden. Its **options** hold
  global settings (hemisphere, notifications).
* **Each plant is a config subentry** of type `plant` (`SUBENTRY_TYPE_PLANT`). Users add
  plants via the "Add plant" button on the integration page; they can reconfigure or
  delete them there too. Adding/removing/changing a subentry reloads the entry.
* **Plant subentry data** (`ConfigSubentry.data`):
  ```python
  {
      "name": "Front rose",  # CONF_NAME
      "preset": "rose",  # CONF_PRESET, key in plant_library.PLANT_LIBRARY or "custom"
      "species": "Rosa 'Iceberg'",  # CONF_SPECIES (optional, "" allowed)
      "location": "Front yard",  # CONF_LOCATION (optional)
      "notes": "",  # CONF_NOTES (optional)
      "created": "2026-09-28",  # CONF_CREATED, ISO date, set on creation, kept on reconfigure
      "tasks": {  # CONF_TASKS; only task types with a schedule are present
          "prune": {"months": [2, 3], "interval_days": 0},
          "fertilize": {"months": [4, 5, 6, 7], "interval_days": 28},
          "custom": {
              "months": [10],
              "interval_days": 0,
              "custom_task_name": "Remove suckers",
          },
      },
  }
  ```
  Months are ints 1–12 and are **already in the user's hemisphere** (presets are defined
  for the northern hemisphere; the config flow shifts them by 6 months when the entry
  option `hemisphere == "south"` before prefilling).
* **Task types** (`const.TASK_TYPES`): `prune, fertilize, water, harvest, sow, protect, custom`.
* **Scheduling** (`scheduler.py`, pure python, see module docstring): months-only = once per
  season; interval-only = every N days; both = every N days inside active months.
* **Progress state** (last done / snooze / notification bookkeeping) is stored by
  `GardenCoordinator` in a `Store`, not in the subentry.

## Core modules (done – do not change signatures without reason)

* `const.py` – all keys/constants.
* `scheduler.py` – `TaskSchedule`, `TaskState`, `next_due()`, `occurrences()`.
* `coordinator.py` – `GardenCoordinator(DataUpdateCoordinator[dict[str, PlantSnapshot]])`,
  `GardenConfigEntry = ConfigEntry[GardenCoordinator]` (use `entry.runtime_data`).
  * `coordinator.data: dict[subentry_id, PlantSnapshot]`
  * `PlantSnapshot(subentry_id, name, data, created, tasks: dict[task, TaskSnapshot])`,
    `.needs_attention`, `.next_task`
  * `TaskSnapshot(subentry_id, task, name, schedule, last_done, snoozed_until, due, days_until, status)`
    status ∈ `due | upcoming | scheduled | inactive`
  * `await coordinator.async_complete_task(subentry_id, task, when: date | None = None)`
  * `await coordinator.async_snooze_task(subentry_id, task, days)`
  * `coordinator.raw_task_state(subentry_id, task) -> dict` mutable store dict (key
    `notified_due` is for the notifier), `await coordinator.async_save()`
  * `coordinator.options` – options merged over `DEFAULT_OPTIONS`
  * `coordinator.plant_subentries()`
* `__init__.py` – sets up coordinator, `GardenNotifier`, platforms, services, reload listener.

## Entities

Every plant is a **device**: `DeviceInfo(identifiers={(DOMAIN, subentry_id)}, name=plant name,
model=species or preset label, suggested_area=location or None, entry_type=DeviceEntryType.SERVICE)`.
Plant entities are added with `async_add_entities(entities, config_subentry_id=subentry_id)`
(one call per plant subentry). Garden-wide entities belong to a device
`identifiers={(DOMAIN, entry.entry_id)}`, name "Garden", added without a subentry id.
All entities: `_attr_has_entity_name = True`, `translation_key`, CoordinatorEntity.

| Platform | Unique id | translation_key | Notes |
|---|---|---|---|
| sensor (per task) | `{subentry_id}_{task}_due` | `task_due_{task}` (custom: `task_due_custom` with placeholder `{name}`) | device_class DATE, state = due date; attrs: `task`, `status`, `days_until`, `last_done`, `snoozed_until`, `months`, `interval_days` |
| sensor (per plant) | `{subentry_id}_next_task` | `next_task` | state = display name of next task (enum-free string) ; attrs `task`, `due`, `days_until` |
| binary_sensor (per plant) | `{subentry_id}_needs_attention` | `needs_attention` | device_class PROBLEM, on when any task status `due`; attr `due_tasks` list |
| button (per task) | `{subentry_id}_{task}_done` | `mark_done_{task}` (custom: `mark_done_custom` w/ `{name}`) | press → `async_complete_task` |
| sensor (garden) | `{entry_id}_tasks_due` | `tasks_due` | count of tasks with status `due`; attr `tasks` list of `{plant, task, due}` |
| calendar (garden) | `{entry_id}_calendar` | `garden_calendar` | all-day events from `scheduler.occurrences()` for every task; summary `"{Task label}: {plant}"` |
| todo (garden) | `{entry_id}_todo` | `garden_tasks` | items = tasks with status `due` or `upcoming`; uid `"{subentry_id}:{task}"`; supports `UPDATE_TODO_ITEM`; setting status completed → `async_complete_task` |

Task display labels (English) used in non-translated places like calendar summaries and
notifications live in `const`-like dict `TASK_LABELS` in `plant_library.py`:
`{"prune": "Prune", "fertilize": "Fertilize", "water": "Water", "harvest": "Harvest",
"sow": "Sow / plant", "protect": "Winter protection", "custom": "Custom task"}`.
For custom tasks use the plant's `custom_task_name` instead.

## Services (`services.py`, registered in `async_setup`)

* `garden_assistant.complete_task` – target: entities (task due sensor or mark-done button
  of this integration); field `date` (optional date).
* `garden_assistant.snooze_task` – target: entities; field `days` (int 1–365, default 7).

Entity → (subentry_id, task) resolution: entity registry `unique_id` ends with `_due` or
`_done`; strip suffix, the task is the last `_`-separated part that is in `TASK_TYPES`,
subentry_id is the rest. Raise `ServiceValidationError` with translation keys for bad input.

## Notifications (`notifications.py`)

`GardenNotifier(hass, coordinator)` with `async def async_start()` and `@callback def async_stop()`.
* Every day at option `notify_time` (`"HH:MM:SS"`) it evaluates tasks with status `due`
  or `upcoming` (upcoming = within `lead_days`).
* For each task it **always fires** event `garden_assistant_task_due`
  (`{entry_id, subentry_id, plant, task, task_name, due, days_until, status}`), once per
  due date (bookkeeping `notified_due` in `raw_task_state`; with `repeat_daily` it fires
  every day until done).
* If option `notify_enabled`: one combined message per run, sent to each service in
  `notify_services` (strings like `notify.mobile_app_pixel` or `mobile_app_pixel`) via
  `hass.services.async_call("notify", name, {"title", "message", "data"})` and, if
  `notify_persistent`, a persistent notification (`persistent_notification.async_create`,
  notification_id `garden_assistant_due`).
* If `actionable_notifications` and a single task is in the message for a `mobile_app_*`
  service, add `data.actions` "Done" (`GARDEN_DONE|{subentry_id}|{task}`) and
  "Snooze 1 day"(`GARDEN_SNOOZE|...`). Listen to `mobile_app_notification_action` event and
  handle those actions. For multiple tasks, send one message per task when actionable is
  on (max 10 per run) so each has buttons.
* Errors of one notify service are logged, not raised.
* Re-schedules itself when options change (entry reload handles this automatically).

## Config flow (`config_flow.py`)

* User step: single instance, asks `hemisphere` (default derived from `hass.config.latitude`
  < 0 → south). Creates entry titled "Garden" with that in options.
* Options flow (`OptionsFlowWithReload` is not needed; reload listener exists): hemisphere,
  notify_enabled, notify_services (multi select of existing `notify` services, custom values
  allowed), notify_persistent, notify_time (TimeSelector), lead_days (0–30),
  repeat_daily, actionable_notifications.
* Subentry flow `PlantSubentryFlowHandler` for `plant`: `user` step (name, preset select from
  library sorted by label + "custom", species, location, notes) → `schedule` step prefilled
  from preset (per task: `{task}_months` multi-select 1–12 with month names, `{task}_interval`
  number 0–365 days; `custom_task_name` text). Also `reconfigure` step with the same two steps
  prefilled from the current data. Months are selectors with string values "1".."12";
  store ints.
