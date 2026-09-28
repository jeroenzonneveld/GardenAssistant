"""Unit tests for the pure scheduling logic."""

from datetime import date

import pytest

from custom_components.garden_assistant.scheduler import (
    TaskSchedule,
    TaskState,
    next_due,
    occurrences,
    season_windows,
)

CREATED = date(2025, 1, 1)


def sched(months=(), interval=0) -> TaskSchedule:
    return TaskSchedule.from_parts(months, interval)


class TestSchedule:
    def test_from_parts_filters_and_converts(self):
        s = TaskSchedule.from_parts(["1", 3, "13", 0, 12], "14")
        assert s.months == frozenset({1, 3, 12})
        assert s.interval_days == 14

    def test_from_parts_none_and_negative(self):
        s = TaskSchedule.from_parts(None, None)
        assert s == TaskSchedule()
        assert not s.active
        assert TaskSchedule.from_parts([], -5).interval_days == 0

    def test_active(self):
        assert sched(months=[3]).active
        assert sched(interval=7).active
        assert not sched().active

    def test_inactive_never_due(self):
        assert next_due(sched(), TaskState(), date(2026, 5, 1), CREATED) is None


class TestMonthsOnly:
    def test_in_season_not_done_is_due_since_season_start(self):
        due = next_due(sched([3, 4]), TaskState(), date(2026, 3, 15), CREATED)
        assert due == date(2026, 3, 1)

    def test_before_season_upcoming(self):
        due = next_due(sched([3, 4]), TaskState(), date(2026, 1, 10), CREATED)
        assert due == date(2026, 3, 1)

    def test_done_in_season_rolls_to_next_year(self):
        state = TaskState(last_done=date(2026, 3, 10))
        due = next_due(sched([3, 4]), state, date(2026, 3, 15), CREATED)
        assert due == date(2027, 3, 1)

    def test_done_on_last_day_of_season(self):
        state = TaskState(last_done=date(2026, 4, 30))
        due = next_due(sched([3, 4]), state, date(2026, 4, 30), CREATED)
        assert due == date(2027, 3, 1)

    def test_missed_season_rolls_over(self):
        due = next_due(sched([3, 4]), TaskState(), date(2026, 6, 1), CREATED)
        assert due == date(2027, 3, 1)

    def test_day_after_season_end_rolls_over(self):
        due = next_due(sched([3, 4]), TaskState(), date(2026, 5, 1), CREATED)
        assert due == date(2027, 3, 1)

    def test_done_previous_year_is_due_again(self):
        state = TaskState(last_done=date(2025, 3, 20))
        due = next_due(sched([3, 4]), state, date(2026, 3, 2), CREATED)
        assert due == date(2026, 3, 1)

    def test_done_before_season_start_is_still_due(self):
        state = TaskState(last_done=date(2026, 2, 20))
        due = next_due(sched([3, 4]), state, date(2026, 3, 2), CREATED)
        assert due == date(2026, 3, 1)

    def test_multiple_seasons_per_year(self):
        s = sched([3, 4, 9])
        assert next_due(s, TaskState(), date(2026, 5, 1), CREATED) == date(2026, 9, 1)
        state = TaskState(last_done=date(2026, 9, 5))
        assert next_due(s, state, date(2026, 9, 6), CREATED) == date(2027, 3, 1)

    def test_single_month(self):
        s = sched([10])
        assert next_due(s, TaskState(), date(2026, 9, 28), CREATED) == date(2026, 10, 1)


class TestWrapAround:
    """Season Nov-Jan crosses the year boundary."""

    S = sched([11, 12, 1])

    def test_windows_wrap(self):
        windows = season_windows(self.S.months, date(2026, 6, 1))
        assert (date(2026, 11, 1), date(2027, 1, 31)) in windows
        assert (date(2025, 11, 1), date(2026, 1, 31)) in windows

    def test_before_season(self):
        assert next_due(self.S, TaskState(), date(2026, 6, 1), CREATED) == date(
            2026, 11, 1
        )

    def test_in_season_december(self):
        assert next_due(self.S, TaskState(), date(2026, 12, 15), CREATED) == date(
            2026, 11, 1
        )

    def test_in_season_january_belongs_to_previous_november(self):
        assert next_due(self.S, TaskState(), date(2027, 1, 10), CREATED) == date(
            2026, 11, 1
        )

    def test_done_in_november_covers_january(self):
        state = TaskState(last_done=date(2026, 11, 20))
        assert next_due(self.S, state, date(2027, 1, 10), CREATED) == date(2027, 11, 1)

    def test_done_in_january_covers_that_season(self):
        state = TaskState(last_done=date(2027, 1, 5))
        assert next_due(self.S, state, date(2027, 1, 10), CREATED) == date(2027, 11, 1)

    def test_after_season_end(self):
        assert next_due(self.S, TaskState(), date(2027, 2, 1), CREATED) == date(
            2027, 11, 1
        )


class TestAllMonths:
    S = sched(range(1, 13))

    def test_calendar_year_season(self):
        assert next_due(self.S, TaskState(), date(2026, 6, 1), CREATED) == date(
            2026, 1, 1
        )

    def test_done_this_year_rolls_to_next(self):
        state = TaskState(last_done=date(2026, 2, 1))
        assert next_due(self.S, state, date(2026, 6, 1), CREATED) == date(2027, 1, 1)

    def test_done_last_year_due_again(self):
        state = TaskState(last_done=date(2025, 12, 31))
        assert next_due(self.S, state, date(2026, 1, 2), CREATED) == date(2026, 1, 1)

    def test_windows_are_calendar_years(self):
        windows = season_windows(self.S.months, date(2026, 6, 1))
        assert (date(2026, 1, 1), date(2026, 12, 31)) in windows


class TestIntervalOnly:
    def test_never_done_due_at_creation(self):
        created = date(2026, 5, 1)
        due = next_due(sched(interval=14), TaskState(), date(2026, 5, 20), created)
        assert due == created

    def test_done_due_after_interval(self):
        state = TaskState(last_done=date(2026, 6, 1))
        due = next_due(sched(interval=14), state, date(2026, 6, 2), CREATED)
        assert due == date(2026, 6, 15)

    def test_overdue_stays_in_past(self):
        state = TaskState(last_done=date(2026, 1, 1))
        due = next_due(sched(interval=7), state, date(2026, 3, 1), CREATED)
        assert due == date(2026, 1, 8)

    def test_interval_crosses_year_end(self):
        state = TaskState(last_done=date(2026, 12, 25))
        due = next_due(sched(interval=10), state, date(2026, 12, 26), CREATED)
        assert due == date(2027, 1, 4)


class TestMonthsAndInterval:
    S = sched([5, 6, 7, 8], 28)

    def test_next_within_season(self):
        state = TaskState(last_done=date(2026, 7, 1))
        assert next_due(self.S, state, date(2026, 7, 2), CREATED) == date(2026, 7, 29)

    def test_last_day_in_season_is_kept(self):
        state = TaskState(last_done=date(2026, 8, 3))
        assert next_due(self.S, state, date(2026, 8, 4), CREATED) == date(2026, 8, 31)

    def test_clamped_to_next_season(self):
        state = TaskState(last_done=date(2026, 8, 20))
        assert next_due(self.S, state, date(2026, 8, 21), CREATED) == date(2027, 5, 1)

    def test_never_done_created_before_season(self):
        created = date(2026, 2, 10)
        assert next_due(self.S, TaskState(), created, created) == date(2026, 5, 1)

    def test_never_done_created_in_season(self):
        created = date(2026, 6, 10)
        assert next_due(self.S, TaskState(), created, created) == created

    def test_wraparound_season_with_interval(self):
        s = sched([11, 12, 1], 14)
        state = TaskState(last_done=date(2026, 12, 25))
        assert next_due(s, state, date(2026, 12, 26), CREATED) == date(2027, 1, 8)
        state = TaskState(last_done=date(2027, 1, 25))
        assert next_due(s, state, date(2027, 1, 26), CREATED) == date(2027, 11, 1)


class TestSnooze:
    def test_snooze_pushes_due_date(self):
        state = TaskState(last_done=date(2026, 6, 1), snoozed_until=date(2026, 6, 20))
        assert next_due(sched(interval=14), state, date(2026, 6, 16), CREATED) == date(
            2026, 6, 20
        )

    def test_snooze_earlier_than_due_is_ignored(self):
        state = TaskState(last_done=date(2026, 6, 1), snoozed_until=date(2026, 6, 5))
        assert next_due(sched(interval=14), state, date(2026, 6, 2), CREATED) == date(
            2026, 6, 15
        )

    def test_snooze_months_only(self):
        state = TaskState(snoozed_until=date(2026, 3, 10))
        assert next_due(sched([3]), state, date(2026, 3, 2), CREATED) == date(
            2026, 3, 10
        )

    def test_snooze_ignored_for_inactive(self):
        state = TaskState(snoozed_until=date(2026, 3, 10))
        assert next_due(sched(), state, date(2026, 3, 2), CREATED) is None


class TestOccurrences:
    def test_inactive_yields_nothing(self):
        result = list(
            occurrences(
                sched(), TaskState(), date(2026, 1, 1), CREATED,
                date(2026, 1, 1), date(2027, 1, 1),
            )
        )  # fmt: skip
        assert result == []

    def test_interval_series(self):
        created = date(2026, 1, 1)
        result = list(
            occurrences(
                sched(interval=10), TaskState(), created, created,
                date(2026, 1, 1), date(2026, 1, 31),
            )
        )  # fmt: skip
        assert result == [
            date(2026, 1, 1),
            date(2026, 1, 11),
            date(2026, 1, 21),
            date(2026, 1, 31),
        ]

    def test_start_filters_earlier_dates(self):
        created = date(2026, 1, 1)
        result = list(
            occurrences(
                sched(interval=10), TaskState(), created, created,
                date(2026, 1, 15), date(2026, 2, 5),
            )
        )  # fmt: skip
        assert result == [date(2026, 1, 21), date(2026, 1, 31)]

    def test_months_only_yearly(self):
        result = list(
            occurrences(
                sched([3]), TaskState(), date(2026, 1, 15), CREATED,
                date(2026, 1, 1), date(2028, 12, 31),
            )
        )  # fmt: skip
        assert result == [date(2026, 3, 1), date(2027, 3, 1), date(2028, 3, 1)]

    def test_first_occurrence_respects_state(self):
        state = TaskState(last_done=date(2026, 3, 5))
        result = list(
            occurrences(
                sched([3]), state, date(2026, 3, 6), CREATED,
                date(2026, 1, 1), date(2028, 12, 31),
            )
        )  # fmt: skip
        assert result == [date(2027, 3, 1), date(2028, 3, 1)]

    def test_first_occurrence_respects_snooze(self):
        state = TaskState(last_done=date(2026, 6, 1), snoozed_until=date(2026, 6, 20))
        result = list(
            occurrences(
                sched(interval=14), state, date(2026, 6, 10), CREATED,
                date(2026, 6, 1), date(2026, 7, 10),
            )
        )  # fmt: skip
        assert result == [date(2026, 6, 20), date(2026, 7, 4)]

    def test_months_and_interval_skip_off_season(self):
        created = date(2026, 5, 1)
        result = list(
            occurrences(
                sched([5, 6], 30), TaskState(), created, created,
                date(2026, 5, 1), date(2027, 6, 30),
            )
        )  # fmt: skip
        assert result == [
            date(2026, 5, 1),
            date(2026, 5, 31),
            date(2026, 6, 30),
            date(2027, 5, 1),
            date(2027, 5, 31),
            date(2027, 6, 30),
        ]

    def test_overdue_first_occurrence_in_past_is_included_when_in_range(self):
        state = TaskState(last_done=date(2026, 1, 1))
        result = list(
            occurrences(
                sched(interval=30), state, date(2026, 3, 1), CREATED,
                date(2026, 1, 1), date(2026, 3, 15),
            )
        )  # fmt: skip
        assert result[0] == date(2026, 1, 31)

    def test_end_before_first_yields_nothing(self):
        result = list(
            occurrences(
                sched([10]), TaskState(), date(2026, 1, 1), CREATED,
                date(2026, 1, 1), date(2026, 6, 1),
            )
        )  # fmt: skip
        assert result == []

    @pytest.mark.parametrize("months", [[1], [11, 12, 1], list(range(1, 13))])
    def test_occurrences_strictly_increasing(self, months):
        result = list(
            occurrences(
                sched(months), TaskState(), date(2026, 6, 1), CREATED,
                date(2026, 1, 1), date(2032, 12, 31),
            )
        )  # fmt: skip
        assert result == sorted(set(result))
        assert len(result) >= 5
