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
from homeassistant.helpers import device_registry as dr, entity_registry as er

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


# Entity ids the tests refer to, keyed by (domain, unique_id). Home Assistant's
# automatic entity id generation changes between releases (2026.9 started
# prefixing the area name), so tests pin these ids in the registry up front.
PINNED_ENTITY_IDS: dict[tuple[str, str], str] = {
    (
        "binary_sensor",
        f"{ROSE_SUBENTRY_ID}_needs_attention",
    ): "front_rose_needs_attention",
    (
        "binary_sensor",
        f"{TOMATO_SUBENTRY_ID}_needs_attention",
    ): "tomato_needs_attention",
    ("button", f"{ROSE_SUBENTRY_ID}_prune_done"): "front_rose_mark_done_prune",
    ("button", f"{ROSE_SUBENTRY_ID}_fertilize_done"): "front_rose_mark_done_fertilize",
    ("button", f"{ROSE_SUBENTRY_ID}_custom_done"): (
        "front_rose_mark_done_deadhead_spent_flowers"
    ),
    ("button", f"{TOMATO_SUBENTRY_ID}_water_done"): "tomato_mark_done_water",
    ("sensor", f"{ROSE_SUBENTRY_ID}_prune_due"): "front_rose_prune",
    ("sensor", f"{ROSE_SUBENTRY_ID}_fertilize_due"): "front_rose_fertilize",
    ("sensor", f"{ROSE_SUBENTRY_ID}_custom_due"): "front_rose_deadhead_spent_flowers",
    ("sensor", f"{ROSE_SUBENTRY_ID}_next_task"): "front_rose_next_task",
    ("sensor", f"{TOMATO_SUBENTRY_ID}_water_due"): "tomato_water",
    ("sensor", f"{TOMATO_SUBENTRY_ID}_next_task"): "tomato_next_task",
}


def _pin_entity_ids(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    registry = er.async_get(hass)
    for (domain, unique_id), object_id in PINNED_ENTITY_IDS.items():
        subentry_id = unique_id.split("_", 2)[0] + "_subentry"
        if subentry_id not in entry.subentries:
            continue
        registry.async_get_or_create(
            domain,
            DOMAIN,
            unique_id,
            suggested_object_id=object_id,
            config_entry=entry,
            config_subentry_id=subentry_id,
        )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """Add and set up an entry."""
    entry.add_to_hass(hass)
    _pin_entity_ids(hass, entry)
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


@pytest.fixture(autouse=True)
def fail_on_deprecation_warnings(
    caplog: pytest.LogCaptureFixture,
) -> Generator[None]:
    """Fail when Home Assistant reports deprecated API usage by this integration.

    Deprecated helpers keep working until they are removed, so without this
    check a removal in a newer Home Assistant release breaks installs silently.
    """
    yield
    deprecations = [
        record.getMessage()
        for record in caplog.get_records("call")
        if "deprecated" in record.getMessage() and DOMAIN in record.getMessage()
    ]
    assert not deprecations, deprecations


def get_device(hass: HomeAssistant, identifier: str) -> dr.DeviceEntry | None:
    """Return the Garden Assistant device with the given identifier.

    Home Assistant 2026.9 deprecated ``async_get_device(identifiers=...)`` in
    favour of the per config entry ``async_get_device_by_identifier``.
    """
    registry = dr.async_get(hass)
    if hasattr(registry, "async_get_device_by_identifier"):
        entries = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            if device := registry.async_get_device_by_identifier(
                (DOMAIN, identifier), entry.entry_id
            ):
                return device
        return None
    return registry.async_get_device(identifiers={(DOMAIN, identifier)})
