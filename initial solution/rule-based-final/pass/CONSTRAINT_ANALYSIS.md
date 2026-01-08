# CONSTRAINT CONSISTENCY ANALYSIS: Planner vs Rule-Based

## Issue 2: Planner vs Rule-Based Check KHÔNG Nhất Quán

### XÁC NHẬN: CÓ SỰ KHÁC BIỆT

---

## Planner Constraint (ga_optimize_priority_fullschedule.py)

**Location**: Line ~260-262

```python
# Check admin hours constraint
if time_in_day + dur_room > admin_end:
    continue  # Skip to next time slot
```

**What it checks**:
```
time_in_day + duration + prep_time <= admin_end
```

**Rationale**: 
- Room must be freed (surgery + prep) within admin hours
- **KHÔNG check surgeon constraint**

---

## Rule-Based Constraint (rule_based_or_sim_v3.py)

**Location**: Line ~903-904

```python
end_surg = now + c.duration() + rest_time
if (not is_admin_time(end_surg - 1)) or (not same_calendar_day(now, end_surg - 1)):
    # Reschedule needed
```

**What it checks**:
```
now + duration + rest_time <= admin_end
AND same_calendar_day(now, end_surg - 1)
```

**Rationale**:
- **Surgeon** must finish (surgery + rest) within admin hours
- Must complete same day

---

## CRITICAL DIFFERENCES

| Aspect | Planner | Rule-Based | Impact |
|--------|---------|------------|--------|
| **Checked** | Room duration | Surgeon duration | Different! |
| **Formula** | dur + prep | dur + rest | Usually rest > prep |
| **Constraint** | `time_in_day + dur + prep <= admin_end` | `now + dur + rest <= admin_end` | Planner LOOSER |
| **Same day check** | ❌ NO | ✅ YES | Planner may span days |

---

## Example Where They Differ

**Scenario**:
- Admin hours: 08:00 - 16:00 (480 - 960 minutes)
- Surgery duration: 90 min
- Prep time: 15 min  
- Rest time: 30 min
- Candidate start: 15:00 (900 minutes)

**Planner check**:
```
time_in_day = 900
dur_room = 90 + 15 = 105
900 + 105 = 1005 > 960 (admin_end)
→ REJECT ✅ (correctly rejects)
```

But if start time = 14:50 (890):
```
890 + 105 = 995 > 960
→ REJECT
```

**Rule-Based check**:
```
end_surg = 900 + 90 + 30 = 1020
is_admin_time(1019)? → 1019 > 960 → FALSE
→ REJECT ✅
```

But if start = 14:50 (890):
```
end_surg = 890 + 90 + 30 = 1010
→ REJECT (surgeon not done in admin time)
```

---

## Where Planner is LOOSER (Allows cases Rule-Based would reject)

**If rest_time > prep_time** (which is common):

Start time near admin_end boundary:
- Planner: checks `t + dur + prep`
- Rule-Based: checks `t + dur + rest`
- If `rest > prep`: Rule-Based rejects more cases

**Result**: 
- Planner says "feasible"
- Simulator/Rule-Based reschedules → baseline fitness affected

---

## CONFIRMED: YES, KHÁC NHAU

✅ **Planner kiểm tra room constraint (dur + prep)**  
✅ **Rule-Based kiểm tra surgeon constraint (dur + rest)**

### Recommendation:

**Planner SHOULD check**:
```python
# Option A: Check BOTH constraints (strictest)
end_room = t + dur_room  # For room
end_surg = t + dur_surg  # For surgeon

if time_in_day + max(dur_room, dur_surg) > admin_end:
    continue

# Option B: Check surgeon only (match Rule-Based)
if time_in_day + dur_surg > admin_end:
    continue
```

**Which one?**
- Option A: Strictest (both room AND surgeon done in admin time)
- Option B: Match Rule-Based (surgeon constraint only)

**Tôi recommend Option B** để match Rule-Based behavior.

---

## Impact if NOT fixed:

- Planner allows cases that Rule-Based/Simulator will reschedule
- Baseline fitness inaccurate
- GA improvement % misleading
- Some "optimal" schedules infeasible in reality
