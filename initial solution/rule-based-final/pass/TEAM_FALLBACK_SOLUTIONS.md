# TEAM FALLBACK SOLUTION: Vấn đề baseline team mapping

## Issue 4: baseline_team không có trong valid_teams → fallback idx=0

### HIỆN TRẠNG

**Code** (line ~583-587):
```python
baseline_team_idx = {}
for pid, data in elective_baseline_data.items():
    team = data["baseline_team"]
    idx = team_to_idx.get(team, 0)  # ← FALLBACK TO 0!
    baseline_team_idx[pid] = idx
```

**Problem**:
- Nếu `baseline_team` KHÔNG nằm trong `team_to_idx`
- → Gán `idx = 0` (team đầu tiên trong valid list)
- → Baseline fitness sai
- → % improvement misleading

---

## KHI NÀO XẢY RA?

### Scenario 1: Assist2 pool khác

**surgery_schedule.xlsx**:
```
pid | main | assist1 | assist2
1   | S1   | S2      | S13      ← S13 không trong pool!
```

**Cap_Rank.xlsx**: Chỉ có S9-S12 trong assist2 pool

**Result**:
- `team_to_idx` không có `(S1, S2, S13)`
- Fallback → `idx=0` = `(S1, S2, S9)` (team khác!)

### Scenario 2: Cap file updated

**Original schedule**: Dùng team `(S3, S4, S10)`  
**New Cap_Rank**: S4 không còn qualified cho surgery type này

**Result**:
- Team invalid → fallback idx=0

---

## ĐỀ XUẤT PHƯƠNG ÁN

### Option A: STRICT - Raise Error (Recommended)

**Triết lý**: Baseline PHẢI reproducible, nếu không → fail fast

```python
baseline_team_idx = {}
for pid, data in elective_baseline_data.items():
    team = data["baseline_team"]
    stype = data["surgery_type"]
    
    # Try to find exact team
    idx = team_to_idx.get(team, None)
    
    if idx is None:
        # STRICT: Baseline team must exist in valid teams
        raise ValueError(
            f"Baseline team {team} for pid={pid} (surgery_type={stype}) "
            f"not found in valid_teams. This indicates baseline schedule "
            f"uses invalid team or Cap_Rank.xlsx mismatch. "
            f"Please ensure baseline schedule is generated with same "
            f"Cap_Rank.xlsx and team constraints."
        )
    
    baseline_team_idx[pid] = idx
```

**Pros**:
✅ Fail fast - phát hiện sớm data mismatch
✅ Đảm bảo baseline reproducible
✅ Prevent misleading metrics

**Cons**:
❌ Yêu cầu baseline schedule khớp 100% với Cap_Rank

---

### Option B: SMART FALLBACK - Find Similar Team

**Triết lý**: Tìm team "gần nhất" thay vì idx=0

```python
def find_nearest_team(target_team, valid_teams, surgery_type):
    """Find team most similar to target team."""
    best_match = None
    best_score = -1
    
    for idx, team in enumerate(valid_teams):
        score = 0
        # Match main surgeon
        if team[0] == target_team[0]:
            score += 3
        # Match assist1
        if team[1] == target_team[1]:
            score += 2
        # Match assist2
        if team[2] == target_team[2]:
            score += 1
        
        if score > best_score:
            best_score = score
            best_match = idx
    
    return best_match if best_match is not None else 0


baseline_team_idx = {}
for pid, data in elective_baseline_data.items():
    team = data["baseline_team"]
    stype = data["surgery_type"]
    
    idx = team_to_idx.get(team, None)
    
    if idx is None:
        # SMART FALLBACK: Find similar team
        valid_teams = valid_teams_by_type.get(stype, [])
        idx = find_nearest_team(team, valid_teams, stype)
        
        print(f"WARNING: Baseline team {team} for pid={pid} not found. "
              f"Using nearest match: {valid_teams[idx]}")
    
    baseline_team_idx[pid] = idx
```

**Pros**:
✅ Graceful degradation
✅ Baseline vẫn chạy được
✅ Tìm team "reasonable" thay vì arbitrary idx=0

**Cons**:
⚠️ Baseline không chính xác 100%
⚠️ Cần careful documentation

---

### Option C: PERMISSIVE - Keep current + Warning

**Triết lý**: Keep fallback=0 nhưng warn user

```python
baseline_team_idx = {}
warnings = []

for pid, data in elective_baseline_data.items():
    team = data["baseline_team"]
    stype = data["surgery_type"]
    
    idx = team_to_idx.get(team, None)
    
    if idx is None:
        idx = 0
        warnings.append(f"pid={pid}: team {team} → fallback to idx=0")
    
    baseline_team_idx[pid] = idx

if warnings:
    print("⚠️ BASELINE TEAM WARNINGS:")
    for w in warnings:
        print(f"  {w}")
    print("This may affect baseline fitness accuracy.")
```

**Pros**:
✅ Minimal code change
✅ User aware of issue

**Cons**:
❌ Baseline vẫn potentially wrong
❌ Metrics questionable

---

### Option D: HYBRID - Strict for validation, Permissive for exploration

```python
# Add argument to control behavior
def map_baseline_teams(
    elective_baseline_data, 
    team_to_idx, 
    valid_teams_by_type,
    strict_mode=True  # NEW ARGUMENT
):
    baseline_team_idx = {}
    
    for pid, data in elective_baseline_data.items():
        team = data["baseline_team"]
        stype = data["surgery_type"]
        
        idx = team_to_idx.get(team, None)
        
        if idx is None:
            if strict_mode:
                # FAIL FAST
                raise ValueError(f"Baseline team {team} not found for pid={pid}")
            else:
                # SMART FALLBACK
                valid_teams = valid_teams_by_type.get(stype, [])
                idx = find_nearest_team(team, valid_teams, stype)
        
        baseline_team_idx[pid] = idx
    
    return baseline_team_idx
```

**Usage**:
```python
# For validation runs (ensure correctness)
baseline_team_idx = map_baseline_teams(..., strict_mode=True)

# For exploration (allow flexibility)
baseline_team_idx = map_baseline_teams(..., strict_mode=False)
```

---

## RECOMMENDATION

**Tôi recommend Option A (STRICT)** vì:

1. **Scientific integrity**: Baseline phải reproducible
2. **Data quality**: Force user ensure data consistency
3. **Meaningful metrics**: % improvement có ý nghĩa

**Implementation priority**: HIGH

**Fallback plan**: Nếu user thường encounter issue này, dùng Option D (hybrid) để balance strict vs flexible.

---

## ADDITIONAL: Check for data consistency

**Before running GA**, add validation:

```python
def validate_baseline_consistency(
    elective_schedule_df,
    cap_rank_path,
    verbose=True
):
    """
    Validate that baseline schedule teams are valid per Cap_Rank.
    
    Returns: (is_valid, issues)
    """
    cap = load_cap_rank_xlsx(cap_rank_path)
    valid_teams_by_type = build_valid_teams_by_type(cap)
    
    issues = []
    
    for _, row in elective_schedule_df.iterrows():
        pid = row["pid"]
        stype = row["surgery_type"]
        team = (row["main"], row["assist1"], row["assist2"])
        
        valid_teams = valid_teams_by_type.get(stype, [])
        if team not in valid_teams:
            issues.append({
                "pid": pid,
                "surgery_type": stype,
                "team": team,
                "reason": "Team not in valid teams for this surgery type"
            })
    
    if verbose and issues:
        print(f"⚠️ Found {len(issues)} baseline team inconsistencies:")
        for issue in issues[:5]:  # Show first 5
            print(f"  PID {issue['pid']}: {issue['team']} invalid for {issue['surgery_type']}")
    
    return len(issues) == 0, issues

# Usage
is_valid, issues = validate_baseline_consistency(
    elective_df, 
    cap_rank_path="Cap_Rank.xlsx"
)

if not is_valid:
    print("ERROR: Baseline schedule has team inconsistencies!")
    print("Please regenerate baseline with correct Cap_Rank.xlsx")
    sys.exit(1)
```

This catches issues BEFORE GA runs → save time!
