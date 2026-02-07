# Intervention System Live Testing Guide

## Prerequisites

✅ All unit tests passing (386/386)
✅ Bug fix applied (`_set_goal` → `set_goal`)
✅ OLLAMA running with gemma3 model
✅ TW2002 server on localhost:2002

## Test Configurations

### Test 1: Opportunistic Baseline
**File**: `config/test_opportunistic_stuck.yaml`
**Purpose**: Establish baseline - bot should get stuck
**Expected**: Repeated actions, sector loops, no progress

```bash
python -m bbsbot.main --config config/test_opportunistic_stuck.yaml --host localhost --port 2002
```

**Monitor for**:
- Same action repeated 3+ times
- Same sector visited 4+ times
- Credits not increasing
- Bot circling between few sectors

### Test 2: Auto-Apply Intervention
**File**: `config/test_ai_intervention.yaml`
**Purpose**: Full intervention system test
**Expected**: Detection → LLM analysis → Auto-apply → Recovery

```bash
python -m bbsbot.main --config config/test_ai_intervention.yaml --host localhost --port 2002
```

**Monitor for**:
1. Console logs showing intervention trigger
2. LLM query to OLLAMA gemma3
3. JSON response with recommendation
4. Goal change logged
5. Bot behavior changes (new sectors, trades)

### Test 3: Manual Intervention
**File**: `config/test_ai_manual_intervention.yaml`
**Purpose**: Human-in-the-loop testing
**Expected**: Detection → Logged → Human reviews → Manual action

```bash
python -m bbsbot.main --config config/test_ai_manual_intervention.yaml --host localhost --port 2002
```

**MCP Tools Available**:
```python
# Check intervention status
status = await tw2002_get_intervention_status()
# Returns: enabled, interventions_count, anomalies, opportunities

# View current bot state
bot_status = await tw2002_get_bot_status()
# Returns: sector, credits, goal, turns, etc.

# Manually intervene
await tw2002_set_goal(goal="exploration", duration_turns=20)

# Force manual intervention
await tw2002_trigger_manual_intervention()
```

## Monitoring Commands

### Watch Session Logs in Real-Time
```bash
# Monitor all intervention events
tail -f ~/.bbsbot/sessions/*.jsonl | grep '"event": "llm.intervention"'

# Monitor all events
tail -f ~/.bbsbot/sessions/*.jsonl | jq .
```

### Check Recent Interventions
```bash
# Last 10 intervention events
grep '"event": "llm.intervention"' ~/.bbsbot/sessions/*.jsonl | tail -10 | jq .

# Count interventions per session
grep '"event": "llm.intervention"' ~/.bbsbot/sessions/*.jsonl | wc -l
```

### Verify OLLAMA Status
```bash
# Check if running
curl -s http://localhost:11434/api/tags | jq '.models[].name'

# Test gemma3 directly
curl http://localhost:11434/api/generate -d '{
  "model": "gemma3",
  "prompt": "Return JSON: {\"test\": \"value\"}",
  "stream": false
}' | jq .
```

## Intervention Event Structure

Logged as JSONL to `~/.bbsbot/sessions/<session_id>.jsonl`:

```json
{
  "ts": 1707300123.456,
  "event": "llm.intervention",
  "session_id": 12345,
  "data": {
    "turn": 245,
    "intervention_number": 3,
    "trigger_type": "anomaly",
    "priority": "HIGH",
    "category": "action_loop",
    "observation": "Repeating MOVE action 3+ times",
    "evidence": ["Last 5 actions: MOVE→MOVE→MOVE→WAIT→MOVE"],
    "recommendation": "adjust_goal",
    "suggested_action": {
      "type": "change_goal",
      "parameters": {"goal": "exploration"}
    },
    "reasoning": "Bot appears stuck in navigation...",
    "confidence": 0.85,
    "auto_applied": true,
    "llm_duration_ms": 1234.5
  }
}
```

## Success Criteria

### ✅ Detection Working
- [ ] Action loops detected (same action 2+ times)
- [ ] Sector loops detected (same sector 3+ visits)
- [ ] Stagnation detected (no progress 5+ turns)
- [ ] Logged with correct priority/confidence

### ✅ LLM Integration Working
- [ ] OLLAMA gemma3 receives prompt
- [ ] Returns valid JSON response
- [ ] Recommendation parsed correctly
- [ ] Duration logged (<5s typical)

### ✅ Auto-Apply Working
- [ ] Intervention applied automatically
- [ ] Goal changes visible in logs
- [ ] Bot behavior changes after intervention
- [ ] Recovery observed within 5-10 turns

### ✅ Manual Intervention Working
- [ ] MCP tools accessible during runtime
- [ ] `get_intervention_status()` returns data
- [ ] `set_goal()` changes bot behavior
- [ ] Recovery after manual intervention

## Troubleshooting

### OLLAMA Issues
**Problem**: LLM calls fail or timeout
**Solutions**:
1. Check OLLAMA running: `curl http://localhost:11434/api/tags`
2. Verify gemma3: Should appear in model list
3. Test manually: `ollama run gemma3 "test"`
4. Increase timeout: Edit `analysis_timeout_seconds` in config

### Invalid JSON Responses
**Problem**: LLM returns non-JSON or malformed
**Solutions**:
1. Check OLLAMA logs for errors
2. Lower `analysis_temperature` (0.1-0.3)
3. Test with different model: `llama3.2` or `llama2`
4. Review intervention prompt in logs

### No Interventions Trigger
**Problem**: Bot runs but no interventions logged
**Solutions**:
1. Lower thresholds in config:
   - `loop_action_threshold: 2`
   - `loop_sector_threshold: 3`
   - `stagnation_turns: 5`
2. Check `min_priority: "low"` to catch all
3. Verify `enabled: true` in intervention config
4. Check cooldown not blocking: `cooldown_turns: 2`

### Interventions Not Applied
**Problem**: Detected but bot doesn't change
**Solutions**:
1. Verify `auto_apply: true` for auto-testing
2. Check recommendation type is valid
3. Review `_apply_intervention()` logs
4. Ensure no exceptions in application logic

## Test Execution Checklist

**Pre-Flight**:
- [ ] OLLAMA running (`ollama serve`)
- [ ] gemma3 available (`ollama list | grep gemma3`)
- [ ] TW2002 server running (localhost:2002)
- [ ] All tests passing (`python -m pytest tests/ -q`)

**Test 1 - Baseline**:
- [ ] Bot started with opportunistic config
- [ ] Observed stuck behavior (loops/stagnation)
- [ ] Baseline session log saved

**Test 2 - Auto-Apply**:
- [ ] Bot started with auto-intervention config
- [ ] Anomaly detected and logged
- [ ] LLM called with intervention prompt
- [ ] Valid JSON response received
- [ ] Intervention auto-applied
- [ ] Goal changed in logs
- [ ] Bot recovered (new behavior observed)
- [ ] Session log contains intervention events

**Test 3 - Manual**:
- [ ] Bot started with manual config
- [ ] Anomaly detected and logged
- [ ] Used MCP `get_intervention_status()`
- [ ] Reviewed recommendations
- [ ] Applied manual intervention via MCP
- [ ] Bot recovered after manual action

**Post-Test**:
- [ ] Review all session logs
- [ ] Count interventions per test
- [ ] Verify recovery success rate
- [ ] Document any threshold adjustments needed
- [ ] Update HANDOFF.md with findings

## Expected Timeline

- **Test 1**: 5-10 minutes (50 turns)
- **Test 2**: 10-15 minutes (100 turns)
- **Test 3**: 10-15 minutes (50 turns + manual intervention)
- **Total**: ~30-40 minutes for all tests

## Next Steps After Testing

1. Review intervention frequency (too many/too few?)
2. Tune thresholds based on real gameplay
3. Adjust LLM prompt if responses poor quality
4. Consider different OLLAMA models if gemma3 insufficient
5. Document optimal configuration settings
6. Update production configs with tuned values
