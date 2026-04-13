# Module Pattern Guide

## Structure

```
module/
  <module_name>/
    __init__.py        # re-exports
    <component>.py    # one class per file
```

## Pattern

### 1. Component file (`<component>.py`)

```python
import logging
import config

logger = logging.getLogger(__name__)


class ComponentName:
    def __init__(self):
        pass


_component_name = None


def get_component_name() -> ComponentName:
    global _component_name
    if _component_name is None:
        _component_name = ComponentName()
    return _component_name
```

### 2. `__init__.py`

```python
from .<component> import ComponentName, get_component_name>

__all__ = ["ComponentName", "get_component_name"]
```

### 3. Integration in bot.py

```python
from module.<module_name> import get_component_name

# Use
component = get_component_name()
```

## Key Principles

1. **Singleton pattern** - Use global `get_*` function to return single instance
2. **One class per file** - Keeps files focused and testable
3. **Re-export in `__init__.py`** - Clean public API
4. **Use config.py** - Configuration stays in main config
5. **Logger per module** - `logger = logging.getLogger(__name__)`