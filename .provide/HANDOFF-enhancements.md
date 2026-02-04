# Pattern Management & Screen Saving Enhancements

## Overview

Added optional pattern management tools and automatic screen saving to complement the enhanced auto-learn loop with prompt detection.

## New Features Implemented

### 1. Pattern Management Tools

**Three new MCP tools for managing prompt patterns:**

#### `bbs_load_prompts_json(namespace)`
- Reload prompt patterns from JSON file
- Optionally specify different namespace to load from
- Returns loaded pattern count and metadata
- Automatically updates the PromptDetector with new patterns

**Example:**
```python
result = await bbs_load_prompts_json(namespace="tw2002")
# Returns: {"success": True, "patterns_loaded": 10, "namespace": "tw2002", ...}
```

#### `bbs_save_prompt_pattern(pattern_json)`
- Append a new prompt pattern to the namespace's prompts.json
- Validates required fields (id, regex)
- Checks for duplicate IDs
- Automatically updates metadata timestamp
- Adds pattern to detector immediately

**Example:**
```python
pattern = {
    "id": "sector_prompt",
    "regex": "Sector\\s+\\d+\\s*:",
    "input_type": "single_key",
    "expect_cursor_at_end": True,
    "notes": "Trade Wars sector navigation prompt"
}
result = await bbs_save_prompt_pattern(json.dumps(pattern))
# Returns: {"success": True, "pattern_id": "sector_prompt", "total_patterns": 11}
```

### 2. Screen Saving to Disk

**Automatic screen capture to organized directory structure:**

#### ScreenSaver Module (`src/mcp_bbs/learning/screen_saver.py`)
- Saves each unique screen to disk (deduplicated by hash)
- Organized by namespace: `.bbs-knowledge/games/{namespace}/screens/`
- Filename format: `{timestamp}-{hash[:8]}-{prompt_id}.txt`
- Includes metadata header with:
  - Timestamp, hash, cursor position, terminal size
  - Prompt ID (if detected)
  - Input type, idle state
  - Cursor at end indicator
  - Time since last change

**Example saved screen:**
```
================================================================================
SCREEN CAPTURE
================================================================================
Timestamp: 2026-02-03 14:56:01
Hash: abc123def456
Cursor: (18, 2)
Size: 80x25
Terminal: ANSI
Prompt ID: login_username
Input Type: multi_key
Idle: True
Cursor at End: True
Time Since Last Change: 2.15s
================================================================================

Welcome to Trade Wars 2002!

Enter your name: _
```

#### Control Tools

**`bbs_set_screen_saving(enabled)`**
- Enable/disable screen saving
- Default: enabled

**`bbs_get_screen_saver_status()`**
- Get current status
- Returns: enabled, screens_dir, saved_count, namespace

### 3. Enhanced Status Tool

**`bbs_status()` now includes:**

```python
{
    "connected": True,
    "host": "localhost",
    "port": 2002,
    "learning": {
        "enabled": True,
        "namespace": "tw2002",
        "prompt_detection": {
            "patterns_loaded": 10,
            "idle_threshold_seconds": 2.0
        },
        "screen_buffer": {
            "size": 15,
            "max_size": 50,
            "is_idle": True,
            "last_change_seconds_ago": 2.34
        },
        "screen_saver": {
            "enabled": True,
            "screens_dir": ".bbs-knowledge/games/tw2002/screens",
            "saved_count": 23,
            "namespace": "tw2002"
        }
    }
}
```

## Files Created

1. `src/mcp_bbs/learning/screen_saver.py` - Screen saving module
2. `test_screen_saving.py` - Screen saving tests

## Files Modified

1. `src/mcp_bbs/app.py` - Added 4 new MCP tools, enhanced bbs_status
2. `src/mcp_bbs/learning/engine.py` - Integrated ScreenSaver, added control methods

## Integration

The screen saver is automatically:
- Initialized with LearningEngine
- Enabled by default
- Updated when namespace changes
- Called on every unique screen (deduplicated by hash)
- Saves screens with prompt ID when detected

## Usage Examples

### Managing Patterns

```python
# Load patterns from different namespace
await bbs_load_prompts_json(namespace="new_game")

# Add new pattern
pattern = {
    "id": "combat_prompt",
    "regex": "Fire\\s+weapons\\?\\s+\\(Y/N\\)",
    "input_type": "single_key",
    "expect_cursor_at_end": True
}
await bbs_save_prompt_pattern(json.dumps(pattern))

# Check status
status = await bbs_status()
print(f"Patterns loaded: {status['learning']['prompt_detection']['patterns_loaded']}")
```

### Controlling Screen Saving

```python
# Disable screen saving temporarily
await bbs_set_screen_saving(enabled=False)

# Do some navigation without saving screens
# ...

# Re-enable
await bbs_set_screen_saving(enabled=True)

# Check what's been saved
saver_status = await bbs_get_screen_saver_status()
print(f"Saved {saver_status['saved_count']} unique screens to {saver_status['screens_dir']}")
```

### Reviewing Saved Screens

```bash
# List saved screens for a game
ls -lh .bbs-knowledge/games/tw2002/screens/

# Example output:
# 20260203-145601-abc123de-login_username.txt
# 20260203-145615-def456gh-main_menu.txt
# 20260203-145632-ghi789jk-sector_command.txt

# View a specific screen
cat .bbs-knowledge/games/tw2002/screens/20260203-145601-abc123de-login_username.txt
```

## Benefits

1. **Pattern Refinement**: Easy to add/test new patterns without editing JSON manually
2. **Session Replay**: All unique screens saved for later analysis
3. **Debugging**: Screen captures help diagnose prompt detection issues
4. **Documentation**: Auto-generated screen library for each game
5. **Training Data**: Screens with metadata can train better detection models

## Performance Considerations

- **Deduplication**: Only saves unique screen hashes (no duplicates)
- **Async I/O**: File writes don't block session reads
- **Memory**: Only hash tracking in memory, files on disk
- **Disk Space**: Text files are small (~1-5KB each), can save thousands

## Testing

All features tested:
- ✓ Pattern loading from JSON
- ✓ Pattern saving with validation
- ✓ Screen saving with deduplication
- ✓ Metadata header formatting
- ✓ Directory structure creation
- ✓ Force save override
- ✓ Enhanced status reporting

## Next Steps

### Recommended

1. **Test Live with TW2002**
   - Connect to BBS and navigate
   - Verify screens are saved correctly
   - Check that prompt IDs appear in filenames
   - Review saved screen content

2. **Pattern Library Building**
   - Use `bbs_save_prompt_pattern` to add patterns as you discover them
   - Test each pattern with `bbs_wait_for_prompt`
   - Build comprehensive pattern library for TW2002

3. **Screen Analysis**
   - Review saved screens directory
   - Identify common prompts not in patterns.json
   - Add missing patterns

### Optional

1. **Screen Viewer Tool**
   - MCP tool to list/view saved screens
   - Filter by prompt_id, date range
   - Show screen transitions

2. **Pattern Statistics**
   - Track which patterns match most often
   - Identify unused patterns
   - Pattern effectiveness metrics

3. **Auto-Pattern Learning**
   - Analyze saved screens to suggest new patterns
   - Learn from user corrections
   - Generate patterns from screen sequences

## Files Reference

**New Tools:**
- `bbs_load_prompts_json(namespace)` - Reload patterns
- `bbs_save_prompt_pattern(pattern_json)` - Save new pattern
- `bbs_set_screen_saving(enabled)` - Control screen saving
- `bbs_get_screen_saver_status()` - Get saver status

**Enhanced Tools:**
- `bbs_status()` - Now includes buffer, detection, and saver info

**New Module:**
- `src/mcp_bbs/learning/screen_saver.py` - Screen persistence

**Screen Storage:**
- `.bbs-knowledge/games/{namespace}/screens/` - Saved screens directory
