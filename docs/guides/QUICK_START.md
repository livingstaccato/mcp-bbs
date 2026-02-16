# Quick Start

This guide gets you from zero to a running TW2002 bot quickly.

## 1. Prerequisites

- Python and `uv` are installed.
- A TW2002 server is reachable (default `localhost:2002`).
- You are in the repo root.

## 2. Verify Setup

```bash
uv run bbsbot --help
uv run bbsbot tw2002 check --host localhost --port 2002
```

If the check fails, fix server connectivity before continuing.

## 3. Run a First Bot

Recommended first run:

```bash
uv run bbsbot tw2002 bot -c examples/configs/test_opportunistic_stuck.yaml
```

Run with explicit host/port overrides if needed:

```bash
uv run bbsbot tw2002 bot \
  -c examples/configs/test_opportunistic_stuck.yaml \
  --host localhost \
  --port 2002
```

## 4. Run an AI Bot

Use the Ollama example config:

```bash
uv run bbsbot tw2002 bot -c examples/configs/ai_strategy_ollama.yml
```

If you want the bundled play-mode runner:

```bash
uv run bbsbot tw2002 play --mode intelligent
```

Available play modes:

```bash
uv run bbsbot tw2002 play --mode full
uv run bbsbot tw2002 play --mode trading
uv run bbsbot tw2002 play --mode 1000turns
```

## 5. Live Screen Visibility

Print live screen output during bot execution:

```bash
uv run bbsbot tw2002 bot -c examples/configs/test_opportunistic_stuck.yaml --watch
```

Or expose watch socket output:

```bash
uv run bbsbot tw2002 bot -c examples/configs/test_opportunistic_stuck.yaml \
  --watch-socket --watch-socket-protocol json
```

## 6. Swarm Manager (Optional)

Start manager API/dashboard:

```bash
uv run python -m bbsbot.manager
```

Common manager endpoints:

```bash
curl -sS http://localhost:2272/health
curl -sS http://localhost:2272/swarm/status
curl -sS -X POST http://localhost:2272/swarm/clear
```

## 7. Next Steps

- For AI strategy details: `docs/guides/INTELLIGENT_BOT.md`
- For swarm telemetry and triage: `docs/guides/SWARM_OPERATIONS_TELEMETRY.md`
- For config examples: `examples/configs/README.md`
