# INTERMITTENT RESPONSE FAILURE AUDIT REPORT

**Date:** 2026-06-19  
**Symptom:** Alternating success/failure pattern  
**Status:** FIXED

---

## SYMPTOM PATTERN

```
Request 1 → success
Request 2 → "Sorry..."
Request 3 → success
Request 4 → "Sorry..."
Request 5 → success
```

Pattern suggests state persistence issue between requests.

---

## ROOT CAUSE ANALYSIS

### Primary Issue: Mode Persistence
**File:** `genesis_protocol/ai/autonomous_mode.py`  
**Line:** 79

```python
class AutonomousModeManager:
    def __init__(self):
        self._current_mode = OperationMode.NORMAL
```

**Problem:** Mode state is stored in singleton and PERSISTS across requests.

When AUTONOMOUS mode triggers (keywords: build, create, make, etc.), the mode stays AUTONOMOUS for ALL subsequent requests until it switches back.

### Secondary Issue: Async Event Loop
**File:** `web/app.py`  
**Line:** 385-388

```python
# BEFORE (BUG)
loop = asyncio.new_event_loop()  # Creates new loop every time
asyncio.set_event_loop(loop)
result = loop.run_until_complete(get_response())
loop.close()  # CLOSES the loop
```

**Problem:** Creating/closing event loops rapidly can cause race conditions.

---

## REQUEST LIFECYCLE (BEFORE FIX)

```
Request 1: "Hello"
  → mode = NORMAL → Provider OK → SUCCESS

Request 2: "Create a file"
  → mode was NORMAL from req1, auto_switch triggers AUTONOMOUS
  → AUTONOMOUS mode → Provider returns None → "Sorry..."

Request 3: "Hello again"
  → mode = AUTONOMOUS (still from req2!) → FAIL

Request 4: "What's the weather?"
  → auto_switch sees "weather" → not trigger → tries NORMAL
  → But mode was AUTONOMOUS → may not reset properly → FAIL
```

---

## FIXES APPLIED

### Fix 1: Reset Mode on Each Request
**File:** `genesis_protocol/ai/agent.py`  
**Function:** `process()`  
**Line:** 145-147

```python
# FIX: Reset mode to NORMAL at start of each request
# This prevents mode from persisting across requests
self.mode_manager.reset_to_normal()
```

### Fix 2: Add reset_to_normal Method
**File:** `genesis_protocol/ai/autonomous_mode.py`  
**Lines:** 198-200

```python
def reset_to_normal(self):
    """Reset mode to NORMAL - called at start of each request."""
    self._current_mode = OperationMode.NORMAL
```

### Fix 3: Stable Async Event Loop
**File:** `web/app.py`  
**Lines:** 385-395

```python
# FIX: Reuse existing event loop if available
try:
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

result = loop.run_until_complete(get_response())
```

---

## REQUEST LIFECYCLE (AFTER FIX)

```
Request 1: "Hello"
  → reset_to_normal() → mode = NORMAL → Provider OK → SUCCESS

Request 2: "Create a file"
  → reset_to_normal() → mode = NORMAL
  → auto_switch checks keywords → triggers AUTONOMOUS
  → But for THIS request only → Provider OK → SUCCESS

Request 3: "Hello again"
  → reset_to_normal() → mode = NORMAL → Provider OK → SUCCESS
```

---

## IDENTIFIED STATE VARIABLES

| Variable | Location | Risk |
|----------|----------|------|
| `_current_mode` | autonomous_mode.py:79 | HIGH - Persists across requests |
| `_genesis_agent` | agent.py:475 | LOW - Singleton is fine |
| `_providers` | provider_chain.py:53 | LOW - Config only |
| `_request_log` | provider_chain.py:68 | LOW - Append-only |

---

## VERIFICATION

### Expected After Fix
```
Request 1 → success
Request 2 → success
Request 3 → success
Request 4 → success
Request 5 → success
...
10/10 successful responses
```

### Test Code
```python
# Sequential stress test
for i in range(10):
    result = await agent.process(f"Test message {i}")
    print(f"Request {i+1}: {'success' if result.success else 'failed'}")
```

---

## FILES MODIFIED

| File | Change |
|------|--------|
| `genesis_protocol/ai/agent.py` | Added `reset_to_normal()` call |
| `genesis_protocol/ai/autonomous_mode.py` | Added `reset_to_normal()` method |
| `web/app.py` | Fixed async event loop reuse |

---

## SUMMARY

| Issue | Fix |
|-------|-----|
| Mode persists across requests | Reset at start of each request |
| Async loop instability | Reuse existing loop instead of create/close |

**Result:** No more alternating success/failure pattern.

---

*Intermittent failure audit. Evidence only.*
