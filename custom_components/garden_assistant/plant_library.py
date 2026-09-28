"""Built-in plant presets for Garden Assistant.

All presets are defined for the *northern hemisphere* in a temperate
(north-west European) climate. Use :func:`preset_tasks` to get the schedule
shifted to the user's hemisphere.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .const import (
    CONF_CUSTOM_TASK_NAME,
    CONF_INTERVAL_DAYS,
    CONF_MONTHS,
    HEMISPHERE_SOUTH,
    TASK_CUSTOM,
)

TASK_LABELS: dict[str, str] = {
    "prune": "Prune",
    "fertilize": "Fertilize",
    "water": "Water",
    "harvest": "Harvest",
    "sow": "Sow / plant",
    "protect": "Winter protection",
    "custom": "Custom task",
}

MONTH_NAMES: dict[int, str] = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

# (months, interval_days)
TaskSpec = tuple[tuple[int, ...], int]


@dataclass(frozen=True, slots=True)
class PlantPreset:
    """A plant care preset (northern hemisphere)."""

    label: str
    species: str
    tasks: dict[str, TaskSpec] = field(default_factory=dict)
    custom_task_name: str = ""


def _p(
    label: str,
    species: str,
    custom_label: str = "",
    **tasks: TaskSpec,
) -> PlantPreset:
    return PlantPreset(label, species, dict(tasks), custom_label)


_SUMMER = (6, 7, 8)
_GROWING = (5, 6, 7, 8, 9)

PLANT_LIBRARY: dict[str, PlantPreset] = {
    "rose": _p(
        "Rose",
        "Rosa",
        "Deadhead spent flowers",
        prune=((3,), 0),
        fertilize=((4, 6), 0),
        protect=((11,), 0),
        custom=((6, 7, 8, 9), 14),
    ),
    "hydrangea": _p(
        "Hydrangea (bigleaf)",
        "Hydrangea macrophylla",
        prune=((3, 4), 0),
        fertilize=((4, 6), 0),
        water=(_SUMMER, 3),
        protect=((11,), 0),
    ),
    "lavender": _p(
        "Lavender",
        "Lavandula angustifolia",
        prune=((4, 8), 0),
        fertilize=((4,), 0),
        water=((7, 8), 14),
    ),
    "boxwood": _p(
        "Boxwood",
        "Buxus sempervirens",
        prune=((5, 6, 9), 0),
        fertilize=((4, 6), 0),
        water=(_SUMMER, 7),
    ),
    "hedge": _p(
        "Hedge (beech / privet)",
        "Fagus sylvatica / Ligustrum",
        prune=((6, 7, 9), 0),
        fertilize=((3, 4), 0),
        water=(_SUMMER, 10),
    ),
    "apple": _p(
        "Apple tree",
        "Malus domestica",
        prune=((1, 2, 7), 0),
        fertilize=((3, 4), 0),
        harvest=((9, 10), 0),
        water=(_SUMMER, 10),
    ),
    "pear": _p(
        "Pear tree",
        "Pyrus communis",
        prune=((1, 2, 7), 0),
        fertilize=((3, 4), 0),
        harvest=((8, 9, 10), 0),
        water=(_SUMMER, 10),
    ),
    "cherry": _p(
        "Cherry tree",
        "Prunus avium",
        prune=((7, 8), 0),
        fertilize=((3, 4), 0),
        harvest=((6, 7), 0),
        water=((5, 6, 7), 14),
    ),
    "plum": _p(
        "Plum tree",
        "Prunus domestica",
        prune=((7, 8), 0),
        fertilize=((3, 4), 0),
        harvest=((8, 9), 0),
        water=(_SUMMER, 14),
    ),
    "grapevine": _p(
        "Grapevine",
        "Vitis vinifera",
        prune=((1, 2, 7), 0),
        fertilize=((3, 4), 0),
        harvest=((9, 10), 0),
        water=((6, 7, 8), 14),
    ),
    "raspberry": _p(
        "Raspberry",
        "Rubus idaeus",
        prune=((2, 8), 0),
        fertilize=((3, 4), 0),
        harvest=((6, 7, 8, 9), 0),
        water=(_SUMMER, 7),
    ),
    "blueberry": _p(
        "Blueberry",
        "Vaccinium corymbosum",
        prune=((2, 3), 0),
        fertilize=((4, 5), 0),
        harvest=((7, 8, 9), 0),
        water=((5, 6, 7, 8, 9), 3),
    ),
    "strawberry": _p(
        "Strawberry",
        "Fragaria x ananassa",
        prune=((8,), 0),
        fertilize=((3, 4), 0),
        harvest=((6, 7), 0),
        sow=((8, 9), 0),
        water=((5, 6, 7, 8), 3),
    ),
    "tomato": _p(
        "Tomato",
        "Solanum lycopersicum",
        "Remove side shoots",
        prune=((6, 7, 8), 0),
        fertilize=((6, 7, 8, 9), 14),
        harvest=((8, 9, 10), 0),
        sow=((3, 4, 5), 0),
        water=((5, 6, 7, 8, 9), 2),
        custom=((6, 7, 8), 7),
    ),
    "potato": _p(
        "Potato",
        "Solanum tuberosum",
        "Earth up plants",
        fertilize=((4, 5), 0),
        harvest=((6, 7, 8, 9), 0),
        sow=((3, 4), 0),
        water=((5, 6, 7), 7),
        custom=((5, 6), 21),
    ),
    "courgette": _p(
        "Courgette",
        "Cucurbita pepo",
        fertilize=((6, 7, 8), 14),
        harvest=((7, 8, 9), 3),
        sow=((4, 5), 0),
        water=((6, 7, 8, 9), 3),
    ),
    "runner_bean": _p(
        "Runner bean",
        "Phaseolus coccineus",
        fertilize=((6, 7), 0),
        harvest=((7, 8, 9), 3),
        sow=((5, 6), 0),
        water=((6, 7, 8, 9), 3),
    ),
    "lettuce": _p(
        "Lettuce",
        "Lactuca sativa",
        fertilize=((4, 5, 6, 7, 8), 0),
        harvest=((5, 6, 7, 8, 9, 10), 7),
        sow=((3, 4, 5, 6, 7, 8), 21),
        water=((4, 5, 6, 7, 8, 9), 2),
    ),
    "rosemary": _p(
        "Rosemary",
        "Salvia rosmarinus",
        prune=((5, 8), 0),
        harvest=((5, 6, 7, 8, 9), 0),
        protect=((11,), 0),
        water=((6, 7, 8), 10),
    ),
    "thyme": _p(
        "Thyme",
        "Thymus vulgaris",
        prune=((4, 8), 0),
        harvest=((5, 6, 7, 8, 9), 0),
        water=((6, 7, 8), 10),
    ),
    "mint": _p(
        "Mint",
        "Mentha",
        prune=((3, 9), 0),
        fertilize=((4, 6), 0),
        harvest=((5, 6, 7, 8, 9), 0),
        water=((5, 6, 7, 8, 9), 3),
    ),
    "basil": _p(
        "Basil",
        "Ocimum basilicum",
        "Pinch out flower buds",
        fertilize=((5, 6, 7, 8), 14),
        harvest=((6, 7, 8, 9), 7),
        sow=((4, 5, 6), 0),
        water=((5, 6, 7, 8, 9), 2),
        custom=((6, 7, 8), 14),
    ),
    "clematis": _p(
        "Clematis",
        "Clematis",
        prune=((2, 3), 0),
        fertilize=((3, 5), 0),
        water=(_SUMMER, 7),
    ),
    "wisteria": _p(
        "Wisteria",
        "Wisteria sinensis",
        prune=((2, 7, 8), 0),
        fertilize=((3,), 0),
        water=((6, 7, 8), 14),
    ),
    "buddleja": _p(
        "Buddleja (butterfly bush)",
        "Buddleja davidii",
        prune=((3, 4), 0),
        fertilize=((4,), 0),
        water=((7, 8), 14),
    ),
    "lawn": _p(
        "Lawn",
        "Lolium / Poa mix",
        "Scarify / aerate",
        fertilize=((4, 6, 9), 0),
        sow=((4, 9), 0),
        water=((6, 7, 8), 7),
        prune=((4, 5, 6, 7, 8, 9, 10), 7),  # mowing
        custom=((4, 9), 0),
    ),
    "fuchsia": _p(
        "Fuchsia",
        "Fuchsia magellanica",
        prune=((3, 4), 0),
        fertilize=((5, 6, 7, 8), 14),
        water=((5, 6, 7, 8, 9), 3),
        protect=((10, 11), 0),
    ),
    "dahlia": _p(
        "Dahlia",
        "Dahlia",
        "Lift and store tubers",
        fertilize=((6, 7, 8), 14),
        sow=((5,), 0),
        water=((6, 7, 8, 9), 4),
        protect=((10, 11), 0),
        custom=((10, 11), 0),
    ),
    "tulip": _p(
        "Tulip bulbs",
        "Tulipa",
        "Lift and dry bulbs (optional)",
        fertilize=((3, 4), 0),
        sow=((10, 11), 0),
        custom=((6, 7), 0),
    ),
    "olive_pot": _p(
        "Olive tree (in pot)",
        "Olea europaea",
        prune=((3, 4), 0),
        fertilize=((4, 5, 6, 7, 8), 28),
        water=((5, 6, 7, 8, 9), 5),
        protect=((11,), 0),
    ),
    "fig": _p(
        "Fig",
        "Ficus carica",
        prune=((3, 4), 0),
        fertilize=((4, 5), 0),
        harvest=((8, 9, 10), 0),
        water=(_SUMMER, 7),
        protect=((11,), 0),
    ),
    "rhododendron": _p(
        "Rhododendron",
        "Rhododendron",
        prune=((5, 6), 0),
        fertilize=((3, 4, 6), 0),
        water=((5, 6, 7, 8), 7),
    ),
    "ornamental_grass": _p(
        "Ornamental grasses",
        "Miscanthus / Calamagrostis",
        prune=((2, 3), 0),
        fertilize=((4,), 0),
        water=((7, 8), 14),
    ),
}


def shift_months(months: Iterable[int | str], hemisphere: str) -> list[int]:
    """Return sorted months, moved by six months for the southern hemisphere."""
    parsed = {int(m) for m in months if 1 <= int(m) <= 12}
    if hemisphere == HEMISPHERE_SOUTH:
        parsed = {(m + 5) % 12 + 1 for m in parsed}
    return sorted(parsed)


def preset_tasks(preset_key: str, hemisphere: str) -> dict[str, dict]:
    """Return the CONF_TASKS structure for a preset in the given hemisphere.

    Unknown preset keys (e.g. ``custom``) give an empty dict.
    """
    preset = PLANT_LIBRARY.get(preset_key)
    if preset is None:
        return {}
    tasks: dict[str, dict] = {}
    for task, (months, interval) in preset.tasks.items():
        entry: dict = {
            CONF_MONTHS: shift_months(months, hemisphere),
            CONF_INTERVAL_DAYS: interval,
        }
        if task == TASK_CUSTOM:
            entry[CONF_CUSTOM_TASK_NAME] = preset.custom_task_name
        tasks[task] = entry
    return tasks
