# A-Cal Example Plugins

These plugins demonstrate the A-Cal plugin system. Each file is a standalone
Python module with a `Plugin` class that implements one or more hooks.

## Installing

Copy any `.py` file to your plugin directory:

```bash
mkdir -p ~/.a-cal/plugins
cp plugins/examples/*.py ~/.a-cal/plugins/
```

Then open A-Cal in Developer mode and click "Scan Directory" in the Runtime
Plugins section, or call the API:

```bash
curl -X POST http://localhost:8000/api/a-cal/developer/plugins/runtime/scan
```

## Available Examples

| Plugin | Type | Hooks | What it does |
|--------|------|-------|-------------|
| `event_tagger.py` | agent | `on_event_created` | Tags events with category metadata based on title keywords |
| `conflict_notifier.py` | agent | `on_event_created` | Logs warnings for high-priority event creation |
| `response_enhancer.py` | agent | `on_conductor_response` | Adds a quick-actions footer to conductor responses |
| `custom_agent.py` | agent | `get_agent_spec`, `on_event_created` | Registers a custom project tracker agent spec + tags project events |
| `sync_rules_pack.py` | sync_rule | `get_sync_rules` | Provides work-life balance sync rules (no work after hours/weekends) |

## Writing Your Own Plugin

Create a `.py` file with a `Plugin` class:

```python
class Plugin:
    name = "My Plugin"
    plugin_type = "agent"  # or "sync_rule", "provider", "ui_component"
    enabled = True

    def on_event_created(self, event):
        """Called when a new event is created. Return modified event or None."""
        return None

    def on_conductor_response(self, response, context):
        """Transform the conductor's response. Return new string or None."""
        return None
```

### Supported Hooks

| Hook | When it fires | Return value |
|------|--------------|-------------|
| `on_event_created(event)` | After an event is created | Modified event dict or None |
| `on_event_updated(event)` | After an event is updated | Modified event dict or None |
| `on_event_deleted(event_id)` | After an event is deleted | None |
| `on_sync_complete(sub_account_id, events)` | After a provider sync finishes | None |
| `on_intent_classified(message, intent)` | After conductor classifies intent | Override intent string or None |
| `on_conductor_response(response, context)` | Before conductor returns response | Transformed response string or None |
| `get_agent_spec()` | When loading agent specs | Agent spec dict or list of dicts |
| `get_sync_rules()` | When loading sync rules | Sync rule dict or list of dicts |

### Safety

- Plugin errors are caught and logged — they never crash the host
- Plugins run in the same process (sandboxing is a future concern)
- Disable a plugin from the UI or API without removing the file
