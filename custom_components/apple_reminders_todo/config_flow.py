"""Config flow for Apple Reminders Todo integration."""
from __future__ import annotations

import os
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_PATH, CONF_TODO_LIST, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    # Validate the path
    if not os.path.exists(data[CONF_PATH]):
        raise InvalidPath

    # Validate the todo entity
    todo_component = hass.data.get("todo", {})
    if not todo_component.get_entity(data[CONF_TODO_LIST]):
        raise EntityNotFound

    # Return validated data
    return {"title": f"Apple Reminders to {data[CONF_TODO_LIST]}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Apple Reminders Todo."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )
            except InvalidPath:
                errors["path"] = "invalid_path"
            except EntityNotFound:
                errors["todo_list"] = "entity_not_found"
            except Exception:
                errors["base"] = "unknown"

        # Provide defaults
        data_schema = vol.Schema(
            {
                vol.Required(CONF_PATH): str,
                vol.Required(CONF_TODO_LIST): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


class InvalidPath(HomeAssistantError):
    """Error to indicate the path is invalid."""


class EntityNotFound(HomeAssistantError):
    """Error to indicate the entity was not found."""