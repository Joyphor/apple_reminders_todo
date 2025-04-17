# Apple Reminders Todo Integration for Home Assistant

This integration allows you to import your Apple Reminders into Home Assistant's local Todo lists. 

!!! This integration is vibe coded with AI and I have no idea what I'm doing !!!

## Features

- Imports reminders from a JSON file exported by Apple Shortcuts
- Preserves completion status, due dates, tags, and other metadata
- Updates todo lists automatically when the JSON file changes
- Supports multiple todo lists

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Add this repository to HACS as a custom repository:
   - Navigate to HACS > Integrations > ⋮ > Custom repositories
   - Add `https://github.com/Joyphor/apple_reminders_todo` with category "Integration"
3. Search for "Apple Reminders Todo" in HACS and install it
4. Restart Home Assistant

### Manual Installation

1. Download the latest release from this repository
2. Copy the `custom_components/apple_reminders_todo` directory to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

Add the following to your `configuration.yaml`:

```yaml
apple_reminders_todo:
  path: /config/todo_data.json  # Path to your JSON file
  todo_list: todo.local_todo    # Your local todo entity ID
  scan_interval: 300            # Check for updates every 5 minutes (optional)
```

## JSON Format

Your JSON file should have the following structure:

```json
{
  "items": [
    {
      "title": "Reminder title",
      "creationDateTime": "2025-03-15T18:09:30+01:00",
      "data": {
        "dueDateTime": "2025-03-22T00:00:00+01:00",
        "isFlagged": true,
        "isCompleted": false,
        "list": "Inbox",
        "priority": "Medium",
        "tags": ["Personal"],
        "name": "Reminder title"
      }
    }
  ],
  "timestamp": "2025-03-15T18:13:39+01:00"
}
```

## Apple Shortcuts Setup

- Create a shortcut in Apple Shortcuts.app
- Add actions to get desired reminders
- Format the data to match the JSON structure above
- Save the JSON to a file accessible by Home Assistant
- Schedule the shortcut to run regularly

## Services

This integration provides the following service:

apple_reminders_todo.update_todos: Manually triggers an update from the JSON file

## Troubleshooting

Check the Home Assistant logs for any errors related to the integration.
