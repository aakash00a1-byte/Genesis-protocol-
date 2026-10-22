# TRUST & IDENTITY CONFIDENCE REPAIR REPORT

**Date:** 2026-06-19  
**Issue:** System may present assumptions as facts  
**Status:** FIXED

---

## PROBLEM

### Before Fix
```
User: "Who is Aakash?"
Response: "You are Aakash."  ← WRONG - we don't KNOW this for certain
```

**Issues:**
1. Assumptions presented as facts
2. No distinction between known and unknown
3. Inferred identity stated confidently
4. User trust compromised by false claims

### Root Cause
**File:** `genesis_protocol/ai/identity_router.py`  
**Problem:** All identity claims stated without confidence levels.

---

## SOLUTION

### New Component: TrustConfidenceSystem
**File:** `genesis_protocol/ai/trust_confidence.py`

Manages identity claims with proper confidence levels.

---

## CONFIDENCE LEVELS

| Level | Meaning | Response Policy |
|-------|---------|-----------------|
| **EXPLICIT** | User directly stated | State confidently |
| **OBSERVED** | Available metadata/records | "Available records indicate..." |
| **INFERRED** | Derived from patterns | "I suspect..., but I am not certain." |
| **UNKNOWN** | No evidence | Ask user instead of guessing |

---

## IMPLEMENTATION

### 1. ConfidenceLevel Enum
**File:** `genesis_protocol/ai/trust_confidence.py`

```python
class ConfidenceLevel(Enum):
    EXPLICIT = "explicit"      # User directly stated
    OBSERVED = "observed"      # Metadata/persisted records
    INFERRED = "inferred"      # Derived from patterns
    UNKNOWN = "unknown"        # No evidence
```

### 2. IdentityEvidence Dataclass
**File:** `genesis_protocol/ai/trust_confidence.py`

```python
@dataclass
class IdentityEvidence:
    value: str
    confidence: ConfidenceLevel
    source: str                    # Where this came from
    timestamp: datetime
    raw_data: Optional[Dict]       # Original data if needed
```

### 3. TrustConfidenceSystem Class
**File:** `genesis_protocol/ai/trust_confidence.py`

| Method | Purpose |
|--------|---------|
| `get_entity_identity()` | Entity identity (always EXPLICIT) |
| `get_user_identity()` | User identity with confidence |
| `store_user_identity()` | Store with source/confidence/timestamp |
| `get_evidence()` | Retrieve evidence for a field |
| `build_identity_query()` | Build proper query with confidence |

### 4. Identity Router Updates
**File:** `genesis_protocol/ai/identity_router.py`

Responses now include confidence indicators:
```
I am **GLUTTONY** [EXPLICIT - I know this for certain]
My nickname is **Gluten** [EXPLICIT - hardcoded]
```

---

## RESPONSE EXAMPLES

### EXPLICIT → State Confidently
```
Question: "What is your name?"
Response: "My name is GLUTTONY." ✓
```

### OBSERVED → Qualified Statement
```
Question: "What is my name?"
Response: "Available records indicate your name may be Aakash, 
but I do not have explicit confirmation." ✓
```

### INFERRED → Uncertain Statement
```
Question: "What is my name?"
Response: "I suspect your name may be Aakash, but I am not certain.
Please confirm if this is correct." ✓
```

### UNKNOWN → Ask User
```
Question: "What is my name?"
Response: "I do not know your name. Could you please tell me?" ✓
```

---

## WRONG vs CORRECT

### Wrong (Before)
```
User: "Who are you talking to?"
AI: "I'm talking to Aakash." ← FALSE ASSUMPTION
```

### Correct (After)
```
User: "Who are you talking to?"
AI: "I do not know your name. Could you please tell me?" ✓
```

---

## STORING IDENTITY EVIDENCE

```python
# Store EXPLICIT identity (user told us)
trust.store_user_identity(
    user_id=1,
    field="name",
    value="Aakash",
    confidence=ConfidenceLevel.EXPLICIT,
    source="user_stated"
)

# Store OBSERVED identity (from metadata)
trust.store_user_identity(
    user_id=1,
    field="email",
    value="aakash@example.com",
    confidence=ConfidenceLevel.OBSERVED,
    source="metadata"
)

# Store INFERRED identity (from patterns)
trust.store_user_identity(
    user_id=1,
    field="city",
    value="Delhi",
    confidence=ConfidenceLevel.INFERRED,
    source="conversation_pattern"
)
```

---

## MEMORY ENTRIES WITH METADATA

Each memory entry now includes:
```python
{
    "value": "Aakash",
    "confidence": "explicit",        # EXPLICIT/OBSERVED/INFERRED/UNKNOWN
    "source": "user_stated",         # Where it came from
    "timestamp": "2026-06-19T..."    # When recorded
}
```

---

## IDENTITY ROUTER UPDATES

### Entity Identity (EXPLICIT)
```python
def _who_are_you(self, identity, gluttony) -> str:
    return f"""I am **{identity.name}**.

**Identity [EXPLICIT - I know this for certain]:**
- Name: {identity.name}
- Nickname: {identity.nickname}
...
"""
```

### User Identity (Uses Trust System)
```python
def _what_is_user_name(self, user_id: int = None) -> str:
    trust = get_trust_system()
    result = trust.get_user_identity(user_id)
    
    if result["status"] == "unknown":
        return result["message"]  # "Could you please tell me?"
    
    if result["message"]:
        return result["message"]  # Qualified response
    
    return f"Your name is {result['data']}."
```

---

## TESTS

**File:** `tests/test_trust_confidence.py`

| Test | Description |
|------|-------------|
| `test_entity_identity_explicit` | Entity identity is EXPLICIT |
| `test_entity_identity_no_qualification` | No confidence qualification needed |
| `test_user_identity_unknown_no_evidence` | Unknown asks user |
| `test_store_and_retrieve_explicit` | Store/retrieve EXPLICIT |
| `test_store_and_retrieve_observed` | Store/retrieve OBSERVED |
| `test_store_and_retrieve_inferred` | Store/retrieve INFERRED |
| `test_explicit_response_format` | EXPLICIT states confidently |
| `test_observed_response_format` | OBSERVED says "Available records..." |
| `test_inferred_response_format` | INFERRED says "I suspect..., but not certain" |
| `test_unknown_response_format` | UNKNOWN asks user |
| `test_never_promote_inference_to_fact` | INFERRED never as fact |
| `test_explicit_states_confidently` | EXPLICIT no qualification |

---

## RULES SUMMARY

| If Confidence Is | Then |
|-----------------|------|
| EXPLICIT | State confidently, no qualification |
| OBSERVED | Say "Available records indicate..." |
| INFERRED | Say "I suspect..., but I am not certain." |
| UNKNOWN | Ask user instead of guessing |

---

## NEVER DO

| Forbidden | Instead |
|-----------|---------|
| "You are Aakash." | "Available records indicate your name may be Aakash..." |
| "Your name is..." (no evidence) | "I do not know your name. Could you tell me?" |
| Guess as fact | Ask for confirmation |
| Assume identity | State uncertainty |

---

## FILES CREATED/MODIFIED

| File | Change |
|------|--------|
| `genesis_protocol/ai/trust_confidence.py` | CREATED - Confidence system |
| `genesis_protocol/ai/identity_router.py` | MODIFIED - Confidence indicators |
| `tests/test_trust_confidence.py` | CREATED - Confidence tests |

---

## CONCLUSION

- Never promote inference into fact
- EXPLICIT → state confidently
- OBSERVED → qualify with "Available records..."
- INFERRED → qualify with "I suspect..., but not certain"
- UNKNOWN → ask user instead of guessing

**Trust > Assumptions**  
**Evidence > Hallucination**

---

*Trust & confidence repair. Evidence only.*
