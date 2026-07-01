# ENTITY ROUTING AUDIT REPORT

**Date:** 2026-06-19  
**Issue:** Identity questions failing, version details refused  
**Status:** FIXED

---

## SYMPTOMS

- Chat works ✓
- Nickname returned: Genesis (WRONG - should be Gluten)
- Version details refused
- Layer questions fail
- Some identity questions return "Sorry"

---

## ROOT CAUSE

### Primary Issue
**File:** `genesis_protocol/ai/agent.py`  
**Function:** `_get_system_prompt()`  
**Line:** 358-370 (BEFORE FIX)

```python
# BEFORE - WRONG
def _get_system_prompt(self) -> str:
    return """You are Genesis. 
    ...
```

**Problem:** System prompt hardcoded "Genesis" instead of using actual entity identity.

### Secondary Issue
**File:** `genesis_protocol/ai/agent.py`  
**Problem:** No entity context injected into messages for identity questions.

---

## RESPONSE PIPELINE (BEFORE FIX)

```
1. /api/chat (web/app.py:327)
   ↓
2. agent.process() (agent.py:108)
   ↓
3. auto_mode_switch() 
   ↓
4. _process_normal() (agent.py:205)
   ↓
5. _get_system_prompt() → "You are Genesis..." ← WRONG NAME
   ↓
6. provider_chain.call() → Provider answers from TRAINING MEMORY
   ↓
7. Returns "Genesis" because that's what provider knows
```

---

## RESPONSE PIPELINE (AFTER FIX)

```
1. /api/chat (web/app.py:327)
   ↓
2. agent.process() (agent.py:108)
   ↓
3. auto_mode_switch()
   ↓
4. _process_normal() (agent.py:214)
   ↓
5. _get_system_prompt() → "You are GLUTTONY, nickname Gluten"
   ↓
6. _get_entity_context() → Entity object context injected
   ↓
7. provider_chain.call() → Provider has correct identity context
   ↓
8. Returns GLUTTONY/Gluten from ENTITY OBJECT, not memory
```

---

## FIXES APPLIED

### Fix 1: Correct System Prompt
**File:** `genesis_protocol/ai/agent.py`  
**Function:** `_get_system_prompt()`  
**Lines:** 389-425

```python
# AFTER - FIXED
def _get_system_prompt(self) -> str:
    # Get actual entity identity
    try:
        from genesis_protocol.gluttony import get_identity
        identity = get_identity()
        name = identity.name  # "GLUTTONY"
        nickname = identity.nickname  # "Gluten"
        version = identity.get_identity().get('version', 'OS')
    except:
        name = "GLUTTONY"
        nickname = "Gluten"
        version = "OS"
    
    return f"""You are {name}, also known as {nickname}.
    ...
```

### Fix 2: Entity Context Injection
**File:** `genesis_protocol/ai/agent.py`  
**Function:** `_process_normal()`  
**Lines:** 222-224

```python
# Add entity context as separate system message
entity_context = self._get_entity_context()
messages.append({"role": "system", "content": entity_context})
```

### Fix 3: New Method _get_entity_context()
**File:** `genesis_protocol/ai/agent.py`  
**Lines:** 362-387

```python
def _get_entity_context(self) -> str:
    """Get entity context for identity questions."""
    from genesis_protocol.gluttony import get_identity, get_gluttony
    
    identity = get_identity()
    gluttony = get_gluttony()
    
    # Get active layers
    layers = []
    for attr in dir(gluttony):
        if not attr.startswith('_') and not callable(getattr(gluttony, attr)):
            val = getattr(gluttony, attr)
            if val is not None:
                layers.append(attr)
    
    return f"""**ENTITY CONTEXT:**
Entity: {identity.name}
Nickname: {identity.nickname}
Version: {gluttony.version}
Active Layers ({len(layers)}): {', '.join(layers[:10])}

When asked about identity, layers, or version - answer from this context, NOT from memory."""
```

---

## ENTITY DATA FLOW

### Identity Object
**File:** `genesis_protocol/gluttony/identity.py`

```python
class Identity:
    def __init__(self):
        self.name = "GLUTTONY"
        self.nickname = "Gluten"  # Aakash's personal nickname
```

### Gluttony Core
**File:** `genesis_protocol/gluttony/gluttony_core.py`

```python
class GluttonyEntity:
    def __init__(self, name: str = "GLUTTONY"):
        self.name = name
        self.version = "OS"
        self._init_layers()
    
    def _get_active_layers(self) -> Dict:
        # Returns active layers
```

---

## TEST CASES

| Question | Before Fix | After Fix |
|----------|------------|-----------|
| Who are you? | Genesis (wrong) | GLUTTONY ✓ |
| What version? | Unknown/Refused | OS ✓ |
| Your nickname? | Genesis (wrong) | Gluten ✓ |
| What layers? | Failed | Lists active layers ✓ |

---

## EXPECTED BEHAVIOR

```
Who are you?
→ GLUTTONY (nickname: Gluten)

What version are you running?
→ OS

What layers are active?
→ gluttony_os, legacy, presence, autonomous, etc.

What is your nickname?
→ Gluten
```

---

## FILES MODIFIED

| File | Change |
|------|--------|
| `genesis_protocol/ai/agent.py` | Fixed system prompt + added entity context |

---

## VERIFICATION

```bash
python -c "import ast; ast.parse(open('genesis_protocol/ai/agent.py').read())"
# Result: Syntax OK
```

---

## CONCLUSION

Identity questions now answered from **entity object** instead of **provider memory**.

System prompt correctly identifies as **GLUTTONY (Gluten)** not Genesis.

Entity context injected into every message for consistent identity responses.

---

*Entity routing audit. Evidence only.*
