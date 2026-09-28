"""Config flow for Garden Assistant."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTIONABLE,
    CONF_CREATED,
    CONF_CUSTOM_TASK_NAME,
    CONF_HEMISPHERE,
    CONF_INTERVAL_DAYS,
    CONF_LEAD_DAYS,
    CONF_LOCATION,
    CONF_MONTHS,
    CONF_NAME,
    CONF_NOTES,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_PERSISTENT,
    CONF_NOTIFY_SERVICES,
    CONF_NOTIFY_TIME,
    CONF_PRESET,
    CONF_REPEAT_DAILY,
    CONF_SPECIES,
    CONF_TASKS,
    DEFAULT_OPTIONS,
    DOMAIN,
    HEMISPHERE_NORTH,
    HEMISPHERE_SOUTH,
    PRESET_CUSTOM,
    SUBENTRY_TYPE_PLANT,
    TASK_CUSTOM,
    TASK_TYPES,
)
from .plant_library import PLANT_LIBRARY, preset_tasks

# Notify services that are not "send to a target" services.
_IGNORED_NOTIFY_SERVICES = {"send_message", "persistent_notification"}


def _hemisphere_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[HEMISPHERE_NORTH, HEMISPHERE_SOUTH],
            translation_key="hemisphere",
            mode=SelectSelectorMode.LIST,
        )
    )


def _months_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[str(m) for m in range(1, 13)],
            multiple=True,
            translation_key="month",
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _number_selector(maximum: int, unit: str = "days") -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=maximum,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _notify_service_options(
    hass: HomeAssistant, current: list[str]
) -> list[SelectOptionDict]:
    """Return the available notify services (plus already configured ones)."""
    values = {
        f"notify.{name}"
        for name in hass.services.async_services_for_domain("notify")
        if name not in _IGNORED_NOTIFY_SERVICES
    }
    values.update(current)
    return [SelectOptionDict(value=v, label=v) for v in sorted(values)]


class GardenAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Garden Assistant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the hemisphere and create the garden."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Garden",
                data={},
                options={**DEFAULT_OPTIONS, **user_input},
            )

        default = (
            HEMISPHERE_SOUTH if self.hass.config.latitude < 0 else HEMISPHERE_NORTH
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_HEMISPHERE, default=default): _hemisphere_selector()}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return GardenOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the supported subentry types."""
        return {SUBENTRY_TYPE_PLANT: PlantSubentryFlowHandler}


class GardenOptionsFlow(OptionsFlow):
    """Global garden settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            user_input = dict(user_input)
            user_input[CONF_LEAD_DAYS] = int(user_input.get(CONF_LEAD_DAYS, 0))
            return self.async_create_entry(data={**DEFAULT_OPTIONS, **user_input})

        opts = {**DEFAULT_OPTIONS, **self.config_entry.options}
        services = list(opts[CONF_NOTIFY_SERVICES])
        schema = vol.Schema(
            {
                vol.Required(CONF_HEMISPHERE): _hemisphere_selector(),
                vol.Required(CONF_NOTIFY_ENABLED): BooleanSelector(),
                vol.Optional(CONF_NOTIFY_SERVICES): SelectSelector(
                    SelectSelectorConfig(
                        options=_notify_service_options(self.hass, services),
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_NOTIFY_PERSISTENT): BooleanSelector(),
                vol.Required(CONF_NOTIFY_TIME): TimeSelector(),
                vol.Required(CONF_LEAD_DAYS): _number_selector(30),
                vol.Required(CONF_REPEAT_DAILY): BooleanSelector(),
                vol.Required(CONF_ACTIONABLE): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, opts),
        )


class PlantSubentryFlowHandler(ConfigSubentryFlow):
    """Add or reconfigure a plant."""

    def __init__(self) -> None:
        """Initialise the flow."""
        super().__init__()
        self._basic: dict[str, Any] = {}

    @property
    def _is_new(self) -> bool:
        return self.source == "user"

    @property
    def _hemisphere(self) -> str:
        return self._get_entry().options.get(CONF_HEMISPHERE, HEMISPHERE_NORTH)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Plant basics (new plant)."""
        return await self._async_basic_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Plant basics (existing plant)."""
        return await self._async_basic_step("reconfigure", user_input)

    async def _async_basic_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input.get(CONF_NAME, "")).strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                self._basic = {
                    CONF_NAME: name,
                    CONF_PRESET: user_input[CONF_PRESET],
                    CONF_SPECIES: str(user_input.get(CONF_SPECIES, "")).strip(),
                    CONF_LOCATION: str(user_input.get(CONF_LOCATION, "")).strip(),
                    CONF_NOTES: str(user_input.get(CONF_NOTES, "")).strip(),
                }
                return await self.async_step_schedule()

        if user_input is not None:
            defaults: dict[str, Any] = user_input
        elif self._is_new:
            defaults = {CONF_PRESET: PRESET_CUSTOM}
        else:
            defaults = dict(self._get_reconfigure_subentry().data)

        preset_options = [
            SelectOptionDict(value=key, label=preset.label)
            for key, preset in sorted(
                PLANT_LIBRARY.items(), key=lambda item: item[1].label.casefold()
            )
        ]
        preset_options.append(
            SelectOptionDict(value=PRESET_CUSTOM, label="Custom (start empty)")
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
                vol.Required(CONF_PRESET): SelectSelector(
                    SelectSelectorConfig(
                        options=preset_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(CONF_SPECIES): TextSelector(),
                vol.Optional(CONF_LOCATION): TextSelector(),
                vol.Optional(CONF_NOTES): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
                ),
            }
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, defaults),
            errors=errors,
        )

    def _schedule_defaults(self) -> dict[str, Any]:
        """Return the prefilled task configuration for the schedule step."""
        preset = self._basic[CONF_PRESET]
        tasks: dict[str, dict[str, Any]]
        if not self._is_new:
            current = self._get_reconfigure_subentry().data
            if current.get(CONF_PRESET) == preset:
                tasks = dict(current.get(CONF_TASKS, {}))
            else:
                tasks = preset_tasks(preset, self._hemisphere)
        else:
            tasks = preset_tasks(preset, self._hemisphere)

        values: dict[str, Any] = {}
        for task in TASK_TYPES:
            conf = tasks.get(task, {})
            values[f"{task}_{CONF_MONTHS}"] = [
                str(m) for m in conf.get(CONF_MONTHS, [])
            ]
            values[f"{task}_interval"] = int(conf.get(CONF_INTERVAL_DAYS, 0) or 0)
        values[CONF_CUSTOM_TASK_NAME] = tasks.get(TASK_CUSTOM, {}).get(
            CONF_CUSTOM_TASK_NAME, ""
        )
        return values

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Per task schedule."""
        errors: dict[str, str] = {}
        if user_input is not None:
            tasks: dict[str, dict[str, Any]] = {}
            for task in TASK_TYPES:
                months = sorted(
                    int(m) for m in user_input.get(f"{task}_{CONF_MONTHS}") or []
                )
                interval = int(user_input.get(f"{task}_interval") or 0)
                if not months and interval <= 0:
                    continue
                conf: dict[str, Any] = {
                    CONF_MONTHS: months,
                    CONF_INTERVAL_DAYS: interval,
                }
                if task == TASK_CUSTOM:
                    custom_name = str(user_input.get(CONF_CUSTOM_TASK_NAME, "")).strip()
                    if not custom_name:
                        errors[CONF_CUSTOM_TASK_NAME] = "custom_task_name_required"
                    conf[CONF_CUSTOM_TASK_NAME] = custom_name
                tasks[task] = conf

            if not errors:
                data = {
                    **self._basic,
                    CONF_CREATED: dt_util.now().date().isoformat(),
                    CONF_TASKS: tasks,
                }
                if self._is_new:
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
                subentry = self._get_reconfigure_subentry()
                data[CONF_CREATED] = (
                    subentry.data.get(CONF_CREATED) or data[CONF_CREATED]
                )
                return self.async_update_and_abort(
                    self._get_entry(), subentry, title=data[CONF_NAME], data=data
                )

        fields: dict[Any, Any] = {}
        for task in TASK_TYPES:
            if task == TASK_CUSTOM:
                fields[vol.Optional(CONF_CUSTOM_TASK_NAME)] = TextSelector()
            fields[vol.Optional(f"{task}_{CONF_MONTHS}")] = _months_selector()
            fields[vol.Optional(f"{task}_interval")] = _number_selector(365)

        defaults = user_input if user_input is not None else self._schedule_defaults()
        return self.async_show_form(
            step_id="schedule",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(fields), defaults
            ),
            errors=errors,
        )
