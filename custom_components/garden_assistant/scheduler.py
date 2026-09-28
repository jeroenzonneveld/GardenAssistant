"""Pure scheduling logic for garden tasks.

This module has no Home Assistant dependencies so it can be unit tested
in isolation.

A task schedule combines two optional parts:

* ``months`` - the months (1-12) in which the task is active.
* ``interval_days`` - how often the task repeats.

Semantics:

* months only: the task is due once per *season*, i.e. once per contiguous
  run of active months (wrapping December -> January). It becomes due on the
  first day of the season and is done for that season once completed.
* interval only: the task repeats every ``interval_days`` after it was last
  done (or after the plant was added).
* months and interval: the task repeats every ``interval_days`` but only
  while in an active month. A due date falling outside the active months
  is moved to the start of the next season.
* neither: the task is inactive and never due.

A snooze pushes the due date to at least ``snoozed_until``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta

# Safety bound for iterating over future occurrences.
_MAX_OCCURRENCES = 1000


@dataclass(frozen=True, slots=True)
class TaskSchedule:
    """Configured schedule for one task."""

    months: frozenset[int] = frozenset()
    interval_days: int = 0

    @classmethod
    def from_parts(
        cls, months: Iterable[int | str] | None, interval_days: int | None
    ) -> TaskSchedule:
        """Build a schedule from loosely typed config values."""
        parsed = frozenset(int(m) for m in (months or ()) if 1 <= int(m) <= 12)
        return cls(months=parsed, interval_days=max(0, int(interval_days or 0)))

    @property
    def active(self) -> bool:
        """Return True if the schedule can ever produce a due date."""
        return bool(self.months) or self.interval_days > 0


@dataclass(frozen=True, slots=True)
class TaskState:
    """Mutable-in-storage progress for one task, as an immutable value."""

    last_done: date | None = None
    snoozed_until: date | None = None


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _month_end(year: int, month: int) -> date:
    ny, nm = _add_months(year, month, 1)
    return date(ny, nm, 1) - timedelta(days=1)


def season_windows(months: frozenset[int], around: date) -> list[tuple[date, date]]:
    """Return season windows (start, end inclusive) overlapping a 3 year span.

    Windows are contiguous runs of active months. When all twelve months are
    active the season is a calendar year.
    """
    if not months:
        return []
    windows: list[tuple[date, date]] = []
    if len(months) == 12:
        for year in range(around.year - 1, around.year + 3):
            windows.append((date(year, 1, 1), date(year, 12, 31)))
        return windows

    # Walk month by month from two years back to two years ahead.
    year, month = around.year - 2, 1
    start: tuple[int, int] | None = None
    prev_active = False
    for _ in range(12 * 5):
        is_active = month in months
        if is_active and not prev_active:
            start = (year, month)
        if not is_active and prev_active and start is not None:
            py, pm = _add_months(year, month, -1)
            windows.append((date(start[0], start[1], 1), _month_end(py, pm)))
            start = None
        prev_active = is_active
        year, month = _add_months(year, month, 1)
    # Windows that started at the very beginning of the walk may be partial;
    # they are far enough in the past not to matter.
    return windows


def _next_active_day(months: frozenset[int], day: date) -> date:
    """Return ``day`` if it is in an active month, else the next season start."""
    if not months or day.month in months:
        return day
    year, month = day.year, day.month
    for _ in range(12):
        year, month = _add_months(year, month, 1)
        if month in months:
            return date(year, month, 1)
    return day  # unreachable when months is non-empty


def next_due(
    schedule: TaskSchedule,
    state: TaskState,
    today: date,
    created: date,
) -> date | None:
    """Return the next due date for a task, or None when inactive.

    The returned date may be in the past (the task is overdue).
    """
    if not schedule.active:
        return None

    due: date | None
    if schedule.interval_days > 0:
        base = state.last_done or created
        if state.last_done is None:
            # Never done: due as soon as it is allowed.
            due = _next_active_day(schedule.months, created)
        else:
            due = _next_active_day(
                schedule.months, base + timedelta(days=schedule.interval_days)
            )
    else:
        due = None
        for start, end in season_windows(schedule.months, today):
            if end < today:
                continue
            if state.last_done is not None and start <= state.last_done:
                # Already done in (or after the start of) this season.
                continue
            due = start
            break

    if due is None:
        return None
    if state.snoozed_until is not None and state.snoozed_until > due:
        due = state.snoozed_until
    return due


def occurrences(
    schedule: TaskSchedule,
    state: TaskState,
    today: date,
    created: date,
    start: date,
    end: date,
) -> Iterator[date]:
    """Yield projected due dates between ``start`` and ``end`` (inclusive).

    The first occurrence is the real next due date; later occurrences assume
    the task will be completed on the day it becomes due.
    """
    due = next_due(schedule, state, today, created)
    count = 0
    while due is not None and due <= end and count < _MAX_OCCURRENCES:
        if due >= start:
            yield due
        count += 1
        # Assume completion on the due date and compute the following one.
        following = next_due(
            schedule,
            TaskState(last_done=due),
            max(today, due + timedelta(days=1)),
            created,
        )
        if following is None or following <= due:
            break
        due = following
