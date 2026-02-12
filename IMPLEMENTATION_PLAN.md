# Plan: Add Screen Content Validation to BBSBot (REVISED)

## Problem Statement

The TW2002 trading bot fails at menu navigation because it sends input based purely on `prompt_id` without validating that the screen state makes sense for that action. Example: the bot receives "prompt.login_name" and sends the username, but the screen actually says "Q to quit - login failed".

**Core Issue**: BBSBot detects *what prompt this is* via regex, but doesn't validate *whether the extracted data makes sense* or *what context the prompt is in*.

## Current State Analysis

### What BBSBot Already Has
- ✅ K/V extraction infrastructure (extractor.py) - extracts values from screens
- ✅ K/V extraction configs in rules (rules.json) - defines what to extract
- ✅ PromptDetection.kv_data field - stores extracted values
- ✅ Type conversion in extractor.py - converts to int, float, bool, string

### What's Missing
- ❌ K/V data is NOT passed to bots (stuck in engine.py, not in snapshot)
- ❌ No validation of extracted values (e.g., is sector 1-1000? are credits >= 0?)
- ❌ Bots receive only (input_type, prompt_id, screen) - no structured data
- ❌ Pre-send validation doesn't exist - bots send blind, catch errors after

### Data Flow Problem

```
Current Flow:
engine.process_screen()
  → detector.detect_prompt()  [identifies "prompt.login_name"]
  → extractor.extract_kv()     [gets {username: "bob"} from screen]
  → PromptDetection(kv_data={username: "bob"})
  → session.read() adds snapshot["prompt_detected"] = {prompt_id, input_type, is_idle}
                                                      ❌ kv_data missing here!
  → bot.wait_and_respond() returns (input_type, prompt_id, screen)
                                    ❌ kv_data lost!
  → trading.py sends input blind based on prompt_id

Needed Flow:
  ... same but:
  → snapshot["prompt_detected"] = {prompt_id, input_type, is_idle, kv_data, validation_status}
  → bot.wait_and_respond() returns (input_type, prompt_id, screen, kv_data)
  → trading.py validates kv_data BEFORE sending input
```

## Solution: Two-Layer Validation Architecture

### Layer 1: Infrastructure Validation (BBSBot)
**Purpose**: Ensure extracted data is well-formed and present

**Where**: extractor.py & rules.py Pydantic models

**What it does**:
- Validates extracted values against type constraints (int 1-1000, not "abc")
- Checks required fields are present
- Returns validation status alongside extracted data

**Example**:
```python
# Rule in rules.json:
{
  "field": "sector",
  "type": "int",
  "regex": "Sector\\s+(\\d+)",
  "validate": {
    "min": 1,
    "max": 1000
  }
}

# Result:
{
  "sector": 499,
  "_validation": {
    "valid": True,
    "errors": []
  }
}

# If screen has "Sector 9999":
{
  "sector": 9999,
  "_validation": {
    "valid": False,
    "errors": ["sector: value 9999 exceeds max 1000"]
  }
}
```

### Layer 2: Business Logic Validation (Bot)
**Purpose**: Make informed decisions before sending input

**Where**: io.py (wait_and_respond), login.py, trading.py

**What it does**:
- Reads kv_data from session
- Checks validation status
- Optionally applies game logic (e.g., "only trade in sector 499")
- Makes smart decisions about what to send

**Example**:
```python
input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)

# Don't send blind - check the data first
if kv_data and not kv_data.get("_validation", {}).get("valid", True):
    raise ScreenValidationError(f"Invalid screen state: {kv_data['_validation']['errors']}")

if "login_name" in prompt_id:
    # We know extraction worked and screen makes sense
    await send_input(bot, username, input_type)
```

## Implementation Plan

### Phase 1: Extend Extractor with Validation

**File**: `src/mcp_bbs/learning/extractor.py`

**Changes**:
1. Add validation logic to KVExtractor.extract():
```python
class KVExtractor:
    @staticmethod
    def extract(
        screen: str,
        config: dict | list,
        run_validation: bool = True  # NEW
    ) -> dict[str, Any] | None:
        # ... existing extraction code ...

        if run_validation and config:
            validation_result = KVExtractor._validate(extracted, config)
            extracted["_validation"] = validation_result

        return extracted

    @staticmethod
    def _validate(extracted: dict, config: list | dict) -> dict:
        """Validate extracted values against constraints."""
        errors = []
        configs = config if isinstance(config, list) else [config]

        for cfg in configs:
            field = cfg.get("field")
            value = extracted.get(field)
            validate_rules = cfg.get("validate", {})

            # Check required
            if cfg.get("required", False) and value is None:
                errors.append(f"{field}: required but not found")
                continue

            if value is None:
                continue

            # Check type (already converted, so validate value semantics)
            if cfg.get("type") == "int":
                if not isinstance(value, int):
                    errors.append(f"{field}: expected int, got {type(value).__name__}")
                    continue

                # Check min/max
                if "min" in validate_rules and value < validate_rules["min"]:
                    errors.append(f"{field}: value {value} below min {validate_rules['min']}")
                if "max" in validate_rules and value > validate_rules["max"]:
                    errors.append(f"{field}: value {value} exceeds max {validate_rules['max']}")

        return {"valid": len(errors) == 0, "errors": errors}
```

**Impact**: Minimal - only adds optional validation layer, backward compatible.

---

### Phase 2: Update Rules Schema (Pydantic)

**File**: `src/mcp_bbs/learning/rules.py`

**Changes**:
1. Extend `KVExtractRule` Pydantic model:
```python
class KVExtractRule(BaseModel):
    field: str
    type: str = "string"
    regex: str
    validate: Optional[Dict[str, Any]] = None  # NEW: {min, max, pattern, allowed_values}
    required: bool = False  # NEW

class ValidationConstraint(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    allowed_values: Optional[List[str]] = None
```

**Impact**: Schema extension only, backward compatible (all new fields optional).

---

### Phase 3: Surface K/V Data Through Session (CRITICAL)

**File**: `src/mcp_bbs/core/session.py`

**Current code (line ~121)**:
```python
if prompt_detection:
    snapshot["prompt_detected"] = {
        "prompt_id": prompt_detection.prompt_id,
        "input_type": prompt_detection.input_type,
        "is_idle": prompt_detection.is_idle,
    }
```

**Change to**:
```python
if prompt_detection:
    snapshot["prompt_detected"] = {
        "prompt_id": prompt_detection.prompt_id,
        "input_type": prompt_detection.input_type,
        "is_idle": prompt_detection.is_idle,
        "kv_data": prompt_detection.kv_data,  # NEW
    }
```

**Impact**: Small targeted change that unblocks the entire validation system.

**Why this matters**: Currently kv_data is extracted but thrown away. This makes it available to bots.

---

### Phase 4: Update Bot I/O Layer

**File**: `src/twbot/io.py`

**Current code (line ~35)**:
```python
async def wait_and_respond(
    bot,
    prompt_id_pattern: Optional[str] = None,
    timeout_ms: int = 10000,
) -> tuple[Optional[str], Optional[str], str]:
    # ... returns (input_type, prompt_id, screen)
```

**Change to**:
```python
async def wait_and_respond(
    bot,
    prompt_id_pattern: Optional[str] = None,
    timeout_ms: int = 10000,
) -> tuple[Optional[str], Optional[str], str, Optional[dict]]:
    """
    Wait for a prompt and return prompt context.

    Returns:
        (input_type, prompt_id, screen, kv_data)
        where kv_data may include "_validation" field with extraction status
    """
    snapshot = await bot.session.read(timeout_ms=250, max_bytes=8192)
    screen = snapshot.get("screen", "")

    if "prompt_detected" in snapshot:
        detected = snapshot["prompt_detected"]
        prompt_id = detected.get("prompt_id")
        input_type = detected.get("input_type")
        kv_data = detected.get("kv_data")  # NEW

        # ... existing error checking ...

        return (input_type, prompt_id, screen, kv_data)  # MODIFIED

    # ... existing timeout/error handling ...
```

**Breaking Change**: This changes the return type from 3-tuple to 4-tuple. **All callers must be updated**.

**Callers to update**:
- `login.py`: ~10 call sites
- `trading.py`: ~15 call sites
- `play_tw2002_trading.py`: a few call sites

---

### Phase 5: Update Bot Callers to Use K/V Data

**File**: `src/twbot/login.py`

**Example change (login prompt)**:
```python
# OLD:
input_type, prompt_id, screen = await wait_and_respond(bot)
if "login_name" in prompt_id and "telnet" not in screen_lower:
    await send_input(bot, username, input_type)

# NEW:
input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)

if "login_name" in prompt_id:
    # Validate screen makes sense before sending
    if kv_data and not kv_data.get("_validation", {}).get("valid", True):
        errors = kv_data["_validation"]["errors"]
        raise ScreenValidationError(f"Screen validation failed: {errors}")

    await send_input(bot, username, input_type)
```

**File**: `src/twbot/trading.py`

**Example change (quantity prompt)**:
```python
# OLD:
input_type, prompt_id, screen = await wait_and_respond(bot)
if "port_quantity" in prompt_id:
    await send_input(bot, str(quantity), input_type)

# NEW:
input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)

if "port_quantity" in prompt_id:
    # Extract current sector/credits to make smart decisions
    if kv_data:
        sector = kv_data.get("sector")
        credits = kv_data.get("credits")

        # Example: validate we're in right sector before buying
        if sector not in [499, 607]:  # Trading sectors
            raise TradeValidationError(f"Cannot trade in sector {sector}")

    await send_input(bot, str(quantity), input_type)
```

**Impact**: Systematic update to all callers. Enables pre-send validation throughout bot.

---

### Phase 6: Add Validation Rules to TW2002 Config

**File**: `games/tw2002/rules.json`

**Update these prompts with validation**:

```json
{
  "id": "prompt.sector_command",
  "kind": "menu",
  "input_type": "single_key",
  "match": {"pattern": "(?i)sector\\s+command.*", "match_mode": "regex"},
  "kv_extract": [
    {
      "field": "sector",
      "type": "int",
      "regex": "Sector\\s+(\\d+)",
      "validate": {"min": 1, "max": 1000},
      "required": true
    },
    {
      "field": "credits",
      "type": "int",
      "regex": "You have\\s+([\\d,]+)\\s+credit",
      "validate": {"min": 0},
      "required": true
    }
  ]
},
{
  "id": "prompt.port_command",
  "kind": "menu",
  "input_type": "single_key",
  "match": {"pattern": "(?i)port\\s+command.*", "match_mode": "regex"},
  "kv_extract": [
    {
      "field": "sector",
      "type": "int",
      "regex": "Sector\\s+(\\d+)",
      "validate": {"min": 1, "max": 1000},
      "required": true
    },
    {
      "field": "port_name",
      "type": "string",
      "regex": "Port:\\s+([\\w\\s]+?)(?:\\s|$)"
    }
  ]
}
```

---

### Phase 7: Addon System Integration (No Changes Needed)

**File**: `src/mcp_bbs/addons/tw2002.py`

**Decision**: Keep as-is for now. The addon layer can:
- Continue extracting high-level game state (trader.add_extracted_game_state_to_snapshot)
- Use K/V extraction for initial data
- Enrich with business logic

**Future consideration**: Could migrate more extraction logic to rules.json, but not required now.

---

## Critical Files Summary

### BBSBot Infrastructure Changes
1. **`src/mcp_bbs/learning/extractor.py`** - Add validation method
2. **`src/mcp_bbs/learning/rules.py`** - Extend Pydantic models for validation
3. **`src/mcp_bbs/core/session.py`** - Surface kv_data in snapshot (1 line change)

### Trading Bot Business Logic Changes
4. **`src/twbot/io.py`** - Update wait_and_respond() return type (breaking change)
5. **`src/twbot/login.py`** - Update all callers to handle 4-tuple return
6. **`src/twbot/trading.py`** - Update all callers to handle 4-tuple return
7. **`src/twbot/play_tw2002_trading.py`** - Update caller if present
8. **`games/tw2002/rules.json`** - Add validation constraints to key prompts

### No Changes Needed
- `src/twbot/errors.py` - Keep existing error detection
- `src/mcp_bbs/addons/tw2002.py` - Keep existing addon logic
- Tests: Create new tests, don't need separate validation.py module

---

## Implementation Order

1. **Week 1: Infrastructure**
   - Phase 1: Extend extractor.py with validation
   - Phase 2: Update rules.py Pydantic models
   - Phase 3: Update session.py to surface kv_data
   - **Test**: Verify kv_data appears in snapshot

2. **Week 2: Bot Integration**
   - Phase 4: Update io.py return type
   - Phase 5: Update all callers (login.py, trading.py, play script)
   - **Test**: Verify 4-tuple is returned and used

3. **Week 3: Rules & Validation**
   - Phase 6: Add validation rules to tw2002/rules.json
   - Phase 7: Verify addon integration
   - **Test**: Full trading cycle with validation

---

## Verification Steps

### Step 1: Test K/V Extraction with Validation

```python
# Test file: test_validation.py
from mcp_bbs.learning.extractor import KVExtractor
from mcp_bbs.learning.rules import KVExtractRule

# Test valid extraction
rule = {"field": "sector", "type": "int", "regex": r"Sector (\d+)", "validate": {"min": 1, "max": 1000}}
screen = "Sector 499"
result = KVExtractor.extract(screen, rule)
assert result["sector"] == 499
assert result["_validation"]["valid"] == True

# Test invalid extraction
screen = "Sector 9999"  # Exceeds max
result = KVExtractor.extract(screen, rule)
assert result["sector"] == 9999
assert result["_validation"]["valid"] == False
assert "exceeds max" in result["_validation"]["errors"][0]
```

### Step 2: Test K/V Data in Snapshot

```python
# Integration test
snapshot = await session.read()
if "prompt_detected" in snapshot:
    kv_data = snapshot["prompt_detected"].get("kv_data")
    assert kv_data is not None
    assert "_validation" in kv_data
```

### Step 3: Test Bot I/O Layer

```python
# Test wait_and_respond returns 4-tuple
input_type, prompt_id, screen, kv_data = await bot.wait_and_respond()
assert isinstance(kv_data, dict) or kv_data is None
```

### Step 4: Full Trading Cycle

```bash
# Should validate before each action
python play_tw2002_trading.py --single-cycle
# Expected: Bot validates screen state, sends input only when valid
```

---

## What This Achieves

✅ **Bots make informed decisions** - they read and validate screen state before sending input
✅ **Separation of concerns** - BBSBot handles extraction/validation, bots handle strategy
✅ **Backward compatible** - validation is optional, existing code still works
✅ **Reusable infrastructure** - any bot/game can use K/V extraction with validation
✅ **Reduced navigation failures** - screen context is validated before action

## What This Does NOT Do

❌ Create separate context_patterns system - too complex
❌ Create validation.py module - logic stays in extractor.py and bot layers
❌ Handle all possible game logic - that's bot's job
❌ Validate screen rendering bugs - focuses on data consistency

## Breaking Changes

**One breaking change**: `wait_and_respond()` now returns 4-tuple instead of 3-tuple.

**All callers must be updated**. List:
- `src/twbot/login.py` - ~10 call sites
- `src/twbot/trading.py` - ~15 call sites
- `src/twbot/play_tw2002_trading.py` - ~3 call sites
- Any other bots using this function

This is a deliberate change that forces bot code to update and use the new validation capability.
