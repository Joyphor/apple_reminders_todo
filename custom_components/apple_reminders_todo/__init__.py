"""Apple Reminders integration for Home Assistant Todo lists."""
from __future__ import annotations

import json
import logging
import os
import hashlib
import voluptuous as vol

from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
from datetime import timedelta

from .const import (
    DOMAIN,
    CONF_PATH,
    CONF_TODO_LIST,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_PATH): cv.string,
                vol.Required(CONF_TODO_LIST): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.Coerce(int),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def generate_stable_uid(reminder: dict) -> str:
    """Generate a stable, unique ID for a reminder."""
    # Combine title and creation time for uniqueness
    uid_base = f"{reminder['title']}_{reminder['creationDateTime']}"
    return hashlib.md5(uid_base.encode()).hexdigest()


def create_rich_description(reminder: dict) -> str:
    """Create a rich description including all reminder metadata."""
    data = reminder['data']
    
    # Format tags if present
    tags_text = ""
    if data.get('tags') and len(data['tags']) > 0:
        tags_text = f"Tags: {', '.join(data['tags'])}"
    
    # Build the description with all available metadata
    description_parts = [
        f"Priority: {data.get('priority')}" if data.get('priority') and data.get('priority') != "None" else "",
        f"Flagged: Yes" if data.get('isFlagged') else "",
        tags_text,
        f"List: {data.get('list')}" if data.get('list') else "",
        f"Created: {reminder.get('creationDateTime')}" if reminder.get('creationDateTime') else ""
    ]
    
    # Filter out empty parts and join with line breaks
    return "\n".join([part for part in description_parts if part])


async def update_todos_from_json(hass: HomeAssistant, path: str, todo_entity_id: str) -> None:
    """Update Home Assistant todos from JSON file."""
    try:
        if not os.path.exists(path):
            _LOGGER.warning("JSON file not found: %s", path)
            return

        # Read the JSON file
        with open(path, "r") as f:
            json_data = json.load(f)
            
        # Get reminders from the proper JSON structure
        reminders = json_data.get("items", [])
        
        # Get the todo component
        todo_component = hass.data.get("todo", {})
        todo_entity = todo_component.get_entity(todo_entity_id)
        
        if not todo_entity:
            _LOGGER.error("Todo entity not found: %s", todo_entity_id)
            return
            
        # Clear existing todos first
        existing_todos = todo_entity.todo_items
        if existing_todos:
            uids_to_remove = [item.uid for item in existing_todos if item.uid]
            if uids_to_remove:
                await todo_entity.async_delete_todo_items(uids=uids_to_remove)
        
        # Add new todos from JSON
        for reminder in reminders:
            # Create the todo item with all the additional information
            try:
                item = TodoItem(
                    uid=generate_stable_uid(reminder),
                    summary=reminder.get('title', ''),
                    status=TodoItemStatus.COMPLETED if reminder.get('data', {}).get('isCompleted') else TodoItemStatus.NEEDS_ACTION,
                    description=create_rich_description(reminder),
                )
                
                # Add due date if available
                due_date_str = reminder.get('data', {}).get('dueDateTime')
                if due_date_str:
                    try:
                        due_date = dt_util.parse_datetime(due_date_str)
                        if due_date:
                            item.due = due_date
                    except (ValueError, TypeError) as err:
                        _LOGGER.warning("Failed to parse due date %s: %s", due_date_str, err)
                        
                await todo_entity.async_create_todo_item(item=item)
            except Exception as item_err:
                _LOGGER.error("Error creating todo item for %s: %s", reminder.get('title'), item_err)
            
        _LOGGER.info("Successfully updated %d todos from %s", len(reminders), path)
        
    except Exception as ex:
        _LOGGER.error("Error updating todos: %s", ex)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Apple Reminders Todo from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    path = entry.data[CONF_PATH]
    todo_entity_id = entry.data[CONF_TODO_LIST]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    # Create service to manually trigger update
    async def handle_update_service(call: ServiceCall) -> None:
        """Handle the service call."""
        await update_todos_from_json(hass, path, todo_entity_id)
    
    hass.services.async_register(DOMAIN, "update_todos", handle_update_service)
    
    # Set up periodic updates
    async_track_time_interval(
        hass, 
        lambda now: hass.async_create_task(update_todos_from_json(hass, path, todo_entity_id)), 
        timedelta(seconds=scan_interval)
    )
    
    # Initial update
    await update_todos_from_json(hass, path, todo_entity_id)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Remove the update interval
    # The service will be removed automatically
    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Apple Reminders Todo component from yaml configuration."""
    if DOMAIN not in config:
        return True
        
    path = config[DOMAIN][CONF_PATH]
    todo_entity_id = config[DOMAIN][CONF_TODO_LIST]
    scan_interval = config[DOMAIN].get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    # Create service to manually trigger update
    async def handle_update_service(call: ServiceCall) -> None:
        """Handle the service call."""
        await update_todos_from_json(hass, path, todo_entity_id)
    
    hass.services.async_register(DOMAIN, "update_todos", handle_update_service)
    
    # Set up periodic updates
    async_track_time_interval(
        hass, 
        lambda now: hass.async_create_task(update_todos_from_json(hass, path, todo_entity_id)), 
        timedelta(seconds=scan_interval)
    )
    
    # Initial update
    await update_todos_from_json(hass, path, todo_entity_id)
    
    return True