# BBSBot Configuration Examples

This directory contains example configurations for different use cases.

## AI Strategy Configurations

### Ollama (Local LLM)

**File:** `ai_strategy_ollama.yml`

Uses a local Ollama instance for AI decision-making.

**Prerequisites:**
```bash
# Install Ollama
brew install ollama  # or download from ollama.ai

# Start Ollama server
ollama serve

# Pull a model
ollama pull llama2
# or llama3, mistral, etc.
```

**Usage:**
```bash
# Set environment variables (optional)
export BBSBOT_LLM__PROVIDER=ollama
export BBSBOT_LLM__OLLAMA__MODEL=llama2
export BBSBOT_LLM__OLLAMA__BASE_URL=http://localhost:11434

# Run bot
python scripts/play_tw2002_trading.py --config examples/configs/ai_strategy_ollama.yml
```

### OpenAI (Future)

**File:** `ai_strategy_openai.yml`

Template for OpenAI integration (not yet implemented).

**Prerequisites:**
```bash
export OPENAI_API_KEY=sk-...
```

## Environment Variables

Configuration values can be overridden via environment variables using the pattern:
```
BBSBOT_<section>__<subsection>__<key>
```

Examples:
```bash
# LLM provider settings
export BBSBOT_LLM__PROVIDER=ollama
export BBSBOT_LLM__OLLAMA__MODEL=llama3
export BBSBOT_LLM__OLLAMA__BASE_URL=http://localhost:11434

# Trading strategy
export BBSBOT_TRADING__STRATEGY=ai_strategy
export BBSBOT_TRADING__AI_STRATEGY__FALLBACK_THRESHOLD=5

# Session limits
export BBSBOT_SESSION__MAX_TURNS_PER_SESSION=1000
```

## Strategy Comparison

| Strategy | Description | Pros | Cons |
|----------|-------------|------|------|
| `opportunistic` | Explores and trades at encountered ports | Simple, reliable | No long-term planning |
| `profitable_pairs` | Finds profitable port pairs | Efficient | Limited exploration |
| `twerk_optimized` | Uses data files for optimal routes | Maximum profit | Requires data files |
| `ai_strategy` | LLM-powered decisions with fallback | Adaptive, strategic | Requires LLM, slower |

## AI Strategy Notes

### Fallback Behavior

The AI strategy uses a hybrid approach:
1. **Primary:** LLM makes decisions
2. **Fallback:** OpportunisticStrategy on failures
3. **Threshold:** 3 consecutive failures triggers fallback
4. **Duration:** Stays in fallback for 10 turns before retrying LLM

### Prompt Configuration

- `context_mode: summary` - Concise prompts (~1600 tokens)
- `context_mode: full` - Detailed prompts (~2500 tokens)
- `sector_radius: 3` - Include adjacent sectors within 3 hops
- `include_history: true` - Add recent actions to prompt

### Performance Tuning

- `timeout_ms: 30000` - LLM request timeout
- `cache_decisions: false` - Cache similar game states (future)
- Lower `max_retries` for faster fallback
- Increase `fallback_duration_turns` for more stable gameplay

### Model Selection

**Ollama Models:**
- `llama2` (7B) - Fast, decent quality
- `llama3` (8B/70B) - Better reasoning, slower
- `mistral` (7B) - Good balance
- `codellama` (7B+) - Code-focused, good for structured output

**Recommendations:**
- Development: `llama2` (fast iteration)
- Production: `llama3` or `mistral` (better decisions)
- Low resources: `tinyllama` (1.1B, fast but limited)

## Troubleshooting

### Ollama Connection Errors

```
LLMConnectionError: Failed to connect to Ollama at http://localhost:11434
```

**Solution:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if not running
ollama serve
```

### Model Not Found

```
LLMModelNotFoundError: Model 'llama2' not found
```

**Solution:**
```bash
# List available models
ollama list

# Pull the model
ollama pull llama2
```

### LLM Timeouts

If LLM requests are timing out:
1. Increase `timeout_seconds` in config
2. Use a smaller/faster model
3. Reduce `max_retries` to fail faster

### Frequent Fallback Mode

If AI keeps entering fallback mode:
1. Check LLM logs for errors
2. Verify model is loaded and responsive
3. Try a more capable model
4. Increase `fallback_threshold` for tolerance
