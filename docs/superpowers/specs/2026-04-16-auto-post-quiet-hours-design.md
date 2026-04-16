# Auto-Post Quiet Hours Design

## Overview

Add a quiet hours feature to prevent scheduled auto-posting during nighttime hours.

## Configuration

New env vars in `config.py`:

```env
AUTO_POST_QUIET_HOURS_START=23  # 0-23, default empty (disabled)
AUTO_POST_QUIET_HOURS_END=6     # 0-23, default empty (disabled)
```

## Logic

- If either var is empty or `START == END`, quiet hours are disabled (posts always allowed)
- If both set with different values, check current UTC hour against the range
- Overnight ranges (e.g., 23-6) wrap past midnight correctly

## Files Changed

| File | Change |
|------|--------|
| `config.py` | Add `AUTO_POST_QUIET_HOURS_START`, `AUTO_POST_QUIET_HOURS_END` with int parsing |
| `module/auto_post/__init__.py` | Add `is_quiet_hours()` helper, skip `post_scheduled()` when active |
| `.env.example` | Document new vars |

## Implementation

1. Add config vars with default `None`, parse with `int(os.getenv(...))` or `None`
2. `is_quiet_hours()` helper:
   ```python
   def is_quiet_hours() -> bool:
       start = config.AUTO_POST_QUIET_HOURS_START
       end = config.AUTO_POST_QUIET_HOURS_END
       if start is None or end is None or start == end:
           return False
       current_hour = datetime.utcnow().hour
       if start < end:
           return start <= current_hour < end
       return current_hour >= start or current_hour < end
   ```
3. Call `is_quiet_hours()` at start of `ScheduledPoster.post_scheduled()`, return early if True
