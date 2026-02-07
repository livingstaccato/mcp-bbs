# LLM Intervention System Implementation

## Overview

The intervention system provides intelligent oversight for TW2002 autonomous bots, detecting behavioral anomalies and missed opportunities through pattern recognition and LLM-powered analysis.

## Architecture

### Core Components

```
TradingBot
  └─ AIStrategy (decision-making)
      ├─ InterventionTrigger (coordination)
      │   ├─ InterventionDetector (pattern detection)
      │   └─ SessionLogger (event recording)
      └─ InterventionAdvisor (LLM analysis)
          └─ LLMManager (LLM calls)
```

### Files Created

**Intervention System** (`src/bbsbot/games/tw2002/interventions/`):
- `detector.py` (458 LOC) - Detection algorithms
- `trigger.py` (229 LOC) - Coordination logic
- `advisor.py` (275 LOC) - LLM prompt building
- `__init__.py` (29 LOC) - Package exports

**Configuration**:
- `config.py` - Added `InterventionConfig` class (35 lines)

**MCP Tools**:
- `mcp_tools_intervention.py` (218 LOC) - External control tools

**Integration**:
- `ai_strategy.py` - Added intervention hooks (151 lines added)

**Verification**:
- `scripts/verify_intervention_system.py` (363 LOC) - Automatic testing

## Detection Algorithms

### Anomalies (High Priority)

1. **Action Loop** (confidence: 0.85)
   - Same action repeated 3+ times
   - Alternating action patterns (A-B-A-B)

2. **Sector Loop** (confidence: 0.8)
   - Same sector visited 4+ times in window

3. **Goal Stagnation** (confidence: 0.75)
   - Credits change <5% over 15 turns

4. **Performance Decline** (confidence: 0.7)
   - Profit/turn drops >50% comparing halves

5. **Turn Waste** (confidence: 0.65)
   - >30% of turns with zero/negative profit

### Opportunities (Medium Priority)

1. **High-Value Trade** (configurable)
   - Available trade worth >5000 credits within 3 hops

2. **Combat Readiness** (confidence: 0.8)
   - Fighters >50 AND shields >100
   - Current goal not "combat"

3. **Banking Optimal** (confidence: 0.85)
   - Carrying >100k credits
   - Not in FedSpace

## LLM Integration

### System Prompt

The intervention advisor uses a specialized system prompt focused on anomaly detection:

```python
INTERVENTION_SYSTEM_PROMPT = """You are an expert Trade Wars 2002 gameplay analyst monitoring autonomous bot performance.

YOUR ROLE: Detect behavioral anomalies, performance degradation, and missed opportunities.

ANALYSIS FRAMEWORK:

1. PATTERN RECOGNITION
   - Stuck behaviors (repeated actions, location loops)
   - Efficiency drops (declining profit velocity, wasted turns)
   - Goal misalignment (actions inconsistent with stated goal)
   - Decision quality issues (poor reasoning, invalid assumptions)

2. OPPORTUNITY DETECTION
   - Overlooked profitable trades
   - Combat readiness gaps
   - Banking failures (excess credits not secured)
   - Exploration inefficiencies

3. SEVERITY ASSESSMENT
   - CRITICAL: Bot stuck, ship at risk, or major capital loss
   - WARNING: Performance declining, suboptimal patterns
   - INFO: Minor inefficiencies, optimization opportunities
```

### Context Building

Each intervention analysis receives rich context:
- Current game state (location, credits, ship status)
- Goal history with metrics (start/end credits, turns, transitions)
- Performance statistics (profit/turn, trades executed)
- Recent decisions with LLM reasoning
- Detected anomalies with evidence
- Identified opportunities with evidence

### Response Format

The LLM returns structured JSON:
```json
{
  "severity": "critical|warning|info",
  "category": "stuck_pattern|performance_decline|opportunity_missed|goal_misalignment",
  "observation": "Concise issue description",
  "evidence": ["Supporting fact 1", "Supporting fact 2"],
  "recommendation": "continue|adjust_goal|manual_review|direct_intervention",
  "suggested_action": {
    "type": "change_goal|reset_strategy|force_move|none",
    "parameters": {...}
  },
  "reasoning": "Why this recommendation",
  "confidence": 0.0-1.0
}
```

## Configuration

### InterventionConfig

```python
class InterventionConfig(BaseModel):
    # Enable/disable
    enabled: bool = True

    # Detection thresholds
    loop_action_threshold: int = 3
    loop_sector_threshold: int = 4
    stagnation_turns: int = 15
    profit_decline_ratio: float = 0.5
    turn_waste_threshold: float = 0.3

    # Opportunity thresholds
    high_value_trade_min: int = 5000
    combat_ready_fighters: int = 50
    combat_ready_shields: int = 100
    banking_threshold: int = 100000

    # Intervention behavior
    auto_apply: bool = False
    min_priority: str = "medium"
    cooldown_turns: int = 5
    max_per_session: int = 20

    # LLM settings
    analysis_temperature: float = 0.3
    analysis_max_tokens: int = 800
```

## MCP Tools

### get_intervention_status()

Returns current intervention system status:
```python
{
    "enabled": true,
    "interventions_this_session": 3,
    "budget_remaining": 17,
    "last_intervention_turn": 245,
    "recent_anomalies": [...],
    "recent_opportunities": [...],
    "turn_history_summary": {...}
}
```

### trigger_manual_intervention(analysis_prompt?)

Forces immediate intervention analysis:
```python
result = await trigger_manual_intervention(
    analysis_prompt="Why is the bot stuck in sector 100?"
)
```

## Session Logging

Interventions are logged to the session JSONL:

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
    "suggested_action": {"type": "change_goal", "parameters": {"goal": "exploration"}},
    "reasoning": "Bot appears stuck in navigation. Switching to exploration may help discover new routes.",
    "confidence": 0.85,
    "auto_applied": false,
    "llm_duration_ms": 1234.5
  }
}
```

## Code Quality

All files pass:
- ✅ **Ruff format/check** (120 char line length)
- ✅ **Mypy type checking** (strict mode)
- ✅ **Bandit security scan** (no issues)
- ✅ **File size limits** (all <500 LOC)

### Type Safety

- Uses `StrEnum` for enumerations
- Pydantic `BaseModel` for all data structures
- Full type annotations throughout
- Generic type hints with `list[T]` syntax

### Security

- No command injection vectors
- Safe JSON parsing with error handling
- Input validation via Pydantic
- No hardcoded credentials

## Integration Points

### AIStrategy Initialization

```python
# Intervention system
self._intervention_trigger = InterventionTrigger(
    enabled=config.intervention.enabled,
    min_priority=config.intervention.min_priority,
    cooldown_turns=config.intervention.cooldown_turns,
    max_interventions_per_session=config.intervention.max_per_session,
    session_logger=self._session_logger,
)
self._intervention_advisor = InterventionAdvisor(
    config=config,
    llm_manager=self.llm_manager,
)
```

### Decision Loop

```python
# Check for intervention triggers
should_intervene, reason, context = self._intervention_trigger.should_intervene(
    current_turn=self._current_turn,
    state=state,
    strategy=self,
)

if should_intervene:
    recommendation = await self._intervention_advisor.analyze(
        state=state,
        recent_decisions=self._get_recent_decisions(),
        strategy_stats=self.stats,
        goal_phases=self._goal_phases,
        anomalies=context.get("anomalies", []),
        opportunities=context.get("opportunities", []),
        trigger_reason=reason,
    )

    await self._intervention_trigger.log_intervention(...)

    if config.intervention.auto_apply:
        action, params = self._apply_intervention(recommendation, state)
```

### Result Tracking

```python
def record_action_result(self, action: TradeAction, profit_delta: int, state: GameState):
    """Record action result for intervention detection."""
    self._intervention_trigger.update_detector(
        turn=self._current_turn,
        state=state,
        action=action.name,
        profit_delta=profit_delta,
        strategy=self,
    )
```

## Verification

### Automatic Testing

The `verify_intervention_system.py` script provides end-to-end testing:

1. **Game Discovery**: Connects to localhost:2002 and discovers available games
2. **Multi-Game Testing**: Tests intervention system across multiple games
3. **Anomaly Monitoring**: Tracks all anomalies and opportunities detected
4. **Statistics**: Reports interventions triggered, anomalies found, turns played
5. **Results**: Saves detailed JSON results for analysis

Usage:
```bash
python scripts/verify_intervention_system.py
```

Output:
- Console logs with real-time progress
- `verification_output.log` with full output
- `verification_results.json` with detailed data

## Performance Characteristics

- **Detection Overhead**: Minimal - runs on existing action history
- **LLM Calls**: Controlled by cooldown (default 5 turns) and budget (default 20/session)
- **Memory**: Fixed-size rolling window (default 10 turns)
- **Latency**: Async LLM calls don't block decision loop

## Future Enhancements

1. **Learning from Interventions**
   - Track intervention outcomes
   - Adjust detection thresholds based on results
   - Build pattern library from successful interventions

2. **Advanced Detection**
   - Machine learning for pattern recognition
   - Temporal pattern analysis (time-series)
   - Multi-bot coordination patterns

3. **Visualization**
   - Real-time intervention dashboard
   - Anomaly heatmaps over time
   - Goal transition graphs with interventions

4. **Integration**
   - Prometheus metrics for monitoring
   - Alert webhooks for critical interventions
   - Strategy replay with intervention points marked

## Dependencies

- **Pydantic**: Data validation and serialization
- **LLMManager**: Existing LLM abstraction
- **SessionLogger**: Event persistence
- **GameState**: Current state tracking
- **GoalPhase**: Goal history tracking

## License

Same as bbsbot project (MIT)
