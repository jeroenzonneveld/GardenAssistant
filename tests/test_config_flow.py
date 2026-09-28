"""Tests for the Garden Assistant config, options and subentry flows."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.garden_assistant.const import DEFAULT_OPTIONS, DOMAIN
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ROSE_DATA, ROSE_SUBENTRY_ID, make_entry, setup_entry


def suggested(result: dict[str, Any]) -> dict[str, Any]:
    """Return the suggested values of a form's schema."""
    return {
        str(marker): marker.description["suggested_value"]
        for marker in result["data_schema"].schema
        if marker.description and "suggested_value" in marker.description
    }


def schema_default(result: dict[str, Any], key: str) -> Any:
    """Return the default of a required schema key."""
    for marker in result["data_schema"].schema:
        if str(marker) == key:
            return marker.default()
    raise AssertionError(f"{key} not in schema")


# ----------------------------------------------------------------- user step


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # Default test location is in the northern hemisphere.
    assert hass.config.latitude > 0
    assert schema_default(result, "hemisphere") == "north"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"hemisphere": "north"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garden"
    assert result["options"] == {**DEFAULT_OPTIONS, "hemisphere": "north"}
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED


async def test_user_step_defaults_to_south_below_equator(hass: HomeAssistant) -> None:
    hass.config.latitude = -33.9
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert schema_default(result, "hemisphere") == "south"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"hemisphere": "south"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["hemisphere"] == "south"


async def test_single_instance_abort(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


# ------------------------------------------------------------------- options


async def test_options_flow_saves_all_options(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    async_mock_service(hass, "notify", "mobile_app_pixel")

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # Current options are suggested.
    assert suggested(result)["hemisphere"] == "north"
    # Existing notify services are offered as options.
    selector = next(
        m for m in result["data_schema"].schema if str(m) == "notify_services"
    )
    offered = [
        o["value"] for o in result["data_schema"].schema[selector].config["options"]
    ]
    assert "notify.mobile_app_pixel" in offered

    new_options = {
        "hemisphere": "south",
        "notify_enabled": True,
        "notify_services": ["notify.mobile_app_pixel", "notify.custom_typed"],
        "notify_persistent": False,
        "notify_time": "07:30:00",
        "lead_days": 3.0,
        "repeat_daily": True,
        "actionable_notifications": False,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], new_options
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert init_integration.options == {**new_options, "lead_days": 3}
    assert isinstance(init_integration.options["lead_days"], int)
    # The update listener reloads the entry.
    assert init_integration.state is ConfigEntryState.LOADED


# ------------------------------------------------------------- plant subentry


async def start_plant_flow(
    hass: HomeAssistant, entry: MockConfigEntry, source: str = "user", **context: Any
) -> dict[str, Any]:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "plant"), context={"source": source, **context}
    )


async def test_add_plant_with_preset_prefills_schedule(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await start_plant_flow(hass, init_integration)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "  Back rose ", "preset": "rose", "location": "Back yard"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "schedule"
    values = suggested(result)
    assert values["prune_months"] == ["3"]
    assert values["fertilize_months"] == ["4", "6"]
    assert values["protect_months"] == ["11"]
    assert values["custom_months"] == ["6", "7", "8", "9"]
    assert values["custom_interval"] == 14
    assert values["custom_task_name"] == "Deadhead spent flowers"
    assert values["water_months"] == []
    assert values["water_interval"] == 0

    # Submit the prefilled values unchanged.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], values
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Back rose"
    await hass.async_block_till_done()

    subentry = next(
        s for s in init_integration.subentries.values() if s.title == "Back rose"
    )
    assert subentry.subentry_type == "plant"
    assert subentry.data["name"] == "Back rose"
    assert subentry.data["preset"] == "rose"
    assert subentry.data["location"] == "Back yard"
    assert subentry.data["created"] == "2026-03-10"
    assert subentry.data["tasks"] == {
        "prune": {"months": [3], "interval_days": 0},
        "fertilize": {"months": [4, 6], "interval_days": 0},
        "protect": {"months": [11], "interval_days": 0},
        "custom": {
            "months": [6, 7, 8, 9],
            "interval_days": 14,
            "custom_task_name": "Deadhead spent flowers",
        },
    }
    assert init_integration.state is ConfigEntryState.LOADED


async def test_add_plant_requires_name(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await start_plant_flow(hass, init_integration)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "   ", "preset": "rose"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"name": "name_required"}


async def test_add_custom_plant_requires_custom_task_name(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await start_plant_flow(hass, init_integration)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Mystery", "preset": "custom"}
    )
    assert result["step_id"] == "schedule"
    values = suggested(result)
    assert values["custom_task_name"] == ""
    assert all(values[f"{t}_months"] == [] for t in ("prune", "custom"))

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"custom_months": ["5"], "custom_interval": 0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "schedule"
    assert result["errors"] == {"custom_task_name": "custom_task_name_required"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "custom_months": ["5", "2"],
            "custom_interval": 0,
            "custom_task_name": " Remove suckers ",
            "water_interval": 3,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    subentry = next(
        s for s in init_integration.subentries.values() if s.title == "Mystery"
    )
    assert subentry.data["tasks"] == {
        "water": {"months": [], "interval_days": 3},
        "custom": {
            "months": [2, 5],
            "interval_days": 0,
            "custom_task_name": "Remove suckers",
        },
    }


async def test_custom_task_name_not_required_without_schedule(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await start_plant_flow(hass, init_integration)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Plain", "preset": "custom"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"water_interval": 5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_south_hemisphere_shifts_preset_months(hass: HomeAssistant) -> None:
    entry = make_entry(options={"hemisphere": "south"}, plants=[])
    await setup_entry(hass, entry)

    result = await start_plant_flow(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Southern rose", "preset": "rose"}
    )
    values = suggested(result)
    # North: prune March, fertilize Apr/Jun, protect Nov, deadhead Jun-Sep.
    assert values["prune_months"] == ["9"]
    assert values["fertilize_months"] == ["10", "12"]
    assert values["protect_months"] == ["5"]
    assert values["custom_months"] == ["1", "2", "3", "12"]
    assert values["custom_interval"] == 14

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], values
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data["tasks"]["prune"]["months"] == [9]
    assert subentry.data["tasks"]["custom"]["months"] == [1, 2, 3, 12]


async def test_reconfigure_keeps_created_and_prefills(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await start_plant_flow(
        hass, init_integration, "reconfigure", subentry_id=ROSE_SUBENTRY_ID
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert suggested(result)["name"] == "Front rose"
    assert suggested(result)["location"] == "Front yard"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Front rose renamed", "preset": "rose", "location": "Porch"},
    )
    assert result["step_id"] == "schedule"
    values = suggested(result)
    # Same preset: prefilled from the stored data, not from the preset library.
    assert values["prune_months"] == ["3"]
    assert values["fertilize_months"] == ["4", "6"]
    assert values["custom_task_name"] == "Deadhead spent flowers"

    values["prune_months"] = ["3", "4"]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], values
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    subentry = init_integration.subentries[ROSE_SUBENTRY_ID]
    assert subentry.title == "Front rose renamed"
    assert subentry.data["name"] == "Front rose renamed"
    assert subentry.data["location"] == "Porch"
    assert subentry.data["created"] == ROSE_DATA["created"] == "2026-01-01"
    assert subentry.data["tasks"]["prune"]["months"] == [3, 4]
    assert init_integration.state is ConfigEntryState.LOADED


async def test_reconfigure_other_preset_uses_preset_schedule(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await start_plant_flow(
        hass, init_integration, "reconfigure", subentry_id=ROSE_SUBENTRY_ID
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Front rose", "preset": "custom"}
    )
    values = suggested(result)
    assert values["prune_months"] == []  # custom preset starts empty


@pytest.mark.parametrize("source", ["user", "reconfigure"])
async def test_subentry_flow_aborts_when_entry_not_loaded(
    hass: HomeAssistant, source: str
) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)  # not set up
    result = await start_plant_flow(
        hass,
        entry,
        source,
        **({"subentry_id": ROSE_SUBENTRY_ID} if source == "reconfigure" else {}),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"
