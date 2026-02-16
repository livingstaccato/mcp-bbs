# Release Checklist

Use this checklist before cutting a release branch/tag.

## 1. Code + Build Gates

- `pytest -q` passes for the full test suite.
- Targeted lint for changed Python files passes.
- `uv build` succeeds for both wheel and sdist.
- No unresolved merge markers or accidental debug edits remain.

## 2. Runtime Smoke Gates

- Swarm manager health is OK: `curl -sS http://localhost:2272/health`.
- Fresh swarm run starts cleanly after `/swarm/clear`.
- Swarm status shows stable workers (`errors == 0`).
- Trailing-window telemetry is captured and reviewed:
  - `net_worth_per_turn`
  - `trades_per_100_turns`
  - `trade_success_rate`
  - no-trade buckets (`t30`, `t60`, `t90`, `t120`)

## 3. AI/Ollama Gates

- With Ollama reachable, AI bot shows non-zero `llm_wakeups` and managed decisions.
- With Ollama intentionally unreachable, fallback is graceful:
  - `decision_source=fallback`
  - `wake_reason=ollama_not_available`
  - status/intent show `AI_DISABLED`.

## 4. Documentation Gates

- `README.md` and `docs/README.md` match current package/license metadata.
- No absolute workstation-specific paths remain in docs.
- Docs links resolve from a clean clone.
- Archive notes are under `docs/archive/` and active guides stay in `docs/guides/`.

## 5. Repository Hygiene

- Legacy scripts are archived under:
  - `scripts/archive/`
  - `src/bbsbot/commands/scripts/archive/`
- Active script surface is documented in archive READMEs.
- No generated artifacts are staged (`__pycache__`, `.pyc`, local logs/state).

## 6. Release Sign-off

- Release notes summarize major behavior changes and operator impact.
- Known risks are documented with mitigations.
- Final branch status is recorded (commit SHA + gate results).
