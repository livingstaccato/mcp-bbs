# 🚀 Intervention System Ready for Live Testing

## Status: ✅ Ready for Phase 3

All preparation work complete. System ready to test with real games on localhost:2002.

## What's Been Done

### Phase 1: Bug Fix ✅
- **Critical bug fixed**: `_apply_intervention()` method now calls correct `self.set_goal()`
- Fixed 3 locations (lines 1125, 1134, 1163)
- All 386 tests still pass

### Phase 2: Test Configurations ✅
Created 3 YAML configs optimized for intervention testing:

1. **test_opportunistic_stuck.yaml**
   - Baseline test (should get stuck)
   - 90% exploration chance
   - Minimal profitable actions

2. **test_ai_intervention.yaml**
   - Auto-apply intervention enabled
   - Low thresholds for quick detection
   - OLLAMA gemma3 integration

3. **test_ai_manual_intervention.yaml**
   - Manual intervention mode
   - Detection without auto-apply
   - For MCP tool testing

### Phase 2: Testing Tools ✅
- **test_intervention_live.sh**: Guided test script
- **TESTING_GUIDE.md**: Complete testing documentation
- **Monitoring commands**: Real-time log viewing

## Prerequisites Verified

✅ OLLAMA running on localhost:11434
✅ gemma3 model available
✅ All 386 unit tests passing
✅ Bug fix applied and tested

## What Needs Testing

Still requires localhost:2002 server running to test:

### Test 1: Opportunistic Baseline
**Purpose**: Verify bot gets stuck (baseline)
**Command**:
```bash
python -m bbsbot.main --config config/test_opportunistic_stuck.yaml --host localhost --port 2002
```
**Expected**: Repeated actions, sector loops

### Test 2: Auto-Apply Intervention
**Purpose**: Full intervention system validation
**Command**:
```bash
python -m bbsbot.main --config config/test_ai_intervention.yaml --host localhost --port 2002
```
**Expected**: Detection → LLM → Auto-apply → Recovery

### Test 3: Manual Intervention
**Purpose**: MCP tool validation
**Command**:
```bash
python -m bbsbot.main --config config/test_ai_manual_intervention.yaml --host localhost --port 2002
```
**Expected**: Detection → Manual MCP intervention → Recovery

## Quick Start Testing

### Option 1: Guided Script
```bash
./scripts/test_intervention_live.sh localhost 2002
```

### Option 2: Manual Testing
```bash
# Verify OLLAMA
curl http://localhost:11434/api/tags | grep gemma3

# Run baseline test
python -m bbsbot.main --config config/test_opportunistic_stuck.yaml --host localhost --port 2002

# Monitor interventions
tail -f ~/.bbsbot/sessions/*.jsonl | grep '"event": "llm.intervention"'
```

## Monitoring During Tests

### Watch for Intervention Events
```bash
# Real-time monitoring
tail -f ~/.bbsbot/sessions/*.jsonl | grep '"event": "llm.intervention"'

# Check recent interventions
grep '"event": "llm.intervention"' ~/.bbsbot/sessions/*.jsonl | tail -5 | jq .
```

### MCP Tools Available
```python
# During Test 3 (manual mode)
await tw2002_get_intervention_status()
await tw2002_get_bot_status()
await tw2002_set_goal(goal="exploration")
```

## Success Criteria

### Anomaly Detection Works
- [ ] Action loops detected (2+ repeated actions)
- [ ] Sector loops detected (3+ visits)
- [ ] Stagnation detected (5+ turns no progress)
- [ ] Events logged to session JSONL

### LLM Intervention Works
- [ ] OLLAMA gemma3 receives prompt
- [ ] Valid JSON response returned
- [ ] Recommendation includes severity, category, action
- [ ] Response parsed without errors

### Auto-Apply Works
- [ ] Goal changes after intervention
- [ ] Bot behavior changes (new sectors/actions)
- [ ] Recovery observed within 5-10 turns
- [ ] Session logs show applied intervention

### Manual Intervention Works
- [ ] MCP tools accessible during runtime
- [ ] `get_intervention_status()` returns data
- [ ] Manual `set_goal()` changes behavior
- [ ] Bot recovers after manual action

## Expected Outcomes

1. **Baseline Test** (~10 min, 50 turns)
   - Bot gets stuck in predictable patterns
   - No interventions (system disabled)
   - Establishes problem to solve

2. **Auto-Apply Test** (~15 min, 100 turns)
   - Bot gets stuck
   - Intervention detected (logged)
   - LLM called with context
   - Recommendation applied
   - Bot recovers and continues

3. **Manual Test** (~15 min, 50 turns + manual)
   - Bot gets stuck
   - Intervention detected (logged)
   - Human reviews via MCP
   - Manual intervention applied
   - Bot recovers

## Troubleshooting Quick Reference

### No Interventions Trigger
- Lower thresholds in config (already set low)
- Check `enabled: true` in intervention config
- Verify `min_priority: "low"`

### LLM Fails
- Check OLLAMA: `curl http://localhost:11434/api/tags`
- Test gemma3: `ollama run gemma3 "test"`
- Try alternate model: llama3.2 or llama2

### Intervention Not Applied
- Verify `auto_apply: true` (Test 2)
- Check logs for `_apply_intervention` errors
- Use MCP tools for manual control (Test 3)

## Files to Review

**Configurations**:
- `config/test_opportunistic_stuck.yaml`
- `config/test_ai_intervention.yaml`
- `config/test_ai_manual_intervention.yaml`

**Documentation**:
- `.provide/TESTING_GUIDE.md` - Complete testing reference
- `.provide/HANDOFF.md` - Implementation summary
- `.provide/INTERVENTION_SYSTEM.md` - System architecture

**Scripts**:
- `scripts/test_intervention_live.sh` - Guided testing

**Session Logs** (after testing):
- `~/.bbsbot/sessions/*.jsonl` - All events including interventions

## Next Steps After Testing

1. Review intervention frequency (optimal?)
2. Tune thresholds based on gameplay
3. Adjust LLM prompt if needed
4. Document optimal settings
5. Update production configs
6. Consider multi-game testing

## Timeline Estimate

- **Setup verification**: 5 minutes
- **Test 1 (baseline)**: 10 minutes
- **Test 2 (auto-apply)**: 15 minutes
- **Test 3 (manual)**: 15 minutes
- **Review logs**: 10 minutes
- **Total**: ~55 minutes

---

**Ready to proceed when localhost:2002 is available.**

For detailed testing procedures, see `.provide/TESTING_GUIDE.md`
