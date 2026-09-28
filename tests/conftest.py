"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_assistant.const import (
    DEFAULT_OPTIONS,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

TODAY = "2026-03-10 12:00:00+00:00"

ROSE_SUBENTRY_ID = "rose_subentry"
TOMATO_SUBENTRY_ID = "tomato_subentry"

ROSE_DATA: dict[str, Any] = {
    "name": "Front rose",
    "preset": "rose",
    "species": "Rosa 'Iceberg'",
    "location": "Front yard",
    "notes": "",
    "created": "2026-01-01",
    "tasks": {
        # Season started 2026-03-01 -> due (9 days overdue) on the frozen day.
        "prune": {"months": [3], "interval_days": 0},
        # Next season starts 2026-04-01 -> scheduled.
        "fertilize": {"months": [4, 6], "interval_days": 0},
        # Every 14 days in Jun-Sep, first on 2026-06-01 -> scheduled.
        "custom": {
            "months": [6, 7, 8, 9],
            "interval_days": 14,
            "custom_task_name": "Deadhead spent flowers",
        },
    },
}

TOMATO_DATA: dict[str, Any] = {
    "name": "Tomato",
    "preset": "custom",
    "species": "",
    "location": "",
    "notes": "",
    "created": "2026-03-12",
    "tasks": {
        # Interval only, never done -> due on the created date (in 2 days).
        "water": {"months": [], "interval_days": 7},
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations in all tests."""
    return


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> FrozenDateTimeFactory:
    """Pin time so due dates are deterministic (local date is 2026-03-10)."""
    freezer.move_to(TODAY)
    return freezer


def make_entry(
    options: dict[str, Any] | None = None,
    plants: list[tuple[str, dict[str, Any]]] | None = None,
) -> MockConfigEntry:
    """Create a garden config entry with plant subentries."""
    if plants is None:
        plants = [(ROSE_SUBENTRY_ID, ROSE_DATA), (TOMATO_SUBENTRY_ID, TOMATO_DATA)]
    return MockConfigEntry(
        domain=DOMAIN,
        title="Garden",
        data={},
        options={**DEFAULT_OPTIONS, **(options or {})},
        entry_id="garden_entry",
        subentries_data=[
            ConfigSubentryData(
                data=data,
                subentry_id=sid,
                subentry_type=SUBENTRY_TYPE_PLANT,
                title=data["name"],
                unique_id=None,
            )
            for sid, data in plants
        ],
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """Add and set up an entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return an (unloaded) garden entry with two plants."""
    return make_entry()


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the garden with two plants."""
    return await setup_entry(hass, mock_config_entry)


@pytest.fixture
def entity_id_for(hass: HomeAssistant):
    """Return a helper resolving a unique_id to an entity_id."""

    def _lookup(domain: str, unique_id: str) -> str:
        entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
        assert entity_id is not None, f"no {domain} entity with unique_id {unique_id}"
        return entity_id

    return _lookup


@pytest.fixture
def no_reload() -> Generator[None]:
    """Skip the real entry reload (for flow tests that only check results)."""
    with patch("homeassistant.config_entries.ConfigEntries.async_reload"):
        yield
