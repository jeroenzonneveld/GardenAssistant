"""Integration tests: setup, entities, services, storage and lifecycle."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)
import voluptuous as vol

from custom_components.garden_assistant.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import (
    ROSE_SUBENTRY_ID,
    TOMATO_SUBENTRY_ID,
    get_device,
    make_entry,
    setup_entry,
)

STORE_KEY = "garden_assistant.state.garden_entry"

ROSE = ROSE_SUBENTRY_ID
TOMATO = TOMATO_SUBENTRY_ID

# unique_id -> (platform, expected entity_id)
EXPECTED_ENTITIES = {
    f"{ROSE}_prune_due": ("sensor", "sensor.front_rose_prune"),
    f"{ROSE}_fertilize_due": ("sensor", "sensor.front_rose_fertilize"),
    f"{ROSE}_custom_due": ("sensor", "sensor.front_rose_deadhead_spent_flowers"),
    f"{ROSE}_next_task": ("sensor", "sensor.front_rose_next_task"),
    f"{ROSE}_needs_attention": (
        "binary_sensor",
        "binary_sensor.front_rose_needs_attention",
    ),
    f"{ROSE}_prune_done": ("button", "button.front_rose_mark_done_prune"),
    f"{ROSE}_fertilize_done": ("button", "button.front_rose_mark_done_fertilize"),
    f"{ROSE}_custom_done": (
        "button",
        "button.front_rose_mark_done_deadhead_spent_flowers",
    ),
    f"{TOMATO}_water_due": ("sensor", "sensor.tomato_water"),
    f"{TOMATO}_next_task": ("sensor", "sensor.tomato_next_task"),
    f"{TOMATO}_needs_attention": (
        "binary_sensor",
        "binary_sensor.tomato_needs_attention",
    ),
    f"{TOMATO}_water_done": ("button", "button.tomato_mark_done_water"),
    "garden_entry_tasks_due": ("sensor", "sensor.garden_tasks_due"),
    "garden_entry_calendar": ("calendar", "calendar.garden_calendar"),
    "garden_entry_todo": ("todo", "todo.garden_tasks"),
}


def state_of(hass: HomeAssistant, entity_id: str):
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


# ------------------------------------------------------------------- setup


async def test_setup_creates_expected_entities(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    assert init_integration.state is ConfigEntryState.LOADED
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, init_integration.entry_id)
    actual = {e.unique_id: (e.domain, e.entity_id) for e in entries}
    print("ENTITY IDS:", actual)
    assert actual == EXPECTED_ENTITIES


async def test_entities_attached_to_subentries_and_devices(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    registry = er.async_get(hass)

    prune = registry.async_get("sensor.front_rose_prune")
    assert prune.config_subentry_id == ROSE
    garden_sensor = registry.async_get("sensor.garden_tasks_due")
    assert garden_sensor.config_subentry_id is None

    rose_device = get_device(hass, ROSE)
    assert rose_device.name == "Front rose"
    assert rose_device.model == "Rosa 'Iceberg'"
    assert rose_device.entry_type is dr.DeviceEntryType.SERVICE
    tomato_device = get_device(hass, TOMATO)
    assert tomato_device.model == "custom"
    garden_device = get_device(hass, init_integration.entry_id)
    assert garden_device.name == "Garden"


async def test_task_sensor_states_and_attributes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    prune = state_of(hass, "sensor.front_rose_prune")
    assert prune.state == "2026-03-01"
    assert prune.attributes["device_class"] == "date"
    assert prune.attributes["task"] == "prune"
    assert prune.attributes["status"] == "due"
    assert prune.attributes["days_until"] == -9
    assert prune.attributes["last_done"] is None
    assert prune.attributes["snoozed_until"] is None
    assert prune.attributes["months"] == [3]
    assert prune.attributes["interval_days"] == 0

    fertilize = state_of(hass, "sensor.front_rose_fertilize")
    assert fertilize.state == "2026-04-01"
    assert fertilize.attributes["status"] == "scheduled"
    assert fertilize.attributes["days_until"] == 22
    assert fertilize.attributes["months"] == [4, 6]

    custom = state_of(hass, "sensor.front_rose_deadhead_spent_flowers")
    assert custom.state == "2026-06-01"
    assert custom.attributes["task"] == "custom"
    assert custom.attributes["interval_days"] == 14

    water = state_of(hass, "sensor.tomato_water")
    assert water.state == "2026-03-12"
    assert water.attributes["status"] == "scheduled"
    assert water.attributes["days_until"] == 2
    assert water.attributes["interval_days"] == 7


async def test_next_task_and_garden_sensors(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    rose_next = state_of(hass, "sensor.front_rose_next_task")
    assert rose_next.state == "Prune"
    assert rose_next.attributes["task"] == "prune"
    assert rose_next.attributes["due"] == "2026-03-01"
    assert rose_next.attributes["days_until"] == -9

    tomato_next = state_of(hass, "sensor.tomato_next_task")
    assert tomato_next.state == "Water"
    assert tomato_next.attributes["due"] == "2026-03-12"

    due = state_of(hass, "sensor.garden_tasks_due")
    assert due.state == "1"
    assert due.attributes["unit_of_measurement"] == "tasks"
    assert due.attributes["tasks"] == [
        {"plant": "Front rose", "task": "Prune", "due": "2026-03-01"}
    ]


async def test_binary_sensor_on_when_due(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    rose = state_of(hass, "binary_sensor.front_rose_needs_attention")
    assert rose.state == "on"
    assert rose.attributes["device_class"] == "problem"
    assert rose.attributes["due_tasks"] == ["Prune"]

    tomato = state_of(hass, "binary_sensor.tomato_needs_attention")
    assert tomato.state == "off"
    assert tomato.attributes["due_tasks"] == []


async def test_custom_task_names_use_placeholder(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    assert (
        state_of(hass, "sensor.front_rose_deadhead_spent_flowers").attributes[
            "friendly_name"
        ]
        == "Front rose Deadhead spent flowers"
    )
    assert (
        state_of(hass, "button.front_rose_mark_done_deadhead_spent_flowers").attributes[
            "friendly_name"
        ]
        == "Front rose Mark done: Deadhead spent flowers"
    )


async def test_setup_without_plants(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, make_entry(plants=[]))
    assert entry.state is ConfigEntryState.LOADED
    assert state_of(hass, "sensor.garden_tasks_due").state == "0"
    assert state_of(hass, "calendar.garden_calendar").state == "off"


# ------------------------------------------------------------------ button


async def press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()


async def test_button_press_marks_done_and_persists(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    events = async_capture_events(hass, "garden_assistant_task_completed")
    await press(hass, "button.front_rose_mark_done_prune")

    prune = state_of(hass, "sensor.front_rose_prune")
    # Done in the March season: next season starts in March 2027.
    assert prune.state == "2027-03-01"
    assert prune.attributes["last_done"] == "2026-03-10"
    assert prune.attributes["status"] == "scheduled"
    assert state_of(hass, "binary_sensor.front_rose_needs_attention").state == "off"
    assert state_of(hass, "sensor.garden_tasks_due").state == "0"

    assert len(events) == 1
    assert events[0].data["subentry_id"] == ROSE
    assert events[0].data["task"] == "prune"
    assert events[0].data["plant"] == "Front rose"
    assert events[0].data["date"] == "2026-03-10"

    stored = hass_storage[STORE_KEY]["data"]
    assert stored["plants"][ROSE]["prune"]["last_done"] == "2026-03-10"

    # State survives an entry reload.
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    prune = state_of(hass, "sensor.front_rose_prune")
    assert prune.attributes["last_done"] == "2026-03-10"
    assert prune.state == "2027-03-01"


async def test_state_loaded_from_existing_storage(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORE_KEY,
        "data": {
            "plants": {
                ROSE: {"prune": {"last_done": "2026-03-05", "snoozed_until": None}},
                "removed_plant": {"water": {"last_done": "2026-01-01"}},
            }
        },
    }
    await setup_entry(hass, make_entry())
    prune = state_of(hass, "sensor.front_rose_prune")
    assert prune.attributes["last_done"] == "2026-03-05"
    assert prune.state == "2027-03-01"
    assert state_of(hass, "binary_sensor.front_rose_needs_attention").state == "off"


async def test_corrupt_storage_is_ignored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORE_KEY,
        "data": {"plants": {ROSE: {"prune": {"last_done": "not-a-date"}}}},
    }
    entry = await setup_entry(hass, make_entry())
    assert entry.state is ConfigEntryState.LOADED
    assert state_of(hass, "sensor.front_rose_prune").state == "2026-03-01"


# ------------------------------------------------------------- todo / calendar


async def get_todo_items(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    response = await hass.services.async_call(
        "todo",
        "get_items",
        {"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    return response[entity_id]["items"]


async def test_todo_items(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    # Default lead_days 0: only due tasks are listed.
    items = await get_todo_items(hass, "todo.garden_tasks")
    assert items == [
        {
            "summary": "Prune: Front rose",
            "uid": f"{ROSE}:prune",
            "status": "needs_action",
            "due": "2026-03-01",
            "description": "Due: 2026-03-01\nLocation: Front yard",
        }
    ]
    assert state_of(hass, "todo.garden_tasks").state == "1"


async def test_todo_includes_upcoming_with_lead_days(hass: HomeAssistant) -> None:
    await setup_entry(hass, make_entry(options={"lead_days": 3}))
    items = await get_todo_items(hass, "todo.garden_tasks")
    assert [i["summary"] for i in items] == ["Prune: Front rose", "Water: Tomato"]
    assert items[1]["due"] == "2026-03-12"
    assert items[1]["description"] == "Due: 2026-03-12"


async def test_todo_complete_item(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    await hass.services.async_call(
        "todo",
        "update_item",
        {
            "entity_id": "todo.garden_tasks",
            "item": f"{ROSE}:prune",
            "status": "completed",
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert await get_todo_items(hass, "todo.garden_tasks") == []
    assert (
        state_of(hass, "sensor.front_rose_prune").attributes["last_done"]
        == "2026-03-10"
    )
    assert (
        hass_storage[STORE_KEY]["data"]["plants"][ROSE]["prune"]["last_done"]
        == "2026-03-10"
    )


async def test_todo_rejects_invalid_updates(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    # Rename only (status stays needs_action).
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "todo",
            "update_item",
            {"entity_id": "todo.garden_tasks", "item": f"{ROSE}:prune", "rename": "x"},
            blocking=True,
        )


async def test_calendar_events(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.garden_calendar",
            "start_date_time": "2026-03-01 00:00:00",
            "end_date_time": "2026-04-15 00:00:00",
        },
        blocking=True,
        return_response=True,
    )
    events = response["calendar.garden_calendar"]["events"]
    assert [(e["start"], e["summary"]) for e in events] == [
        ("2026-03-01", "Prune: Front rose"),
        ("2026-03-12", "Water: Tomato"),
        ("2026-03-19", "Water: Tomato"),
        ("2026-03-26", "Water: Tomato"),
        ("2026-04-01", "Fertilize: Front rose"),
        ("2026-04-02", "Water: Tomato"),
        ("2026-04-09", "Water: Tomato"),
    ]
    assert events[0]["end"] == "2026-03-02"
    assert events[0]["location"] == "Front yard"
    assert events[0]["description"] == "Front rose (Front yard)"


async def test_calendar_custom_task_and_state(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.garden_calendar",
            "start_date_time": "2026-06-01 00:00:00",
            "end_date_time": "2026-06-20 00:00:00",
        },
        blocking=True,
        return_response=True,
    )
    summaries = [
        e["summary"]
        for e in response["calendar.garden_calendar"]["events"]
        if "Deadhead" in e["summary"]
    ]
    assert summaries == [
        "Deadhead spent flowers: Front rose",
        "Deadhead spent flowers: Front rose",
    ]
    # The calendar entity reports the next event starting today or later
    # (the overdue prune task of 2026-03-01 is in the past).
    calendar = state_of(hass, "calendar.garden_calendar")
    assert calendar.attributes["message"] == "Water: Tomato"
    assert calendar.state == "off"


# ------------------------------------------------------------------ services


async def test_complete_task_service_with_date(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "complete_task",
        {"entity_id": "sensor.front_rose_prune", "date": "2026-03-05"},
        blocking=True,
    )
    prune = state_of(hass, "sensor.front_rose_prune")
    assert prune.attributes["last_done"] == "2026-03-05"
    assert prune.state == "2027-03-01"


async def test_complete_task_service_multiple_and_button_targets(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "complete_task",
        {
            "entity_id": [
                "sensor.front_rose_prune",
                "button.front_rose_mark_done_prune",  # same task, deduplicated
                "button.tomato_mark_done_water",
            ]
        },
        blocking=True,
    )
    assert (
        state_of(hass, "sensor.front_rose_prune").attributes["last_done"]
        == "2026-03-10"
    )
    water = state_of(hass, "sensor.tomato_water")
    assert water.attributes["last_done"] == "2026-03-10"
    assert water.state == "2026-03-17"


async def test_complete_task_service_via_device_target(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    device = get_device(hass, TOMATO)
    await hass.services.async_call(
        DOMAIN, "complete_task", {"device_id": device.id}, blocking=True
    )
    # The device also has next-task and needs-attention entities; those are
    # skipped silently when reached through a device target.
    assert state_of(hass, "sensor.tomato_water").attributes["last_done"] == "2026-03-10"


async def test_snooze_task_service(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "snooze_task",
        {"entity_id": "sensor.front_rose_prune", "days": 5},
        blocking=True,
    )
    prune = state_of(hass, "sensor.front_rose_prune")
    assert prune.attributes["snoozed_until"] == "2026-03-15"
    assert prune.state == "2026-03-15"
    assert prune.attributes["status"] == "scheduled"
    assert state_of(hass, "binary_sensor.front_rose_needs_attention").state == "off"


async def test_snooze_task_default_days(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "snooze_task",
        {"entity_id": "button.front_rose_mark_done_prune"},
        blocking=True,
    )
    assert state_of(hass, "sensor.front_rose_prune").state == "2026-03-17"


async def test_complete_clears_snooze(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "snooze_task",
        {"entity_id": "sensor.front_rose_prune", "days": 5},
        blocking=True,
    )
    await press(hass, "button.front_rose_mark_done_prune")
    assert state_of(hass, "sensor.front_rose_prune").attributes["snoozed_until"] is None


@pytest.mark.parametrize("days", [0, 366, "abc"])
async def test_snooze_days_validation(
    hass: HomeAssistant, init_integration: MockConfigEntry, days: Any
) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "snooze_task",
            {"entity_id": "sensor.front_rose_prune", "days": days},
            blocking=True,
        )


async def test_complete_task_invalid_date(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "complete_task",
            {"entity_id": "sensor.front_rose_prune", "date": "yesterday-ish"},
            blocking=True,
        )


async def test_service_without_target(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await hass.services.async_call(DOMAIN, "complete_task", {}, blocking=True)


async def test_service_rejects_foreign_entity(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", "other", "abc", suggested_object_id="foreign"
    )
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "complete_task", {"entity_id": "sensor.foreign"}, blocking=True
        )
    assert err.value.translation_key == "not_garden_entity"
    assert err.value.translation_placeholders == {"entity_id": "sensor.foreign"}

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "complete_task",
            {"entity_id": "sensor.not_registered"},
            blocking=True,
        )
    assert err.value.translation_key == "not_garden_entity"


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.front_rose_next_task",
        "sensor.garden_tasks_due",
        "binary_sensor.front_rose_needs_attention",
        "todo.garden_tasks",
    ],
)
async def test_service_rejects_non_task_entity(
    hass: HomeAssistant, init_integration: MockConfigEntry, entity_id: str
) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "snooze_task", {"entity_id": entity_id, "days": 2}, blocking=True
        )
    assert err.value.translation_key == "not_task_entity"


async def test_service_with_unloaded_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "complete_task",
            {"entity_id": "sensor.front_rose_prune"},
            blocking=True,
        )
    assert err.value.translation_key == "entry_not_loaded"


async def test_coordinator_rejects_unknown_task(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    coordinator = init_integration.runtime_data
    with pytest.raises(KeyError):
        await coordinator.async_complete_task("nope", "prune")
    with pytest.raises(KeyError):
        await coordinator.async_snooze_task(ROSE, "not_a_task", 1)


async def test_todo_complete_for_removed_task_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "todo",
            "update_item",
            {
                "entity_id": "todo.garden_tasks",
                "item": f"{ROSE}:water",
                "status": "completed",
            },
            blocking=True,
        )


# ---------------------------------------------------------------- lifecycle


async def test_midnight_refresh_updates_due_state(
    hass: HomeAssistant, init_integration: MockConfigEntry, freezer
) -> None:
    assert state_of(hass, "sensor.tomato_water").attributes["status"] == "scheduled"
    # The daily refresh runs at 00:00:05 local time.
    freezer.move_to("2026-03-13 00:00:05+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    water = state_of(hass, "sensor.tomato_water")
    assert water.attributes["status"] == "due"
    assert state_of(hass, "binary_sensor.tomato_needs_attention").state == "on"


async def test_removing_subentry_removes_entities_and_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    await press(hass, "button.front_rose_mark_done_prune")
    assert ROSE in hass_storage[STORE_KEY]["data"]["plants"]

    hass.config_entries.async_remove_subentry(init_integration, ROSE)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    remaining = {
        e.unique_id
        for e in er.async_entries_for_config_entry(registry, init_integration.entry_id)
    }
    assert remaining == {
        f"{TOMATO}_water_due",
        f"{TOMATO}_next_task",
        f"{TOMATO}_needs_attention",
        f"{TOMATO}_water_done",
        "garden_entry_tasks_due",
        "garden_entry_calendar",
        "garden_entry_todo",
    }
    assert hass.states.get("sensor.front_rose_prune") is None
    assert hass.states.get("binary_sensor.front_rose_needs_attention") is None
    assert get_device(hass, ROSE) is None
    assert get_device(hass, TOMATO) is not None
    assert init_integration.state is ConfigEntryState.LOADED
    assert state_of(hass, "sensor.garden_tasks_due").state == "0"

    # Progress of the removed plant does not linger in storage.
    await press(hass, "button.tomato_mark_done_water")
    assert ROSE not in hass_storage[STORE_KEY]["data"]["plants"]


async def test_unload_and_reload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert state_of(hass, "sensor.front_rose_prune").state == "unavailable"

    assert await hass.config_entries.async_setup(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
    assert state_of(hass, "sensor.front_rose_prune").state == "2026-03-01"


async def test_remove_entry_deletes_store(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    await press(hass, "button.front_rose_mark_done_prune")
    assert STORE_KEY in hass_storage
    assert await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    assert STORE_KEY not in hass_storage
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_button_press_error_becomes_ha_error(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    coordinator = init_integration.runtime_data

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise KeyError("Unknown plant")

    coordinator.async_complete_task = boom
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.front_rose_mark_done_prune"},
            blocking=True,
        )


async def test_device_target_without_task_entities(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    garden = get_device(hass, init_integration.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "complete_task", {"device_id": garden.id}, blocking=True
        )
    assert err.value.translation_key == "no_entities"
