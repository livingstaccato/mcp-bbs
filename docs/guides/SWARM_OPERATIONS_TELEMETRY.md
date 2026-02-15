# Swarm Operations + Telemetry Guide

This guide documents the current TW2002 swarm runtime behavior, the ROI math,
and the diagnostics required to explain performance drops.

## What Changed

1. ROI baseline now uses **net worth estimate** (not liquid credits only).
2. Cargo valuation includes:
   - observed port quotes,
   - parsed quote-derived value hints,
   - conservative commodity floor fallback.
3. Credits handling now tracks verification state:
   - `credits_verified`
   - `credits_last_verified_at`
   - dashboard can display cached credits while reconnecting.
4. Prompt/screen normalization strips ANSI and leaked SGR fragments.
5. Screen action tags like `<Move>` are extracted and exposed in status:
   - `screen_primary_action_tag`
   - `screen_action_tags`
   - `screen_action_tag_telemetry`.
6. Anti-collapse and trade-quality controls are config-driven with strategy overrides.

## Config Controls (Global + Override)

Primary controls live under:

- `trading.anti_collapse`
- `trading.trade_quality`

Optional strategy overrides:

- `trading.profitable_pairs.anti_collapse_override`
- `trading.profitable_pairs.trade_quality_override`
- `trading.no_trade_guard.anti_collapse_override`
- `trading.no_trade_guard.trade_quality_override`

Effective value resolution:

`effective = global defaults + strategy override (partial allowed)`

## Runtime Signals to Watch

Use these endpoints continuously:

- `/swarm/status`
- `/swarm/timeseries/summary?window_minutes=15`
- `/swarm/timeseries/summary?window_minutes=60`

Key health metrics:

- `delta.net_worth_per_turn`
- `delta.trades_per_100_turns`
- `delta.trade_success_rate`
- `delta.no_trade_120p`
- `delta.roi_confidence`
- `delta.roi_low_confidence`
- `delta.roi_confidence_reasons`

Trade-quality / anti-collapse diagnostics:

- `trade_quality.block_rate`
- `trade_quality.accept_rate`
- `trade_quality.verified_lane_growth_rate`
- `trade_quality.reroute_events_per_100_turns`
- `trade_failure_reasons` (especially `wrong_side`, `no_port`, `no_interaction`)

Combat/attrition attribution:

- `combat_telemetry`
- `attrition_telemetry`
- `delta_attribution_telemetry` (`trade|bank|combat|unknown`)

## Interpreting Common Failure Patterns

1. `credits` dips while `net worth` holds:
   - often inventory timing, not real loss.
2. Low `trade_success_rate` with rising structural failures:
   - lane quality issue (`wrong_side`/`no_port`), not combat.
3. High turns with near-flat credits:
   - throughput collapse or over-exploration; inspect attempt budget and blocked counters.
4. Credits flicker around reconnect:
   - expected while unverified; confirm with `credits_verified`.
5. Frequent login/menu states:
   - session churn or prompt recovery; inspect worker logs and prompt context.

## Clean-Room Re-Test Checklist

1. Stop manager/workers.
2. Clear `sessions/*` runtime artifacts and `logs/*`.
3. Start manager in foreground TTY.
4. Spawn fixed composition run (example: 19 dynamic + 1 AI).
5. Record 15m and 60m summaries from a zeroed baseline.
6. On degradation, classify bottom bots with status + events + worker log sample.

## Release Gate Checklist (Swarm-Focused)

1. `errors == 0`
2. `running >= target-1`
3. 15m `net_worth_per_turn > 0` for final 3 samples
4. 15m `trades_per_100_turns >= 1.0` (or current run target)
5. 15m `trade_success_rate >= 0.08` (or current run target)
6. Negative deltas have attribution evidence (`trade|bank|combat|unknown`)

