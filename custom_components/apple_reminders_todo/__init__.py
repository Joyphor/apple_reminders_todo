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

def _read_json_file(path: str) -> dict:
    """Read JSON file and return parsed data."""
    with open(path, "r") as f:
        return json.load(f)

def generate_stable_uid(reminder: dict) -> str:
    """Generate a stable, unique ID for a reminder."""
    # Get title and creation time with fallbacks
    title = reminder.get('title', '')
    creation_time = reminder.get('creationDateTime', '')
    
    # Combine to create a unique identifier
    uid_base = f"{title}_{creation_time}"
    
    return hashlib.md5(uid_base.encode()).hexdigest()


def create_rich_description(reminder: dict) -> str:
    """Create a rich description including all reminder metadata."""
    # Format tags if present
    tags_text = ""
    if reminder.get('tags') and len(reminder['tags']) > 0:
        tags_text = f"Tags: {', '.join(reminder['tags'])}"
    
    # Build the description with all available metadata
    description_parts = [
        f"Priority: {reminder.get('priority')}" if reminder.get('priority') and reminder.get('priority') != "None" else "",
        f"Flagged: Yes" if reminder.get('isFlagged') else "",
        tags_text,
        f"List: {reminder.get('list')}" if reminder.get('list') else "",
        f"Created: {reminder.get('creationDateTime')}" if reminder.get('creationDateTime') else ""
    ]
    
    # Filter out empty parts and join with line breaks
    return "\n".join([part for part in description_parts if part])


async def update_todos_from_json(hass: HomeAssistant, path: str, todo_entity_id: str, last_timestamp=None) -> str:
    """Update Home Assistant todos from JSON file. Returns the new timestamp."""
    try:
        # Check file existence in an executor
        file_exists = await hass.async_add_executor_job(os.path.exists, path)
        if not file_exists:
            _LOGGER.warning("JSON file not found: %s", path)
            return last_timestamp

        # Read the JSON file in an executor
        json_data = await hass.async_add_executor_job(_read_json_file, path)
            
        # Get the timestamp from the JSON
        json_timestamp = json_data.get("timestamp")
        
        # Only process if timestamp has changed
        if last_timestamp is not None and json_timestamp == last_timestamp:
            _LOGGER.debug("JSON data hasn't changed since last update (timestamp: %s), skipping", json_timestamp)
            return last_timestamp
        
        _LOGGER.info("JSON data has changed (old timestamp: %s, new timestamp: %s), updating todos", 
                    last_timestamp, json_timestamp)
        
        # Get reminders from the proper JSON structure
        reminders = json_data.get("items", [])
        
        # Get the todo component
        todo_component = hass.data.get("todo", {})
        todo_entity = todo_component.get_entity(todo_entity_id)
        
        if not todo_entity:
            _LOGGER.error("Todo entity not found: %s", todo_entity_id)
            return json_timestamp  # Still return the timestamp so we don't reprocess
        
        # Get existing todos
        existing_todos = todo_entity.todo_items or []
        
        # Delete all existing items in one operation
        if existing_todos:
            try:
                uids_to_remove = [item.uid for item in existing_todos if item.uid]
                if uids_to_remove:
                    _LOGGER.debug("Removing all %d existing items", len(uids_to_remove))
                    await todo_entity.async_delete_todo_items(uids=uids_to_remove)
                    _LOGGER.debug("Successfully removed all existing items")
            except Exception as del_err:
                _LOGGER.warning("Error during bulk deletion: %s", del_err)
        
        # Add new items from JSON
        added_count = 0
        for reminder in reminders:
            try:
                item = TodoItem(
                    uid=generate_stable_uid(reminder),
                    summary=reminder.get('title', ''),
                    status=TodoItemStatus.COMPLETED if reminder.get('isCompleted') else TodoItemStatus.NEEDS_ACTION,
                    description=create_rich_description(reminder),
                )
                
                # Add due date if available
                due_date_str = reminder.get('dueDateTime')
                if due_date_str:
                    try:
                        due_date = dt_util.parse_datetime(due_date_str)
                        if due_date:
                            # Convert to the local timezone that Home Assistant uses
                            # This is crucial for compatibility with iCal
                            due_date = dt_util.as_local(due_date)
                            item.due = due_date
                            _LOGGER.debug("Processed due date %s as %s", due_date_str, due_date)
                        else:
                            _LOGGER.warning("Could not parse due date: %s", due_date_str)
                    except (ValueError, TypeError) as err:
                        _LOGGER.warning("Failed to parse due date %s: %s", due_date_str, err)
                
                # Create new item
                await todo_entity.async_create_todo_item(item=item)
                added_count += 1
                    
            except Exception as item_err:
                _LOGGER.error("Error creating todo item for %s: %s", reminder.get('title'), item_err)
        
        _LOGGER.info("Todo list update complete: removed %d existing items, added %d new items", 
                    len(existing_todos), added_count)
        
        return json_timestamp
        
    except Exception as ex:
        _LOGGER.error("Error updating todos: %s", ex)
        return last_timestamp

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Apple Reminders Todo from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    path = entry.data[CONF_PATH]
    todo_entity_id = entry.data[CONF_TODO_LIST]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    # Data storage for this entry
    entry_data = {
        "last_timestamp": None
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data
    
    # Create service to manually trigger update
    async def handle_update_service(call: ServiceCall) -> None:
        """Handle the service call."""
        force_update = call.data.get("force", False)
        timestamp_to_use = None if force_update else entry_data["last_timestamp"]
        
        entry_data["last_timestamp"] = await update_todos_from_json(
            hass, path, todo_entity_id, timestamp_to_use
        )
    
    hass.services.async_register(
        DOMAIN, 
        "update_todos", 
        handle_update_service,
        vol.Schema({
            vol.Optional("force"): cv.boolean,
        })
    )
    
    # Set up periodic updates with proper threading approach
    def _handle_interval(now):
        """Handle interval timer callback."""
        async def _update_with_timestamp():
            entry_data["last_timestamp"] = await update_todos_from_json(
                hass, path, todo_entity_id, entry_data["last_timestamp"]
            )
        hass.add_job(_update_with_timestamp)
    
    # Store the remove callback function so we can clean up on unload
    entry.async_on_unload(
        async_track_time_interval(
            hass, 
            _handle_interval,
            timedelta(seconds=scan_interval)
        )
    )
    
    # Initial update
    entry_data["last_timestamp"] = await update_todos_from_json(
        hass, path, todo_entity_id, None  # Force first update
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Note: We don't need to manually remove the time interval listener
    # since we used entry.async_on_unload when setting it up
    
    # Remove the service
    hass.services.async_remove(DOMAIN, "update_todos")
    
    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Apple Reminders Todo component from yaml configuration."""
    if DOMAIN not in config:
        return True
        
    path = config[DOMAIN][CONF_PATH]
    todo_entity_id = config[DOMAIN][CONF_TODO_LIST]
    scan_interval = config[DOMAIN].get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    # Data storage
    component_data = {
        "last_timestamp": None
    }
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = component_data
    
    # Create service to manually trigger update
    async def handle_update_service(call: ServiceCall) -> None:
        """Handle the service call."""
        force_update = call.data.get("force", False)
        timestamp_to_use = None if force_update else component_data["last_timestamp"]
        
        component_data["last_timestamp"] = await update_todos_from_json(
            hass, path, todo_entity_id, timestamp_to_use
        )
    
    hass.services.async_register(
        DOMAIN, 
        "update_todos", 
        handle_update_service,
        vol.Schema({
            vol.Optional("force"): cv.boolean,
        })
    )
    
    # Set up periodic updates with proper threading approach
    def _handle_interval(now):
        """Handle interval timer callback."""
        async def _update_with_timestamp():
            component_data["last_timestamp"] = await update_todos_from_json(
                hass, path, todo_entity_id, component_data["last_timestamp"]
            )
        hass.add_job(_update_with_timestamp)
    
    async_track_time_interval(
        hass, 
        _handle_interval,
        timedelta(seconds=scan_interval)
    )
    
    # Initial update
    component_data["last_timestamp"] = await update_todos_from_json(
        hass, path, todo_entity_id, None  # Force first update
    )
    
    return True