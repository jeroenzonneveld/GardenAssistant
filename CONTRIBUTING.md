# Contributing

Thanks for helping out! Bug reports, plant presets and pull requests are welcome.

## Development setup

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```

The scheduling logic in `custom_components/garden_assistant/scheduler.py` is pure Python
and must stay free of Home Assistant imports so it can be unit tested in isolation.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for an overview of the integration.

## Pull requests

- Keep changes focused and add or update tests.
- Run `ruff format .` before committing.
- Use conventional commit messages (`feat:`, `fix:`, `docs:`, ...).
- Adding a plant preset: extend `plant_library.py` with northern hemisphere months;
  the config flow shifts them for the southern hemisphere.
- Do not add external requirements to `manifest.json` unless there is no alternative.

## Releasing

The `version` in `manifest.json` must equal the release tag (without a leading `v`);
the release workflow fails otherwise.
