"""Tests for events and notifications."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant.components.persistent_notification import (
    _async_get_or_create_notifications,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from .conftest import ROSE_SUBENTRY_ID, TOMATO_SUBENTRY_ID, make_entry, setup_entry

ROSE = ROSE_SUBENTRY_ID
TOMATO = TOMATO_SUBENTRY_ID
STORE_KEY = "garden_assistant.state.garden_entry"

# Notification time used in the tests (UTC, see the fixture below).
NOTIFY_DAY_1 = "2026-03-10 08:00:00+00:00"
NOTIFY_DAY_2 = "2026-03-11 08:00:00+00:00"
NOTIFY_DAY_3 = "2026-03-12 08:00:00+00:00"


@pytest.fixture(autouse=True)
async def utc_timezone(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Use UTC and start before 08:00 so the first daily trigger is today's."""
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-03-10 07:00:00+00:00")


async def fire_daily(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: str
) -> None:
    """Move time to ``when`` and fire the time trigger."""
    freezer.move_to(when)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)


def persistent_message(hass: HomeAssistant) -> str | None:
    notification = _async_get_or_create_notifications(hass).get("garden_assistant_due")
    return notification["message"] if notification else None


# ------------------------------------------------------------------- events


async def test_event_fired_once_per_due_date(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, make_entry())
    events = async_capture_events(hass, "garden_assistant_task_due")

    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert len(events) == 1
    assert events[0].data["task"] == "prune"

    # Next day: same due date, no repeat_daily -> nothing new.
    await fire_daily(hass, freezer, NOTIFY_DAY_2)
    assert len(events) == 1

    # The tomato becomes due on 2026-03-12 -> one new event for it only.
    await fire_daily(hass, freezer, NOTIFY_DAY_3)
    assert len(events) == 2
    assert events[1].data["task"] == "water"
    assert events[1].data["plant"] == "Tomato"
    assert events[1].data["due"] == "2026-03-12"
    assert events[1].data["days_until"] == 0


async def test_event_first_run_data_is_exact(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, make_entry())
    events = async_capture_events(hass, "garden_assistant_task_due")
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert [e.data for e in events] == [
        {
            "entry_id": "garden_entry",
            "subentry_id": ROSE,
            "plant": "Front rose",
            "task": "prune",
            "task_name": "Prune",
            "due": "2026-03-01",
            "days_until": -9,
            "status": "due",
        }
    ]


async def test_event_repeats_daily_with_repeat_daily(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, make_entry(options={"repeat_daily": True}))
    events = async_capture_events(hass, "garden_assistant_task_due")

    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    await fire_daily(hass, freezer, NOTIFY_DAY_2)
    assert [e.data["task"] for e in events] == ["prune", "prune"]
    assert [e.data["days_until"] for e in events] == [-9, -10]


async def test_event_fired_even_when_notifications_disabled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, make_entry(options={"notify_enabled": False}))
    events = async_capture_events(hass, "garden_assistant_task_due")
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert len(events) == 1
    assert persistent_message(hass) is None


async def test_event_for_upcoming_tasks_within_lead_days(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, make_entry(options={"lead_days": 3}))
    events = async_capture_events(hass, "garden_assistant_task_due")
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    by_task = {e.data["task"]: e.data for e in events}
    assert set(by_task) == {"prune", "water"}
    assert by_task["water"]["status"] == "upcoming"
    assert by_task["water"]["days_until"] == 2


async def test_no_event_after_task_completed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_entry(hass, make_entry(options={"repeat_daily": True}))
    events = async_capture_events(hass, "garden_assistant_task_due")
    await entry.runtime_data.async_complete_task(ROSE, "prune")
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert events == []


async def test_notified_bookkeeping_persisted(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    await setup_entry(hass, make_entry())
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    stored = hass_storage[STORE_KEY]["data"]["plants"]
    assert stored[ROSE]["prune"]["notified_due"] == "2026-03-01"


async def test_notification_time_option_is_respected(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, make_entry(options={"notify_time": "09:15:00"}))
    events = async_capture_events(hass, "garden_assistant_task_due")
    await fire_daily(hass, freezer, NOTIFY_DAY_1)  # 08:00 -> not the time
    assert events == []
    await fire_daily(hass, freezer, "2026-03-10 09:15:00+00:00")
    assert len(events) == 1


async def test_invalid_notify_time_falls_back_to_default(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await setup_entry(hass, make_entry(options={"notify_time": "garbage"}))
    assert "Invalid notify time" in caplog.text
    events = async_capture_events(hass, "garden_assistant_task_due")
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert len(events) == 1


# -------------------------------------------------------- persistent + notify


async def test_persistent_notification_created(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(
        hass,
        make_entry(
            options={"notify_enabled": True, "notify_persistent": True, "lead_days": 3}
        ),
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    notification = _async_get_or_create_notifications(hass)["garden_assistant_due"]
    assert notification["title"] == "Garden Assistant"
    assert notification["message"] == (
        "Front rose: Prune (overdue by 9 days)\nTomato: Water (due in 2 days)"
    )


async def test_no_persistent_notification_when_disabled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(
        hass, make_entry(options={"notify_enabled": True, "notify_persistent": False})
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert persistent_message(hass) is None


async def test_persistent_notification_dismissed_when_nothing_pending(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_entry(hass, make_entry(options={"notify_enabled": True}))
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert persistent_message(hass) is not None

    await entry.runtime_data.async_complete_task(ROSE, "prune")
    await fire_daily(hass, freezer, NOTIFY_DAY_2)
    assert persistent_message(hass) is None


async def test_notify_service_called_with_actions(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_entry(
        hass,
        make_entry(
            options={
                "notify_enabled": True,
                "notify_services": ["notify.mobile_app_test"],
                "actionable_notifications": True,
            }
        ),
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)

    assert len(calls) == 1
    data = calls[0].data
    assert data["title"] == "Garden Assistant"
    assert data["message"] == "Front rose: Prune (overdue by 9 days)"
    assert data["data"]["tag"] == f"garden_assistant_{ROSE}_prune"
    assert data["data"]["actions"] == [
        {"action": f"GARDEN_DONE|{ROSE}|prune", "title": "Done"},
        {"action": f"GARDEN_SNOOZE|{ROSE}|prune", "title": "Snooze 1 day"},
    ]


async def test_service_name_without_prefix_and_one_message_per_task(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    await setup_entry(
        hass,
        make_entry(
            options={
                "notify_enabled": True,
                "notify_services": ["mobile_app_test"],
                "lead_days": 3,
            }
        ),
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert [c.data["message"] for c in calls] == [
        "Front rose: Prune (overdue by 9 days)",
        "Tomato: Water (due in 2 days)",
    ]
    assert all("actions" in c.data["data"] for c in calls)


async def test_non_actionable_sends_combined_message_without_actions(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    other = async_mock_service(hass, "notify", "living_room_tv")
    await setup_entry(
        hass,
        make_entry(
            options={
                "notify_enabled": True,
                "notify_services": ["notify.mobile_app_test", "notify.living_room_tv"],
                "actionable_notifications": False,
                "lead_days": 3,
            }
        ),
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    expected = "Front rose: Prune (overdue by 9 days)\nTomato: Water (due in 2 days)"
    assert [c.data["message"] for c in calls] == [expected]
    assert calls[0].data["data"] == {}
    assert [c.data["message"] for c in other] == [expected]


async def test_actionable_only_for_mobile_app_services(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    other = async_mock_service(hass, "notify", "living_room_tv")
    await setup_entry(
        hass,
        make_entry(
            options={
                "notify_enabled": True,
                "notify_services": ["notify.living_room_tv"],
                "actionable_notifications": True,
            }
        ),
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert len(other) == 1
    assert other[0].data["data"] == {}


async def test_actionable_messages_capped_at_ten_with_remainder(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    plants = [
        (
            f"plant_{i:02d}",
            {
                "name": f"Plant {i:02d}",
                "preset": "custom",
                "created": "2026-03-01",
                "tasks": {"water": {"months": [], "interval_days": 7}},
            },
        )
        for i in range(12)
    ]
    await setup_entry(
        hass,
        make_entry(
            options={
                "notify_enabled": True,
                "notify_services": ["notify.mobile_app_test"],
            },
            plants=plants,
        ),
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert len(calls) == 11
    assert all("actions" in c.data["data"] for c in calls[:10])
    assert calls[10].data["data"] == {}
    assert calls[10].data["message"].count("\n") == 1  # the two remaining tasks


async def test_failing_notify_service_does_not_block_others(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken(call: ServiceCall) -> None:
        raise RuntimeError("push service down")

    hass.services.async_register("notify", "broken", broken)
    good = async_mock_service(hass, "notify", "good")
    await setup_entry(
        hass,
        make_entry(
            options={
                "notify_enabled": True,
                "notify_services": ["notify.broken", "notify.missing", "notify.good"],
            }
        ),
    )
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert len(good) == 1
    assert "Sending notification via notify.broken failed" in caplog.text
    assert "notify.missing not found" in caplog.text


# ------------------------------------------------------------ mobile actions


async def send_action(hass: HomeAssistant, action: Any) -> None:
    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()


async def test_done_action_marks_task_done(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    completed = async_capture_events(hass, "garden_assistant_task_completed")
    await send_action(hass, f"GARDEN_DONE|{ROSE}|prune")

    prune = hass.states.get("sensor.front_rose_prune")
    assert prune.attributes["last_done"] == "2026-03-10"
    assert prune.attributes["status"] == "scheduled"
    assert len(completed) == 1


async def test_snooze_action_snoozes_one_day(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    await send_action(hass, f"GARDEN_SNOOZE|{ROSE}|prune")
    prune = hass.states.get("sensor.front_rose_prune")
    assert prune.attributes["snoozed_until"] == "2026-03-11"
    assert prune.state == "2026-03-11"


@pytest.mark.parametrize(
    "action",
    [
        None,
        42,
        "SOMETHING_ELSE",
        "GARDEN_DONE|only_two",
        "GARDEN_DONE|unknown_plant|prune",
        f"GARDEN_DONE|{ROSE}|water",  # rose has no water task
        f"GARDEN_DONE|{ROSE}|prune|extra",
        f"GARDEN_NOPE|{ROSE}|prune",
    ],
)
async def test_invalid_actions_are_ignored(
    hass: HomeAssistant, init_integration: MockConfigEntry, action: Any
) -> None:
    await send_action(hass, action)
    prune = hass.states.get("sensor.front_rose_prune")
    assert prune.attributes["last_done"] is None
    assert prune.attributes["snoozed_until"] is None


async def test_done_action_dismisses_persistent_notification_when_empty(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, make_entry(options={"notify_enabled": True}))
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert persistent_message(hass) is not None
    await send_action(hass, f"GARDEN_DONE|{ROSE}|prune")
    assert persistent_message(hass) is None


async def test_action_listener_removed_on_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    coordinator = init_integration.runtime_data
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    before = coordinator._state["plants"].get(ROSE, {}).get("prune", {}).copy()
    await send_action(hass, f"GARDEN_DONE|{ROSE}|prune")
    after = coordinator._state["plants"].get(ROSE, {}).get("prune", {})
    assert after == before


async def test_time_trigger_removed_on_unload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_entry(hass, make_entry())
    events = async_capture_events(hass, "garden_assistant_task_due")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await fire_daily(hass, freezer, NOTIFY_DAY_1)
    assert events == []
