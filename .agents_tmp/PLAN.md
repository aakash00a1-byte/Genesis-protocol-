# CONTEXT OVERFLOW FAILURE INVESTIGATION PLAN

## 1. OBJECTIVE

Reproduce and diagnose the context overflow failure that occurs when ingesting large reports. Identify the exact component (conversation_history, memory, database, context_builder, provider_chain, groq_provider, timeout, or token overflow) causing the "An error occurred. Please try again." error.

## 2. CONTEXT SUMMARY

### System Architecture
- **Entry Point:** `/api/chat` in `web/app.py` (line 327)
- **Agent Processing:** `genesis_protocol/ai/agent.py`
- **Provider Chain:** `genesis_protocol/ai/provider_chain.py`
- **LLM Providers:** `genesis_protocol/ai/providers/` (groq, openai, gemini, etc.)
- **Memory System:** `genesis_protocol/memory/` (unified_memory, conversation_memory)

### Error Source Identified
The error message "An error occurred. Please try again." originates from `agent.py` line 234-242:
```python
except Exception as e:
    self.logger.error(f"Agent processing error: {e}")
    return AgentResponse(
        success=False,
        response="An error occurred. Please try again.",
        ...
    )
```

### Pipeline Flow
```
/api/chat → agent.process() → _process_normal() → provider_chain.call() → Provider (Groq/API)
```

### Potential Failure Components
1. **Token Overflow:** No explicit truncation of large inputs before LLM context window
2. **Memory System:** Full report content stored, retrieved without truncation
3. **Provider Chain:** Messages array grows unbounded with large context
4. **Timeout:** Default 30-second timeout may be exceeded
5. **Database:** SQLite TEXT field handling large payloads
6. **Conversation History:** No pagination or size limits

## 3. APPROACH OVERVIEW

Evidence-first investigation using:
1. Diagnostic logging additions (non-invasive)
2. Reproduction with simulated large input
3. Railway log analysis
4. Component-by-component failure isolation

**Rationale:** User explicitly requested NO PATCHES and NO GUESSES - all conclusions must be evidence-based.

## 4. IMPLEMENTATION STEPS

### Step 1: Add Diagnostic Logging to Agent (EVIDENCE COLLECTION)

**Goal:** Capture exception type, stack trace, request length before error occurs

**Method:**
Add logging at the start of `agent.process()` and in the exception handler to capture:
- `len(query)` for request length
- `len(context)` for memory context size
- `sys.exc_info()` for full stack trace
- `len(messages)` for provider chain message count

**Reference:** `genesis_protocol/ai/agent.py` lines 111-125 and 234-242

### Step 2: Add Token Counting to Context Building (EVIDENCE COLLECTION)

**Goal:** Measure actual token count before sending to provider

**Method:**
Add logging in `_process_normal()` after building messages array:
- Count tokens using tiktoken (if available) or estimate
- Log each message length and total
- Log system prompt length separately

**Reference:** `genesis_protocol/ai/agent.py` lines 244-266

### Step 3: Create Reproduction Test Script (EVIDENCE COLLECTION)

**Goal:** Reproduce failure with controlled large input

**Method:**
Create test script that:
1. Generates a large text payload (simulating a report)
2. Sends to `/api/chat` endpoint
3. Captures full response including any errors
4. Measures timing at each pipeline stage

**Reference:** New file: `scripts/test_large_input.py`

### Step 4: Create Large Report Test Data (EVIDENCE COLLECTION)

**Goal:** Generate test data matching production scenario

**Method:**
Create a sample large report file (50KB-500KB) with realistic content to test:
- Maximum message size handling
- Token estimation accuracy
- Memory context accumulation

**Reference:** `data/test_reports/`

### Step 5: Analyze Railway Logs (EVIDENCE COLLECTION)

**Goal:** Examine production logs for actual error details

**Method:**
1. Access Railway dashboard for the production deployment
2. Filter logs for `/api/chat` requests with large payloads
3. Extract error messages, stack traces, and timing data
4. Compare with local reproduction results

**Reference:** Railway deployment at provided URLs

### Step 6: Test Each Component in Isolation (FAILURE ISOLATION)

**Goal:** Determine exact failing component

**Method:**
Test each component separately:
1. **Memory only:** Does `unified_memory.get_context()` handle large inputs?
2. **Context builder only:** Does `build_context()` truncate properly?
3. **Provider only:** Does Groq/OpenAI reject oversized requests?
4. **Database only:** Does SQLite handle large TEXT inserts?

**Reference:** 
- `genesis_protocol/memory/unified_memory.py`
- `genesis_protocol/ai/prompts/conversation_prompt.py`
- `genesis_protocol/ai/providers/groq_provider.py`

### Step 7: Measure Timeout Behavior (FAILURE ISOLATION)

**Goal:** Determine if timeout is the cause

**Method:**
1. Check current timeout configuration
2. Create test with large input that should timeout
3. Measure actual time to failure
4. Compare with timeout setting

**Reference:**
- `genesis_protocol/config.py` - timeout configuration
- `genesis_protocol/ai/providers/groq_provider.py` line 44

### Step 8: Document Findings with Evidence (REPORTING)

**Goal:** Record all evidence for root cause determination

**Method:**
Create evidence document capturing:
- Exception type and stack trace
- Request length at failure
- Token count at failure point
- Component that threw the exception
- Full error message from provider (if API error)

**Reference:** New file: `CONTEXT_OVERFLOW_EVIDENCE.md`

## 5. TESTING AND VALIDATION

### Success Criteria
- [ ] Reproduced same error with test script
- [ ] Captured full exception with stack trace
- [ ] Measured request length and token count
- [ ] Identified exact failing component
- [ ] Documented evidence without patching

### Validation Checklist
- [ ] Exception type identified (AttributeError, ValueError, httpx.HTTPStatusError, etc.)
- [ ] Stack trace captured showing failure point
- [ ] Request length recorded (bytes/characters)
- [ ] Token count estimated or calculated
- [ ] Railway logs examined
- [ ] Component isolated (memory/provider/database/timeout/token)

### Evidence Required for Each Item
| Item | Evidence Source |
|------|-----------------|
| Exception Type | `sys.exc_info()` output |
| Stack Trace | Full traceback string |
| Request Length | `len(query)` or `len(message)` |
| Token Count | Tiktoken count or estimation |
| Component | Line number and file from traceback |
