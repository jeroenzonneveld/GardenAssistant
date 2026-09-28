# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

Releasing: bump `version` in `custom_components/garden_assistant/manifest.json`, add a
section for it below and merge to `main`. The release workflow then creates the tag and
the GitHub release.

## [0.1.0] - 2026-09-28

First public release of Garden Assistant: manage the plants in your garden and never
miss pruning, feeding or harvest time again.

### Added

- **Plants as sub-entries.** Add, reconfigure or delete plants from the integration page;
  each plant becomes its own device.
- **33 built-in presets** (rose, hydrangea, lavender, fruit trees, vegetables, herbs,
  lawn and more), shifted automatically for the southern hemisphere.
- **Task types:** prune, fertilize, water, harvest, sow / plant, winter protection and a
  custom task with your own name.
- **Flexible schedules:** once per season, every N days, or every N days within the
  active months, with snooze support.
- **Entities per plant:** due-date sensors, "mark done" buttons, a next-task sensor and a
  needs-attention binary sensor.
- **Garden-wide entities:** a tasks-due sensor, a calendar and a to-do list.
- **Optional proactive alerts:** a daily digest to any `notify` service and/or a
  persistent notification, lead days, repeat daily, and actionable mobile notifications
  with Done / Snooze buttons.
- **For automations:** the event `garden_assistant_task_due` and the services
  `garden_assistant.complete_task` and `garden_assistant.snooze_task`.
- English and Dutch translations.

Requires Home Assistant 2025.4.0 or newer. Install through HACS as a custom repository:
`https://github.com/jeroenzonneveld/GardenAssistant` (category *Integration*).
