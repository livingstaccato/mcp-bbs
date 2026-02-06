# AI Strategy Quick Start Guide

## Overview

The AI Strategy uses Large Language Models (LLMs) to make intelligent trading decisions in Trade Wars 2002. It features:

- **Provider-agnostic architecture** - Swap between Ollama, OpenAI, Gemini
- **Hybrid approach** - LLM primary, algorithmic fallback on failures
- **Resilient design** - Graceful degradation, automatic recovery
- **Production-ready** - Comprehensive error handling, retry logic

## Prerequisites

### Option 1: Ollama (Recommended for Getting Started)

```bash
# Install Ollama
brew install ollama  # macOS
# or download from https://ollama.ai

# Start Ollama server
ollama serve

# Pull a model (in another terminal)
ollama pull llama2
# or try: llama3, mistral, codellama
```

### Option 2: OpenAI (Future)

OpenAI provider is stubbed out but not yet implemented.

```bash
export OPENAI_API_KEY=sk-...
```

## Installation

```bash
# Install dependencies
pip install -e .

# Or just the new dependency
pip install httpx>=0.27.0
```

## Quick Start

### 1. Using Configuration File

Create a config file or use the example:

```bash
cp examples/configs/ai_strategy_ollama.yml my_config.yml
```

Edit if needed:

```yaml
trading:
  strategy: ai_strategy

llm:
  provider: ollama
  ollama:
    model: llama2
```

Run the bot:

```bash
python scripts/play_tw2002_trading.py --config my_config.yml
```

### 2. Using Environment Variables

Override config with environment variables:

```bash
export BBSBOT_TRADING__STRATEGY=ai_strategy
export BBSBOT_LLM__PROVIDER=ollama
export BBSBOT_LLM__OLLAMA__MODEL=llama2

python scripts/play_tw2002_trading.py
```

### 3. Programmatic Usage

```python
from bbsbot.games.tw2002 import TradingBot, BotConfig
from bbsbot.games.tw2002.config import TradingConfig

# Configure AI strategy
config = BotConfig()
config.trading.strategy = "ai_strategy"
config.llm.provider = "ollama"
config.llm.ollama.model = "llama2"

# Create and run bot
bot = TradingBot(config=config, ...)
# ... bot.play() ...
```

## How It Works

### Decision Flow

```
1. GameState → PromptBuilder
   ├─ System prompt: Game mechanics, actions
   └─ User prompt: Current state, ship status, adjacent sectors

2. Prompt → LLMManager → Ollama → LLM Response

3. Response → ResponseParser
   ├─ Try JSON parsing
   └─ Fallback to regex

4. Validate decision against game state
   ├─ Success: Execute action
   └─ Failure: Use fallback strategy

5. Track failures
   └─ 3 consecutive failures → Fallback mode for 10 turns
```

### Fallback Behavior

The AI strategy uses OpportunisticStrategy as fallback:

- **Threshold:** 3 consecutive LLM failures
- **Duration:** Stays in fallback for 10 turns
- **Recovery:** Automatically retries LLM after cooldown
- **Resilient:** Game continues even if LLM is unavailable

## Configuration Reference

### AI Strategy Settings

```yaml
trading:
  strategy: ai_strategy

  ai_strategy:
    # Enable/disable AI
    enabled: true

    # Fallback behavior
    fallback_strategy: opportunistic
    fallback_threshold: 3        # Failures before fallback
    fallback_duration_turns: 10  # Turns in fallback mode

    # Prompt configuration
    context_mode: summary        # full | summary
    sector_radius: 3             # Adjacent sectors to include
    include_history: true
    max_history_items: 5

    # Performance
    timeout_ms: 30000            # LLM request timeout
    cache_decisions: false       # Future feature

    # Learning
    record_history: true         # Future feature
```

### LLM Provider Settings

```yaml
llm:
  provider: ollama

  ollama:
    base_url: http://localhost:11434
    model: llama2
    timeout_seconds: 30.0
    max_retries: 3
    retry_delay_seconds: 1.0
    retry_backoff_multiplier: 2.0
```

## Model Recommendations

### Development
- **llama2** (7B) - Fast, decent quality, good for testing
- **tinyllama** (1.1B) - Very fast, limited reasoning

### Production
- **llama3** (8B) - Better reasoning, still fast
- **mistral** (7B) - Good balance of speed and quality
- **codellama** (7B+) - Good for structured output

### Testing
```bash
# Compare models
ollama pull llama2
ollama pull llama3
ollama pull mistral

# Run with different models
BBSBOT_LLM__OLLAMA__MODEL=llama3 python scripts/play_tw2002_trading.py
```

## Monitoring

### Check Logs

```bash
# View AI decisions
grep "ai_decision" ~/.bbsbot/tw2002/*.jsonl

# View failures
grep "ai_strategy_failure" ~/.bbsbot/tw2002/*.jsonl

# View fallback activations
grep "ai_strategy_entering_fallback" ~/.bbsbot/tw2002/*.jsonl
```

### Log Format

AI decisions are logged with structured data:

```json
{
  "event": "ai_decision",
  "action": "TRADE",
  "reasoning": "Port has good buy prices",
  "confidence": 0.85,
  "latency_ms": 1250
}
```

## Troubleshooting

### Ollama Not Running

**Error:** `LLMConnectionError: Failed to connect to Ollama`

**Solution:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

### Model Not Found

**Error:** `LLMModelNotFoundError: Model 'llama2' not found`

**Solution:**
```bash
# List available models
ollama list

# Pull the model
ollama pull llama2
```

### Slow Decisions

**Problem:** LLM takes 5+ seconds per decision

**Solutions:**
1. Use a smaller/faster model (llama2 vs llama3:70b)
2. Reduce context with `context_mode: summary`
3. Lower `sector_radius` to reduce adjacent sector info
4. Check CPU/GPU usage with `ollama ps`

### Frequent Fallback

**Problem:** AI keeps entering fallback mode

**Solutions:**
1. Check Ollama logs: `ollama logs`
2. Try a more capable model
3. Increase `timeout_seconds`
4. Increase `fallback_threshold` for more tolerance
5. Check prompt quality with `context_mode: full`

### Invalid Decisions

**Problem:** LLM suggests invalid actions

**Solutions:**
1. Validation catches most issues
2. Check logs for `invalid_*` messages
3. Try a more capable model
4. Adjust prompt in `strategies/ai/prompts.py`

## Performance Tips

### Optimize for Speed
```yaml
llm:
  ollama:
    model: llama2           # Faster than llama3
    timeout_seconds: 10.0   # Fail faster

trading:
  ai_strategy:
    context_mode: summary
    sector_radius: 2
    include_history: false
```

### Optimize for Quality
```yaml
llm:
  ollama:
    model: llama3           # Better reasoning
    timeout_seconds: 60.0   # More time to think

trading:
  ai_strategy:
    context_mode: full
    sector_radius: 4
    include_history: true
```

## Advanced Usage

### Custom Prompts

Edit `src/bbsbot/games/tw2002/strategies/ai/prompts.py`:

```python
SYSTEM_PROMPT = """
Your custom system prompt here...
"""
```

### Custom Response Parsing

Edit `src/bbsbot/games/tw2002/strategies/ai/parser.py`:

```python
def _parse_with_regex(self, content: str, state: GameState):
    # Add custom parsing logic
    ...
```

### Multiple LLM Providers

```python
# Switch providers dynamically
config.llm.provider = "ollama"
bot1 = TradingBot(config=config)

config.llm.provider = "openai"  # When implemented
bot2 = TradingBot(config=config)
```

## Next Steps

1. **Test with real game** - Run 50+ turns and observe behavior
2. **Tune prompts** - Adjust based on LLM output quality
3. **Monitor performance** - Track decision quality and latency
4. **Experiment with models** - Find best balance for your needs
5. **Implement OpenAI** - When needed for production

## Examples

See `examples/configs/` for complete configuration examples:

- `ai_strategy_ollama.yml` - Working Ollama setup
- `ai_strategy_openai.yml` - OpenAI template (future)
- `README.md` - Detailed documentation

## Getting Help

If you encounter issues:

1. Check logs in `~/.bbsbot/tw2002/`
2. Verify Ollama is running: `curl http://localhost:11434/api/tags`
3. Test with simpler model: `llama2` or `tinyllama`
4. Enable debug logging: `export BBSBOT_LOG_LEVEL=DEBUG`
5. Check documentation in `examples/configs/README.md`

## What's Next?

Future enhancements planned:

- OpenAI and Gemini provider implementations
- Response caching for similar game states
- Few-shot learning with successful examples
- Function calling API support
- Multi-agent coordination
- Token usage tracking and cost monitoring

Happy trading! 🚀
