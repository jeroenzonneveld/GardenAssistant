# Garden Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validate](https://github.com/jeroenzonneveld/GardenAssistant/actions/workflows/validate.yml/badge.svg)](https://github.com/jeroenzonneveld/GardenAssistant/actions/workflows/validate.yml)
[![Tests](https://github.com/jeroenzonneveld/GardenAssistant/actions/workflows/tests.yml/badge.svg)](https://github.com/jeroenzonneveld/GardenAssistant/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/github/license/jeroenzonneveld/GardenAssistant)](LICENSE)

Garden Assistant is a Home Assistant integration that keeps track of the recurring work
in your garden: when to prune the roses, feed the tomatoes, sow the beans or protect the
fig tree from frost. Add your plants, pick a preset (or define your own schedule) and the
integration tells you what is due, through entities, a calendar, a to-do list and
optional notifications.

Everything is calculated locally; there is no cloud service and no external dependency.

## Features

- **Plants as sub-entries**: every plant is a sub-entry of the single "Garden" entry and
  shows up as its own device. Add, reconfigure or delete plants from the integration page.
- **Presets**: start from a built-in plant preset with sensible northern-hemisphere
  schedules (automatically shifted by six months for the southern hemisphere), or choose
  `custom` and fill in everything yourself.
- **Task types**: prune, fertilize, water, harvest, sow / plant, winter protection and a
  custom task with a name of your choice.
- **Flexible schedules**: per task, use active months, a repeat interval, or both.
  See [How scheduling works](#how-scheduling-works).
- **Entities per plant**: a due-date sensor and a "mark done" button for each task, a
  "next task" sensor and a "needs attention" binary sensor.
- **Garden-wide entities**: a "tasks due" counter sensor, a garden calendar and a to-do
  list.
- **Notifications** (optional): a daily digest to any `notify` service and/or a persistent
  notification, with a configurable lead time, plus actionable mobile app notifications
  (Done / Snooze).
- **Event for automations**: `garden_assistant_task_due` is fired for every task that
  becomes due, whether or not notifications are enabled.
- **Services**: `garden_assistant.complete_task` and `garden_assistant.snooze_task`.

## Installation

Requires Home Assistant 2025.4.0 or newer.

### HACS (custom repository)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jeroenzonneveld&repository=GardenAssistant&category=integration)

Or manually:

1. In Home Assistant open **HACS**.
2. Open the three-dot menu (top right) and choose **Custom repositories**.
3. Enter `https://github.com/jeroenzonneveld/GardenAssistant`, select the category
   **Integration** and click **Add**.
4. Search for **Garden Assistant** in HACS, open it and click **Download**.
5. Restart Home Assistant.

### Manual

1. Download the latest release from the
   [releases page](https://github.com/jeroenzonneveld/GardenAssistant/releases).
2. Copy the folder `custom_components/garden_assistant` into the `custom_components`
   folder of your Home Assistant configuration directory.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings > Devices & services > Add integration** and search for
   **Garden Assistant**.
2. Choose your **hemisphere**. It defaults to the location configured in Home Assistant.
   Presets use it to shift their months, so a rose that is pruned in February in the
   north is pruned in August in the south.
3. On the integration page click **Add plant**:
   - Enter a name, and optionally species, location and notes. The location is used as the
     suggested area of the plant's device.
   - Pick a **preset** or `custom`.
   - On the next screen adjust the schedule per task type: the months in which the task is
     active and/or an interval in days. Leave both empty to disable a task. For a custom
     task also enter its name.
4. Use the three-dot menu of a plant to **reconfigure** it later (for instance when you
   want to shift a schedule) or to delete it.

Global settings (hemisphere and notifications) are under **Configure** on the integration.

### Plant presets

Presets are a starting point for a temperate (north-west European) climate; adjust them to
your local climate and variety. Available presets:

Apple tree, Basil, Blueberry, Boxwood, Buddleja (butterfly bush), Cherry tree, Clematis,
Courgette, Dahlia, Fig, Fuchsia, Grapevine, Hedge (beech / privet), Hydrangea (bigleaf),
Lavender, Lawn, Lettuce, Mint, Olive tree (in pot), Ornamental grasses, Pear tree, Plum tree,
Potato, Raspberry, Rhododendron, Rose, Rosemary, Runner bean, Strawberry, Thyme, Tomato,
Tulip bulbs and Wisteria.

Missing a plant? Open an issue or a pull request against
`custom_components/garden_assistant/plant_library.py`.

### Entities

For every plant, grouped in one device:

| Entity | Description |
|---|---|
| `sensor` per task ("Prune", ...) | Date the task is due next. Attributes: `task`, `status` (`due`, `upcoming`, `scheduled`, `inactive`), `days_until`, `last_done`, `snoozed_until`, `months`, `interval_days`. |
| `button` per task ("Mark done: Prune", ...) | Press when you did the job. |
| `sensor` "Next task" | Name of the next task with `task`, `due` and `days_until` attributes. |
| `binary_sensor` "Needs attention" | On while at least one task is due. Attribute `due_tasks`. |

For the garden as a whole:

| Entity | Description |
|---|---|
| `sensor` "Tasks due" | Number of tasks that are due right now, with a `tasks` attribute listing them. |
| `calendar` "Calendar" | All-day events for every scheduled occurrence, for example "Prune: Front rose". |
| `todo` "Tasks" | Due and upcoming tasks. Checking an item off marks the task as done. |

## How scheduling works

Each task has two optional settings: **months** and **interval (days)**. Which of them you
fill in selects one of three modes. Months are always the months of your own hemisphere.

### 1. Months only: once per season

The task is due **once per season**. A season is an unbroken run of active months and can
wrap around the new year (November to January is one season).

- The task becomes due on the **first day of the season**.
- Marking it done anywhere within the season finishes it until the next season starts.
- If you miss the whole season, it does not stay overdue forever; the next due date is the
  start of the next season.
- Selecting all twelve months means "once per calendar year".

Example: pruning in February and March. The task is due from 1 February; once you mark it
done on 10 February, the next due date is 1 February next year.

### 2. Interval only: every N days

The task repeats **N days after it was last done**. When it has never been done, it is due
straight away (from the day the plant was added). A task that is overdue stays due until you
mark it done, and the next due date is counted from the day you actually did it.

Example: water every 3 days. Done on Monday, next due on Thursday.

### 3. Months and interval: every N days inside the season

The task repeats every N days, but **only in the active months**. When the next due date
would fall outside the active months, it is moved to the first day of the next season.

Example: fertilize every 28 days from April to July. Done on 20 July, the next due date
would be 17 August, which is outside the season, so the task is next due on 1 April the year
after.

### Snoozing

Snoozing a task (service `garden_assistant.snooze_task` or the mobile notification action)
pushes its due date to at least the snooze date. It never makes a task due earlier.

### Status

| Status | Meaning |
|---|---|
| `due` | The due date is today or in the past. |
| `upcoming` | Due within the configured lead days. |
| `scheduled` | Has a due date further in the future. |

## Notifications

Under **Configure** on the integration:

| Option | Description |
|---|---|
| Enable notifications | Send notifications for due and upcoming tasks. |
| Notify services | One or more `notify` services, such as `notify.mobile_app_pixel`. |
| Persistent notification | Also create a persistent notification in the Home Assistant UI. |
| Notification time | Time of day the check runs and notifications are sent. |
| Lead days | Also include tasks that are due within this many days (0 to 30). |
| Repeat daily | Keep notifying every day until the task is done instead of only once. |
| Actionable notifications | For mobile app services, add **Done** and **Snooze 1 day** buttons. |

With actionable notifications enabled, every task gets its own notification (up to 10 per
run) so each one has its own buttons. Errors from one notify service are logged and do not
stop the others.

The event `garden_assistant_task_due` is fired regardless of the notification settings, so
you can build your own notifications, for example on a speaker or a dashboard.

## Events and services

### Event `garden_assistant_task_due`

Fired once per due date (every day when "Repeat daily" is on) for each due or upcoming task.

```yaml
entry_id: 01J...
subentry_id: 01J...
plant: Front rose
task: prune
task_name: Prune
due: "2027-02-01"
days_until: 0
status: due
```

### Service `garden_assistant.complete_task`

Marks a task as done. Target a task due sensor or a "mark done" button of this integration.

| Field | Description |
|---|---|
| `date` | Optional. The date it was done (defaults to today). |

### Service `garden_assistant.snooze_task`

| Field | Description |
|---|---|
| `days` | Days to postpone (1 to 365, default 7). |

## Example automation

Announce due tasks on a speaker and mark them as done from a physical button:

```yaml
automation:
  - alias: "Garden: announce due task"
    triggers:
      - trigger: event
        event_type: garden_assistant_task_due
        event_data:
          status: due
    actions:
      - action: tts.speak
        target:
          entity_id: tts.home_assistant_cloud
        data:
          media_player_entity_id: media_player.kitchen
          message: >-
            Garden reminder: {{ trigger.event.data.task_name }}
            for {{ trigger.event.data.plant }}.

  - alias: "Garden: front rose pruned"
    triggers:
      - trigger: state
        entity_id: input_button.rose_pruned
    actions:
      - action: garden_assistant.complete_task
        target:
          entity_id: sensor.front_rose_prune
        data:
          date: "{{ now().date() }}"
```

Entity ids follow the plant name and task: `sensor.<plant>_<task>` (due date),
`button.<plant>_mark_done_<task>`, `sensor.<plant>_next_task`,
`binary_sensor.<plant>_needs_attention`, and for the garden `sensor.garden_tasks_due`,
`calendar.garden_calendar` and `todo.garden_tasks`. Custom tasks use their own name, and
Dutch installations get Dutch names, and since Home Assistant 2026.9 the area (the plant's location) is put in front, e.g. `sensor.front_yard_front_rose_prune`. The exact ids depend on your plant and task names; check them under
**Settings > Devices & services > Garden Assistant**.

## Lovelace example

```yaml
type: vertical-stack
cards:
  - type: todo-list
    entity: todo.garden_tasks
    title: Garden tasks
  - type: calendar
    entities:
      - calendar.garden_calendar
    initial_view: listWeek
  - type: entities
    title: Front rose
    entities:
      - binary_sensor.front_rose_needs_attention
      - sensor.front_rose_next_task
      - sensor.front_rose_prune
      - button.front_rose_mark_done_prune
```

Adjust the entity ids to match your installation.

## FAQ

**Can I have more than one garden?**
No. There is a single "Garden" entry; use the location field of each plant to tell areas
apart.

**A task I completed shows up again immediately.**
In months-only mode a task is done for the whole season once marked done. If it shows up
again, check that the `last_done` attribute changed and that the months are correct for
your hemisphere.

**I changed the hemisphere but my plants did not change.**
The hemisphere shifts presets while you add or reconfigure a plant. Existing plants keep
their stored months; reconfigure them to pick up the shifted values.

**Where is my progress stored?**
In Home Assistant's `.storage` directory, next to the entry, not in the plant configuration.
It is included in your regular Home Assistant backups.

**A task has no entities.**
Tasks without months and without an interval are disabled and get no entities. Reconfigure
the plant to add a schedule.

**How do I get notified on my phone?**
Enable notifications, add your `notify.mobile_app_<device>` service and turn on
actionable notifications for Done and Snooze buttons.

## Contributing

Issues and pull requests are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check . && pytest
```

## License

[MIT](LICENSE) (c) 2026 Jeroen Zonneveld
