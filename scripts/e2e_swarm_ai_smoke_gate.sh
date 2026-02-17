#!/usr/bin/env bash
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

MANAGER_URL="${MANAGER_URL:-http://localhost:2272}"
TW2002_HOST="${TW2002_HOST:-localhost}"
TW2002_PORT="${TW2002_PORT:-2002}"
TW2002_GAME_LETTER="${TW2002_GAME_LETTER:-C}"
BASE_CONFIG="${BASE_CONFIG:-examples/configs/test_ai_intervention.yaml}"
OLLAMA_ON_URL="${OLLAMA_ON_URL:-http://localhost:11434}"
OLLAMA_OFF_URL="${OLLAMA_OFF_URL:-http://127.0.0.1:65530}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3}"
MAX_TURNS="${MAX_TURNS:-20}"
MIN_TURNS_ON="${MIN_TURNS_ON:-4}"
MIN_TURNS_OFF="${MIN_TURNS_OFF:-4}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-2}"
POLL_TIMEOUT_SECONDS="${POLL_TIMEOUT_SECONDS:-240}"

RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
ARTIFACT_DIR="${ARTIFACT_DIR:-logs/e2e/ai_smoke_${RUN_STAMP}}"
TMP_DIR="$(mktemp -d)"
MANAGER_PID=""
MANAGER_STARTED_BY_SCRIPT="0"

log() {
  printf '[e2e-smoke] %s\n' "$*"
}

die() {
  printf '[e2e-smoke] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  set +e
  if curl -fsS "${MANAGER_URL}/health" >/dev/null 2>&1; then
    curl -fsS -X POST "${MANAGER_URL}/swarm/clear" >/dev/null 2>&1 || true
  fi
  if [[ "${MANAGER_STARTED_BY_SCRIPT}" == "1" ]]; then
    if [[ -n "${MANAGER_PID}" ]]; then
      kill "${MANAGER_PID}" >/dev/null 2>&1 || true
    fi
    pkill -f "python3 -m bbsbot.manager" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}

trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

wait_for_manager_health() {
  local retries=30
  local sleep_seconds=1
  local i
  for i in $(seq 1 "${retries}"); do
    if curl -fsS "${MANAGER_URL}/health" >"${ARTIFACT_DIR}/manager_health.json" 2>/dev/null; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  return 1
}

ensure_manager() {
  if curl -fsS "${MANAGER_URL}/health" >"${ARTIFACT_DIR}/manager_health.json" 2>/dev/null; then
    log "Using existing swarm manager at ${MANAGER_URL}"
    return 0
  fi

  log "Starting swarm manager at ${MANAGER_URL}"
  uv run python -m bbsbot.manager >"${ARTIFACT_DIR}/manager.log" 2>&1 &
  MANAGER_PID="$!"
  MANAGER_STARTED_BY_SCRIPT="1"

  if ! wait_for_manager_health; then
    die "Manager failed to start; see ${ARTIFACT_DIR}/manager.log"
  fi
}

check_ollama_on() {
  local tags_url="${OLLAMA_ON_URL%/}/api/tags"
  if ! curl -fsS "${tags_url}" >"${ARTIFACT_DIR}/ollama_tags.json"; then
    die "Ollama not reachable at ${OLLAMA_ON_URL}"
  fi
  if ! python - "${ARTIFACT_DIR}/ollama_tags.json" "${OLLAMA_MODEL}" <<'PY'
import json
import sys

tags_path = sys.argv[1]
model = sys.argv[2]
data = json.load(open(tags_path, encoding="utf-8"))
models = data.get("models") or []
for item in models:
    name = str(item.get("name") or "")
    if name == model or name.startswith(f"{model}:"):
        raise SystemExit(0)
raise SystemExit(1)
PY
  then
    die "Model ${OLLAMA_MODEL} not found at ${OLLAMA_ON_URL}"
  fi
}

build_case_config() {
  local source="$1"
  local target="$2"
  local ollama_url="$3"

  python - "${source}" "${target}" "${TW2002_HOST}" "${TW2002_PORT}" "${TW2002_GAME_LETTER}" "${MAX_TURNS}" "${ollama_url}" "${OLLAMA_MODEL}" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
host = sys.argv[3]
port = int(sys.argv[4])
game_letter = sys.argv[5]
max_turns = int(sys.argv[6])
ollama_url = sys.argv[7]
model = sys.argv[8]

text = source.read_text(encoding="utf-8")

patterns = [
    (r'(^\s*host:\s*)".*?"(\s*(?:#.*)?)$', rf'\g<1>"{host}"\g<2>', "host"),
    (r'(^\s*port:\s*)\d+(\s*(?:#.*)?)$', rf"\g<1>{port}\g<2>", "port"),
    (r'(^\s*game_letter:\s*)".*?"(\s*(?:#.*)?)$', rf'\g<1>"{game_letter}"\g<2>', "game_letter"),
    (
        r'(^\s*max_turns_per_session:\s*)\d+(\s*(?:#.*)?)$',
        rf"\g<1>{max_turns}\g<2>",
        "max_turns_per_session",
    ),
    (r'(^\s*base_url:\s*)".*?"(\s*(?:#.*)?)$', rf'\g<1>"{ollama_url}"\g<2>', "ollama.base_url"),
    (r'(^\s*model:\s*)".*?"(\s*(?:#.*)?)$', rf'\g<1>"{model}"\g<2>', "ollama.model"),
]

for pattern, replacement, label in patterns:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"Failed to set {label} in {source}")
    text = updated

target.write_text(text, encoding="utf-8")
PY
}

clear_swarm() {
  curl -fsS -X POST "${MANAGER_URL}/swarm/clear" >"$1"
}

run_case() {
  local mode="$1"
  local config_path="$2"
  local min_turns="$3"
  local case_dir="${ARTIFACT_DIR}/${mode}"
  local bot_id="e2e_${mode}_${RUN_STAMP}"
  local attempts=$((POLL_TIMEOUT_SECONDS / POLL_INTERVAL_SECONDS))
  local reached=0
  local i
  local turns=0
  local llm_wakeups=0
  local state="unknown"

  mkdir -p "${case_dir}"
  log "Running ${mode} scenario with bot_id=${bot_id}"

  clear_swarm "${case_dir}/clear_before.json"
  curl -fsS -X POST --get "${MANAGER_URL}/swarm/spawn" \
    --data-urlencode "config_path=${config_path}" \
    --data-urlencode "bot_id=${bot_id}" \
    >"${case_dir}/spawn.json"

  for i in $(seq 1 "${attempts}"); do
    curl -fsS "${MANAGER_URL}/swarm/status" >"${case_dir}/status_latest.json"
    read -r turns llm_wakeups state <<<"$(python - "${case_dir}/status_latest.json" "${bot_id}" <<'PY'
import json
import sys

status_path = sys.argv[1]
bot_id = sys.argv[2]
obj = json.load(open(status_path, encoding="utf-8"))
bot = next((b for b in obj.get("bots", []) if b.get("bot_id") == bot_id), {})
turns = int(bot.get("turns_executed") or 0)
llm = int(bot.get("llm_wakeups") or 0)
state = str(bot.get("state") or "missing")
print(f"{turns} {llm} {state}")
PY
)"
    log "${mode} poll=${i} state=${state} turns=${turns} llm_wakeups=${llm_wakeups}"
    if (( turns >= min_turns )); then
      reached=1
      break
    fi
    sleep "${POLL_INTERVAL_SECONDS}"
  done

  if (( reached == 0 )); then
    die "${mode} scenario did not reach ${min_turns} turns in ${POLL_TIMEOUT_SECONDS}s"
  fi

  curl -fsS "${MANAGER_URL}/swarm/status" >"${case_dir}/status_final.json"
  curl -fsS "${MANAGER_URL}/bot/${bot_id}/events" >"${case_dir}/events.json"
  curl -fsS "${MANAGER_URL}/swarm/timeseries/summary?window_minutes=15" >"${case_dir}/timeseries_15m.json"

  python - "${mode}" "${case_dir}/status_final.json" "${case_dir}/events.json" "${bot_id}" "${case_dir}/assertions.json" <<'PY'
import json
import sys
from pathlib import Path

mode = sys.argv[1]
status_path = Path(sys.argv[2])
events_path = Path(sys.argv[3])
bot_id = sys.argv[4]
assertions_path = Path(sys.argv[5])

status_obj = json.load(status_path.open(encoding="utf-8"))
events_obj = json.load(events_path.open(encoding="utf-8"))

bot = next((b for b in status_obj.get("bots", []) if b.get("bot_id") == bot_id), None)
if not bot:
    raise SystemExit(f"Bot {bot_id} not found in status output")

actions = [e for e in events_obj.get("events", []) if e.get("type") == "action"]
if not actions:
    raise SystemExit(f"{mode}: no action events captured")

managed_sources = {"llm_managed", "llm_direct", "supervisor_autopilot", "goal_contract"}
managed_count = sum(1 for e in actions if str(e.get("decision_source") or "") in managed_sources)
fallback_count = sum(1 for e in actions if str(e.get("decision_source") or "") == "fallback")
non_fallback_count = sum(1 for e in actions if str(e.get("decision_source") or "") not in {"", "fallback"})
ollama_unavailable_count = sum(
    1 for e in actions if str(e.get("wake_reason") or "").startswith("ollama_not_available")
)
ai_disabled_count = sum(1 for e in actions if "AI_DISABLED" in str(e.get("strategy_intent") or ""))
ai_action_count = sum(1 for e in actions if str(e.get("action") or "").startswith("AI:"))
llm_wakeups = int(bot.get("llm_wakeups") or 0)
turns_executed = int(bot.get("turns_executed") or 0)

if mode == "on":
    if llm_wakeups <= 0:
        raise SystemExit("AI-on assertion failed: llm_wakeups must be > 0")
    if managed_count <= 0 and non_fallback_count <= 0:
        raise SystemExit("AI-on assertion failed: no managed/non-fallback decisions found")
    if ollama_unavailable_count > 0:
        raise SystemExit("AI-on assertion failed: got ollama_not_available wake reasons")
elif mode == "off":
    if fallback_count <= 0:
        raise SystemExit("AI-off assertion failed: no fallback decisions found")
    if ollama_unavailable_count <= 0:
        raise SystemExit("AI-off assertion failed: no ollama_not_available wake reason found")
    if ai_disabled_count <= 0:
        raise SystemExit("AI-off assertion failed: no AI_DISABLED intent found")
    if non_fallback_count > 0:
        raise SystemExit("AI-off assertion failed: found non-fallback decisions")
else:
    raise SystemExit(f"Unknown mode: {mode}")

summary = {
    "mode": mode,
    "bot_id": bot_id,
    "turns_executed": turns_executed,
    "llm_wakeups": llm_wakeups,
    "action_events": len(actions),
    "ai_action_events": ai_action_count,
    "managed_count": managed_count,
    "fallback_count": fallback_count,
    "non_fallback_count": non_fallback_count,
    "ollama_not_available_count": ollama_unavailable_count,
    "ai_disabled_count": ai_disabled_count,
    "strategy": bot.get("strategy"),
    "status_detail": bot.get("status_detail"),
}

assertions_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary))
PY
}

main() {
  require_cmd uv
  require_cmd curl
  require_cmd python

  mkdir -p "${ARTIFACT_DIR}"
  log "Artifacts: ${ARTIFACT_DIR}"

  [[ -f "${BASE_CONFIG}" ]] || die "Base config not found: ${BASE_CONFIG}"

  log "Checking TW2002 connectivity ${TW2002_HOST}:${TW2002_PORT}"
  uv run bbsbot tw2002 check --host "${TW2002_HOST}" --port "${TW2002_PORT}" \
    >"${ARTIFACT_DIR}/tw2002_check.log" 2>&1 || die "TW2002 connectivity check failed"

  log "Checking Ollama model availability at ${OLLAMA_ON_URL}"
  check_ollama_on

  ensure_manager

  local config_on="${TMP_DIR}/ai_on.yaml"
  local config_off="${TMP_DIR}/ai_off.yaml"
  build_case_config "${BASE_CONFIG}" "${config_on}" "${OLLAMA_ON_URL}"
  build_case_config "${BASE_CONFIG}" "${config_off}" "${OLLAMA_OFF_URL}"

  run_case "on" "${config_on}" "${MIN_TURNS_ON}"
  run_case "off" "${config_off}" "${MIN_TURNS_OFF}"

  clear_swarm "${ARTIFACT_DIR}/clear_after.json"

  log "PASS: AI on/off swarm smoke gate succeeded"
  log "Inspect assertions:"
  log "  ${ARTIFACT_DIR}/on/assertions.json"
  log "  ${ARTIFACT_DIR}/off/assertions.json"
}

main "$@"
