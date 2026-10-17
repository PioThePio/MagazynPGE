"""Native UI setup: select the existing sensor; never modify it."""

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_MAX_AGE_HOURS, DOMAIN
from .history import sample_from_state
from .ledger import LedgerError, energy


def age_field(default: int):
    return {
        vol.Required("max_age_hours", default=default): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=168, step=1, mode=selector.NumberSelectorMode.BOX
            )
        )
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            sources = {
                "import": user_input["import_entity_id"],
                "export": user_input["export_entity_id"],
            }
            for direction, entity_id in sources.items():
                try:
                    sample = sample_from_state(self.hass.states.get(entity_id))
                    if energy(sample.value) < 0:
                        raise LedgerError(
                            "invalid_source", "Licznik musi być nieujemny."
                        )
                except LedgerError:
                    errors[f"{direction}_entity_id"] = "invalid_source"
            if sources["import"] == sources["export"]:
                errors["base"] = "same_source"
            if not errors:
                await self.async_set_unique_id(
                    f"{sources['import']}|{sources['export']}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Magazyn PGE",
                    data={"sources": sources},
                    options={"max_age_hours": int(user_input["max_age_hours"])},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("import_entity_id"): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required("export_entity_id"): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    **age_field(DEFAULT_MAX_AGE_HOURS),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="", data={"max_age_hours": int(user_input["max_age_hours"])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                age_field(
                    self.config_entry.options.get(
                        "max_age_hours", DEFAULT_MAX_AGE_HOURS
                    )
                )
            ),
        )
