# PRODUCTION REALITY REPORT
**Generated:** 2026-06-19

---

## 1. ENDPOINT STATUS

| Endpoint | HTTP Code | Status |
|----------|-----------|--------|
| `/api/health` | 200 | ✓ |
| `/api/entity` | 200 | ✓ |
| `/api/state` | 200 | ✓ |
| `/api/survival/status` | 200 | ✓ |
| `/api/timeline` | 200 | ✓ |
| `/api/journal` | 200 | ✓ |
| `/api/trust` | 200 | ✓ |
| `/api/archive` | 200 | ✓ |
| `/api/snapshot` | 200 | ✓ |
| `/api/knowledge` | 200 | ✓ |
| `/api/proposals` | 200 | ✓ |
| `/api/lessons` | 200 | ✓ |

**All 12 endpoints: 200 OK**

---

## 2. IDENTITY VERIFICATION

| Property | Value |
|----------|-------|
| **Entity name** | GLUTTONY |
| **Version** | OS |
| **Nickname** | Gluten |
| **Active layers count** | 12 |

**Active Layers:**
1. autonomous
2. interaction
3. learning
4. tools
5. improvement
6. proposal
7. approval
8. survival
9. knowledge
10. journal
11. trust
12. autonomy

---

## 3. JOURNAL ENTRY PERSISTENCE

| Test | Result |
|------|--------|
| Create journal entry | ✓ 200 |
| Entry content | "Production reality test - verification entry" |
| Entry type | observation |
| Total entries | 20 |
| Persistence verified | ✓ |

---

## 4. SNAPSHOT CREATION & VERIFICATION

| Test | Result |
|------|--------|
| Create snapshot | ✓ 200 |
| Snapshot ID | `daily_20260619_075916` |
| Snapshot label | "Production test snapshot" |
| File path | `data/legacy/snapshots/daily/daily_20260619_075916.json` |
| File size | 302 bytes |
| Snapshot exists | ✓ |

---

## 5. RESTART SIMULATION & PERSISTENCE

| Test | Before Restart | After Restart |
|------|---------------|---------------|
| Timeline events | 0 → 1 | 1 (preserved) ✓ |
| Relationship interactions | 0 | 0 (preserved) ✓ |
| Trust reliability | 0.8 | 0.8 (preserved) ✓ |

**Continuity Layer Restore:**
| Component | Restored |
|-----------|----------|
| Timeline | Yes ✓ |
| Relationship | Yes ✓ |
| Trust | Yes ✓ |

---

## 6. ARCHIVES STATUS

| Archive Type | Path |
|-------------|------|
| Archive root | `data/archive/` |
| Exports | `data/archive/exports/` |
| Snapshots | `data/archive/snapshots/` |

---

## 7. TEST SUITE RESULTS

| Metric | Value |
|--------|-------|
| **Total tests** | 225 |
| **Passed** | 225 |
| **Failed** | 0 |
| **Duration** | 3.68s |

---

## 8. STARTUP METRICS

| Metric | Value |
|--------|-------|
| **Startup time** | 0.398 seconds |
| **Memory (Current RSS)** | 12.58 MB |
| **Memory (Peak RSS)** | 3.04 MB (test) |
| **CPU Usage** | 2.4% |
| **Available Memory** | 14162.12 MB |

---

## 9. WARNINGS DETECTED

### Resource Warnings (6)
These are minor file handling warnings - files opened but not explicitly closed:

| File | Type |
|------|------|
| `data/proposals/proposals.json` | unclosed read |
| `data/approvals/requests.json` | unclosed read |
| `data/survival/costs.json` | unclosed read |
| `data/gluttony_os/self_knowledge.json` | unclosed read/write |
| `data/gluttony_os/journal/2026-06-19.json` | unclosed read |

**Severity:** LOW - These don't affect functionality but should be fixed for resource hygiene.

---

## 10. CRITICAL FAILURES

**None detected.**

---

## SUMMARY

| Category | Status |
|----------|--------|
| All endpoints responding | ✓ |
| Identity verified | ✓ |
| Journal persistence | ✓ |
| Snapshot creation | ✓ |
| Restart persistence | ✓ |
| Test suite | ✓ 225/225 |
| Critical failures | ✓ None |

---

## RECOMMENDATIONS

1. **Fix file handle leaks** - Add context managers or explicit close() for JSON file operations
2. **Monitor memory growth** - Track over longer uptime periods
3. **Regular snapshots** - Implement automated daily/weekly/monthly snapshot scheduling

---

*Evidence only. No assumptions made.*
