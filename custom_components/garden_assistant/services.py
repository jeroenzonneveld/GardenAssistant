"""Services for Garden Assistant."""

from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.service import async_extract_referenced_entity_ids

from .const import (
    ATTR_DATE,
    ATTR_DAYS,
    DOMAIN,
    SERVICE_COMPLETE_TASK,
    SERVICE_SNOOZE_TASK,
    TASK_TYPES,
)
from .coordinator import GardenCoordinator

COMPLETE_TASK_SCHEMA = cv.make_entity_service_schema({vol.Optional(ATTR_DATE): cv.date})
SNOOZE_TASK_SCHEMA = cv.make_entity_service_schema(
    {vol.Optional(ATTR_DAYS, default=7): vol.All(vol.Coerce(int), vol.Range(1, 365))}
)

_SUFFIXES = ("_due", "_done")


def _parse_unique_id(unique_id: str) -> tuple[str, str] | None:
    """Return (subentry_id, task) for a task entity unique id, else None."""
    for suffix in _SUFFIXES:
        if unique_id.endswith(suffix):
            stem = unique_id.removesuffix(suffix)
            subentry_id, sep, task = stem.rpartition("_")
            if sep and subentry_id and task in TASK_TYPES:
                return subentry_id, task
    return None


def _resolve_targets(
    hass: HomeAssistant, call: ServiceCall
) -> list[tuple[GardenCoordinator, str, str]]:
    """Resolve the targeted entities to (coordinator, subentry_id, task)."""
    selected = async_extract_referenced_entity_ids(hass, call)
    # Explicitly targeted entities must be task entities of this integration.
    # Entities only reached through a device/area/label target are skipped
    # silently when they are not (e.g. the next-task sensor of a plant device).
    explicit = set(selected.referenced)
    entity_ids = sorted(explicit | selected.indirectly_referenced)
    if not entity_ids:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entities"
        )

    registry = er.async_get(hass)
    result: list[tuple[GardenCoordinator, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entity_id in entity_ids:
        reg_entry = registry.async_get(entity_id)
        if entity_id not in explicit and (
            reg_entry is None
            or reg_entry.platform != DOMAIN
            or _parse_unique_id(reg_entry.unique_id) is None
        ):
            continue
        if reg_entry is None or reg_entry.platform != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_garden_entity",
                translation_placeholders={"entity_id": entity_id},
            )
        parsed = _parse_unique_id(reg_entry.unique_id)
        if parsed is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_task_entity",
                translation_placeholders={"entity_id": entity_id},
            )
        entry = (
            hass.config_entries.async_get_entry(reg_entry.config_entry_id)
            if reg_entry.config_entry_id
            else None
        )
        coordinator = getattr(entry, "runtime_data", None) if entry else None
        if (
            entry is None
            or entry.state is not ConfigEntryState.LOADED
            or not isinstance(coordinator, GardenCoordinator)
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"entity_id": entity_id},
            )
        subentry_id, task = parsed
        key = (entry.entry_id, subentry_id, task)
        if key in seen:
            continue
        seen.add(key)
        result.append((coordinator, subentry_id, task))
    if not result:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entities"
        )
    return result


async def _async_complete_task(hass: HomeAssistant, call: ServiceCall) -> None:
    when: date | None = call.data.get(ATTR_DATE)
    for coordinator, subentry_id, task in _resolve_targets(hass, call):
        await coordinator.async_complete_task(subentry_id, task, when)


async def _async_snooze_task(hass: HomeAssistant, call: ServiceCall) -> None:
    days: int = call.data[ATTR_DAYS]
    for coordinator, subentry_id, task in _resolve_targets(hass, call):
        await coordinator.async_snooze_task(subentry_id, task, days)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""

    async def complete_task(call: ServiceCall) -> None:
        await _async_complete_task(hass, call)

    async def snooze_task(call: ServiceCall) -> None:
        await _async_snooze_task(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE_TASK, complete_task, schema=COMPLETE_TASK_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SNOOZE_TASK, snooze_task, schema=SNOOZE_TASK_SCHEMA
    )
