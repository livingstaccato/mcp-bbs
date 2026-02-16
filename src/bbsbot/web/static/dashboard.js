// BBSBot Swarm Dashboard - WebSocket client with log viewer
(function () {
  "use strict";

  let sortKey = "bot_id";
  let sortReverse = false;
  let lastData = null;
  let updateTimer = null;  // Debounce timer for table updates
  let tablePointerActive = false;
  let pendingTableData = null;
  let tablePointerReleaseTimer = null;
  const TABLE_POINTER_RELEASE_GRACE_MS = 90;
  let swarmPingTimer = null;
  let swarmPollTimer = null;
  const strategyCptRegistry = new Map();
  const runMetricHistory = [];
  const RUN_TREND_SAMPLE_INTERVAL_S = 60;
  let lastRunMetricSampleTs = 0;
  let activeRunStartTs = null;
  let lastRunTotalTurns = 0;
  let lastRunTotalBots = 0;
  let runHistoryHydrated = false;
  let runBaselineNetWorth = null;
  let runBaselineTurns = null;
  let runBaselineTrades = null;
  let runtimeUiTimer = null;
  let runtimeHasActiveBots = false;
  let summary15Cache = null;
  let summary15CacheTs = 0;
  let summary15Inflight = null;
  const SUMMARY15_CACHE_MS = 120000;
  const latestBotsById = new Map();
  const lastKnownCreditsByBotId = new Map();

  const $ = (sel) => document.querySelector(sel);
  const dot = $("#dot");
  const connStatus = $("#conn-status");
  const botListMeta = $("#bot-list-meta");
  const filterStateEl = $("#filter-state");
  const filterStrategyEl = $("#filter-strategy");
  const filterLayoutEl = $("#filter-layout");
  const filterSearchEl = $("#filter-search");
  const filterNoTradeEl = $("#filter-no-trade");
  const strategyFilterOptionSet = new Set();
  const TABLE_VIEW_STORAGE_KEY = "bbsbot.dashboard.table_view";
  const TABLE_VIEWS = new Set(["balanced", "compact", "trader", "ops", "full"]);
  const testRuntimeValueEl = $("#test-runtime-value");
  const testRuntimeSinceEl = $("#test-runtime-since");
  const testRuntimeFillEl = $("#test-runtime-fill");
  const runTradeAttemptsEl = $("#run-trade-attempts");
  const runTradeFailuresEl = $("#run-trade-failures");
  const runFailNoPortEl = $("#run-fail-no-port");
  const runFailNoInteractEl = $("#run-fail-no-interact");
  const runFailWrongSideEl = $("#run-fail-wrong-side");
  const runLaggardsEl = $("#run-laggards");
  const runOreNowEl = $("#run-ore-now");
  const runOrgNowEl = $("#run-org-now");
  const runEquipNowEl = $("#run-equip-now");
  const runCreditsChartSvgEl = $("#run-credits-chart-svg");
  const runResourcesChartSvgEl = $("#run-resources-chart-svg");

  function renderOrDeferTable(data) {
    if (tablePointerActive) {
      pendingTableData = data;
      return;
    }
    renderBotTable(data);
  }

  function flushDeferredTableRender() {
    if (tablePointerActive || !pendingTableData) return;
    const data = pendingTableData;
    pendingTableData = null;
    renderBotTable(data);
  }

  function installTableInteractionGuards() {
    const tbody = $("#bot-table");
    if (!tbody) return;
    const hold = () => {
      if (tablePointerReleaseTimer) {
        clearTimeout(tablePointerReleaseTimer);
        tablePointerReleaseTimer = null;
      }
      tablePointerActive = true;
    };
    const release = () => {
      if (tablePointerReleaseTimer) clearTimeout(tablePointerReleaseTimer);
      // Keep the guard active briefly after pointerup so click handlers run
      // before a deferred table flush can replace the clicked row/button.
      tablePointerReleaseTimer = setTimeout(() => {
        tablePointerReleaseTimer = null;
        tablePointerActive = false;
        flushDeferredTableRender();
      }, TABLE_POINTER_RELEASE_GRACE_MS);
    };
    tbody.addEventListener("pointerdown", hold, true);
    document.addEventListener("pointerup", release, true);
    document.addEventListener("pointercancel", release, true);
    document.addEventListener("dragend", release, true);
  }

  // --- Toast notifications ---
  let toastTimer = null;
  function showToast(msg, type) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast show " + (type || "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = "toast"; }, 3000);
  }

  // --- Formatting helpers ---
  function formatCredits(n) {
    return n.toLocaleString();
  }

  function formatUptime(s) {
    if (s < 60) return Math.floor(s) + "s";
    if (s < 3600) {
      const m = Math.floor(s / 60);
      const sec = Math.floor(s % 60);
      return m + "m" + String(sec).padStart(2, "0") + "s";
    }
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h + "h" + String(m).padStart(2, "0") + "m";
  }

  function computeBotCptPresentation(bot) {
    const turns = Number(bot.turns_executed || 0);
    const runCpt = Number(bot.credits_per_turn || 0);
    const adjCpt = Number(bot.cpt_index || 1.0);
    const baselineRaw = bot.cpt_baseline_credits;
    const baselineCredits = baselineRaw == null ? null : Number(baselineRaw);
    const baselineLocked = !!bot.cpt_baseline_locked || (isFinite(baselineCredits) && baselineCredits > 0);
    const adjustedReady = (bot.adjusted_cpt_ready !== undefined && bot.adjusted_cpt_ready !== null)
      ? !!bot.adjusted_cpt_ready
      : baselineLocked;
    const runReady = (bot.run_cpt_ready !== undefined && bot.run_cpt_ready !== null)
      ? !!bot.run_cpt_ready
      : (adjustedReady && turns > 0);
    const runText = runReady ? formatSigned(runCpt, 2) : "pending";
    const adjustedText = adjustedReady && isFinite(adjCpt) && adjCpt > 0 ? `${adjCpt.toFixed(2)}x` : "unverified";
    const adjustedDeltaPct = adjustedReady && isFinite(adjCpt) && adjCpt > 0 ? ((adjCpt - 1.0) * 100.0) : null;
    const adjustedDeltaText = adjustedDeltaPct == null ? "pending" : `${formatSigned(adjustedDeltaPct, 1)}%`;
    const baselineText = (baselineLocked && isFinite(Number(baselineCredits)) && Number(baselineCredits) > 0)
      ? `base ${formatCredits(Math.round(Number(baselineCredits)))}`
      : "base pending";
    return {
      runCpt,
      adjCpt,
      runReady,
      adjustedReady,
      baselineText,
      runText,
      adjustedText,
      adjustedDeltaText,
      runColor: runReady ? (runCptColor(runCpt) || "") : "",
      adjustedColor: adjustedReady ? (strategyCptColor(adjCpt) || "") : "",
    };
  }

  function normalizeTableView(view) {
    const value = String(view || "").trim().toLowerCase();
    return TABLE_VIEWS.has(value) ? value : "balanced";
  }

  function applyTableView(view, persist = true, rerender = true) {
    const selected = normalizeTableView(view);
    if (document.body) {
      document.body.setAttribute("data-table-view", selected);
    }
    if (filterLayoutEl && filterLayoutEl.value !== selected) {
      filterLayoutEl.value = selected;
    }
    if (persist) {
      try {
        localStorage.setItem(TABLE_VIEW_STORAGE_KEY, selected);
      } catch (_) {}
    }
    if (rerender && lastData) {
      renderOrDeferTable(lastData);
    }
  }

  function initTableView() {
    let saved = "balanced";
    try {
      saved = normalizeTableView(localStorage.getItem(TABLE_VIEW_STORAGE_KEY) || "balanced");
    } catch (_) {}
    if (filterLayoutEl && filterLayoutEl.value) {
      saved = normalizeTableView(filterLayoutEl.value);
    }
    applyTableView(saved, false, false);
  }

  function formatRelativeTime(timestamp) {
    if (!timestamp) return "N/A";
    const now = Date.now() / 1000;
    const age = now - timestamp;
    if (age < 60) return Math.floor(age) + "s ago";
    if (age < 3600) return Math.floor(age / 60) + "m ago";
    return Math.floor(age / 3600) + "h ago";
  }

  function formatRelativeStamp(timestamp) {
    if (!timestamp) return "-";
    return formatRelativeTime(timestamp);
  }

  function formatAbsoluteTime(timestamp) {
    if (!timestamp) return "-";
    return new Date(timestamp * 1000).toLocaleString();
  }

  function formatAgeSeconds(ts) {
    if (!ts) return "-";
    const age = Math.max(0, (Date.now() / 1000) - Number(ts));
    if (age < 60) return Math.floor(age) + "s ago";
    if (age < 3600) return Math.floor(age / 60) + "m ago";
    return Math.floor(age / 3600) + "h ago";
  }

  function formatClockDuration(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const hh = Math.floor(total / 3600);
    const mm = Math.floor((total % 3600) / 60);
    const ss = total % 60;
    return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  }

  function formatTimeOnly(ts) {
    if (!ts) return "-";
    return new Date(Number(ts) * 1000).toLocaleTimeString();
  }

  function renderRuntimeTick(nowS = (Date.now() / 1000)) {
    const runtimeSec = (activeRunStartTs && runtimeHasActiveBots) ? Math.max(0, nowS - activeRunStartTs) : 0;
    if (testRuntimeValueEl) testRuntimeValueEl.textContent = formatClockDuration(runtimeSec);
    if (testRuntimeSinceEl) testRuntimeSinceEl.textContent = activeRunStartTs ? `since ${formatTimeOnly(activeRunStartTs)}` : "since -";
    if (testRuntimeFillEl) {
      const pct = Math.max(0, Math.min(100, (runtimeSec / 3600) * 100));
      testRuntimeFillEl.style.width = `${pct.toFixed(1)}%`;
    }
  }

  function formatSigned(n, digits = 2) {
    const v = Number(n || 0);
    if (!isFinite(v)) return "-";
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(digits)}`;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function percent(v) {
    if (!isFinite(v)) return "0.0%";
    return (v * 100).toFixed(1) + "%";
  }

  function creditColor(credits) {
    const value = Number(credits);
    if (!isFinite(value) || value < 0) return "";
    // Subtle red -> green ramp tuned for early-game credit ranges.
    const min = 0;
    const max = 1500;
    const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
    const eased = t * t * (3 - 2 * t);
    const hue = 6 + (136 * eased);
    return `hsl(${hue.toFixed(1)} 60% 62%)`;
  }

  function creditGlyph() {
    return "¢";
  }

  function strategyCptColor(cpt) {
    const value = Number(cpt);
    if (!isFinite(value)) return "";
    const min = 0.4;
    const max = 1.6;
    const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
    const eased = t * t * (3 - 2 * t);
    const hue = 8 + (132 * eased);
    return `hsl(${hue.toFixed(1)} 58% 64%)`;
  }

  function runCptColor(cpt) {
    const value = Number(cpt);
    if (!isFinite(value)) return "";
    const min = -1.5;
    const max = 1.5;
    const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
    const eased = t * t * (3 - 2 * t);
    const hue = 8 + (132 * eased);
    return `hsl(${hue.toFixed(1)} 58% 64%)`;
  }

  function computeAggregateMetrics(data) {
    const bots = data.bots || [];
    let accept = 0;
    let counter = 0;
    let tooHigh = 0;
    let tooLow = 0;
    let noTrade30 = 0;
    let noTrade60 = 0;
    let noTrade90 = 0;
    let noTrade120 = 0;
    const nowS = Date.now() / 1000;
    const activeStates = new Set(["running", "recovering", "blocked"]);
    const byStrategy = new Map();

    for (const b of bots) {
      const a = Number(b.haggle_accept || 0);
      const c = Number(b.haggle_counter || 0);
      const h = Number(b.haggle_too_high || 0);
      const l = Number(b.haggle_too_low || 0);
      accept += a;
      counter += c;
      tooHigh += h;
      tooLow += l;

      const turns = Number(b.turns_executed || 0);
      const trades = Number(b.trades_executed || 0);
      if (trades === 0 && String(b.state || "") === "running") {
        if (turns >= 30) noTrade30 += 1;
        if (turns >= 60) noTrade60 += 1;
        if (turns >= 90) noTrade90 += 1;
        if (turns >= 120) noTrade120 += 1;
      }

      const cptMeta = computeBotCptPresentation(b);
      const cptIndex = Number(b.cpt_index || 1.0);
      const turnsExec = Number(b.turns_executed || 0);
      const tradesExec = Number(b.trades_executed || 0);
      const sid = (b.strategy_id || b.strategy || "unknown").toString();
      const mode = (b.strategy_mode || "unknown").toString();
      const key = `${sid}(${mode})`;
      const state = String(b.state || "").toLowerCase();
      const lastUpdate = Number(b.last_update_time || 0);
      const isFresh = lastUpdate > 0 && nowS - lastUpdate <= 120;
      if (!byStrategy.has(key)) {
        byStrategy.set(key, {
          key,
          n: 0,
          sumCpt: 0,
          sumDelta: 0,
          sumTurns: 0,
          sumTradesAll: 0,
          sumTurnsAll: 0,
          activeBots: 0,
          samplesSkipped: 0,
        });
      }
      const bucket = byStrategy.get(key);
      if (isFinite(turnsExec) && turnsExec > 0) bucket.sumTurnsAll += turnsExec;
      if (isFinite(tradesExec) && tradesExec > 0) bucket.sumTradesAll += tradesExec;
      if (activeStates.has(state) && isFresh) bucket.activeBots += 1;

      const hasValidIndex = cptMeta.adjustedReady && isFinite(cptIndex) && cptIndex > 0 && cptIndex < 100;
      if (hasValidIndex) {
        bucket.sumCpt += cptIndex;
        bucket.n += 1;
        if (isFinite(turnsExec) && turnsExec > 0) bucket.sumTurns += turnsExec;
      } else {
        bucket.samplesSkipped += 1;
      }
    }

    const offers = accept + counter + tooHigh + tooLow;
    const acceptRate = offers > 0 ? accept / offers : 0;
    const tooHighRate = offers > 0 ? tooHigh / offers : 0;
    const tooLowRate = offers > 0 ? tooLow / offers : 0;

    const strategyRows = Array.from(byStrategy.values())
      .map((v) => {
        const cpt = v.n > 0 ? v.sumCpt / v.n : 1.0;
        const tradesPer100 = v.sumTurnsAll > 0 ? (v.sumTradesAll * 100) / v.sumTurnsAll : 0;
        return {
          key: v.key,
          cpt,
          n: v.n,
          turns: v.sumTurns,
          tradesPer100,
          activeNow: v.activeBots > 0,
          lowConfidence: v.n < 3 || v.sumTurns < 200,
          samplesSkipped: v.samplesSkipped || 0,
        };
      })
      .filter((x) => !(x.key.toLowerCase().includes("(unknown)") && x.n === 0 && x.tradesPer100 === 0))
      .sort((a, b) => b.cpt - a.cpt);

    return { acceptRate, tooHighRate, tooLowRate, noTrade30, noTrade60, noTrade90, noTrade120, strategyRows };
  }

  function renderStrategyCpt(rowsNow) {
    const strategyEl = $("#strategy-cpt");
    if (!strategyEl) return;

    const nowS = Date.now() / 1000;
    const seen = new Set();
    for (const row of (rowsNow || [])) {
      const key = String(row.key || "").trim();
      if (!key) continue;
      seen.add(key);
      const prev = strategyCptRegistry.get(key) || {};
      strategyCptRegistry.set(key, {
        ...prev,
        key,
        cpt: Number(row.cpt || 0),
        n: Number(row.n || 0),
        turns: Number(row.turns || 0),
        tradesPer100: Number(row.tradesPer100 || 0),
        lowConfidence: !!row.lowConfidence,
        samplesSkipped: Number(row.samplesSkipped || 0),
        activeNow: !!row.activeNow,
        lastSeen: nowS,
      });
    }

    for (const [key, rec] of strategyCptRegistry.entries()) {
      if (seen.has(key)) continue;
      strategyCptRegistry.set(key, { ...rec, activeNow: false });
    }

    const stateRank = { ACTIVE: 0, WARM: 1, FADED: 2 };
    const rows = Array.from(strategyCptRegistry.values())
      .map((rec) => {
        const age = Math.max(0, nowS - Number(rec.lastSeen || nowS));
        let state = "FADED";
        if (rec.activeNow && age <= 20) state = "ACTIVE";
        else if (age <= 180) state = "WARM";
        return { ...rec, age, state };
      })
      .sort((a, b) => {
        const sr = (stateRank[a.state] ?? 9) - (stateRank[b.state] ?? 9);
        if (sr !== 0) return sr;
        const c = Number(b.cpt || 0) - Number(a.cpt || 0);
        if (c !== 0) return c;
        return Number(b.lastSeen || 0) - Number(a.lastSeen || 0);
      })
      .slice(0, 24);

    if (!rows.length) {
      strategyEl.textContent = "-";
      return;
    }

    strategyEl.innerHTML = `
      <div class="strategy-cpt-table-wrap">
        <table class="strategy-cpt-table">
          <thead>
            <tr>
              <th>Strategy</th>
              <th>CPT Index</th>
              <th>N</th>
              <th>Turns</th>
              <th>T/100</th>
              <th>State</th>
              <th>Age</th>
            </tr>
          </thead>
          <tbody>
            ${rows
              .map((row) => {
                const cpt = Number(row.cpt || 0);
                const cptText = `${cpt.toFixed(2)}x`;
                const t100 = Number(row.tradesPer100 || 0).toFixed(1);
                const color = strategyCptColor(cpt);
                const stateCls = row.state.toLowerCase();
                const parsed = parseStrategyKey(row.key);
                const sid = strategyLabelFull(parsed.id || "unknown");
                const mode = strategyLabelFull(parsed.mode || "unknown");
                const title = `${row.key} | n=${row.n} | turns=${row.turns}${row.samplesSkipped ? ` | skip=${row.samplesSkipped}` : ""}`;
                return `
                  <tr class="strategy-cpt-row ${stateCls}${row.lowConfidence ? " low-confidence" : ""}" title="${esc(title)}">
                    <td class="strategy-key">
                      <div class="strategy-key-block">
                        <span class="strategy-chip-row">
                          <span class="chip sid">${esc(sid)}</span>
                          <span class="chip mode">${esc(mode)}</span>
                        </span>
                      </div>
                    </td>
                    <td class="strategy-cpt-num"${color ? ` style="color:${color}"` : ""}>${esc(cptText)}</td>
                    <td class="strategy-n">${esc(String(row.n))}</td>
                    <td class="strategy-turns">${esc(formatCredits(Math.round(Number(row.turns || 0))))}</td>
                    <td class="strategy-t100">${esc(t100)}</td>
                    <td><span class="strategy-state strategy-state-${stateCls}">${esc(row.state)}</span></td>
                    <td class="strategy-age">${esc(formatAgeSeconds(row.lastSeen))}</td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function computeRunMetrics(data) {
    const bots = data.bots || [];
    const liveStates = new Set(["running", "recovering", "blocked", "queued"]);
    const includeStates = new Set(["running", "recovering", "blocked", "queued", "completed", "error", "disconnected"]);
    let turns = 0;
    let trades = 0;
    let runStart = Number.POSITIVE_INFINITY;
    let activeBots = 0;
    let totalNetWorth = Number(data.total_net_worth_estimate || 0);
    let totalLiquid = Number(data.total_credits || 0);
    let totalBanked = Number(data.total_bank_credits || 0);
    let totalCargoFuelOre = 0;
    let totalCargoOrganics = 0;
    let totalCargoEquipment = 0;
    let tradeAttempts = 0;
    let tradeSuccesses = 0;
    let failNoPort = 0;
    let failNoInteraction = 0;
    let failWrongSide = 0;
    let failOther = 0;
    let laggards = 0;
    let combatSeen = 0;
    let underAttackReports = 0;
    let unknownDelta = 0;
    let combatDelta = 0;
    let attritionCredits = 0;
    let oppSeen = 0;
    let oppExecuted = 0;
    let blockedUnknownSide = 0;
    let blockedNoPort = 0;
    let blockedLowScore = 0;
    let blockedBudgetExhausted = 0;
    let rerouteWrongSide = 0;
    let rerouteNoPort = 0;
    let rerouteNoInteraction = 0;
    let verifiedLanes = 0;
    let acceptRateHint = 0;

    for (const b of bots) {
      const state = String(b.state || "").toLowerCase();
      if (!includeStates.has(state)) continue;
      turns += Number(b.turns_executed || 0);
      trades += Number(b.trades_executed || 0);
      totalCargoFuelOre += Number(b.cargo_fuel_ore || 0);
      totalCargoOrganics += Number(b.cargo_organics || 0);
      totalCargoEquipment += Number(b.cargo_equipment || 0);
      tradeAttempts += Number(b.trade_attempts || 0);
      tradeSuccesses += Number(b.trade_successes || 0);
      const turnsExec = Number(b.turns_executed || 0);
      const tradesExec = Number(b.trades_executed || 0);
      if (turnsExec >= 80 && tradesExec <= 1) laggards += 1;
      const fr = b.trade_failure_reasons || {};
      failNoPort += Number(fr.trade_fail_no_port || 0);
      failNoInteraction += Number(fr.trade_fail_no_interaction || 0);
      failWrongSide += Number(fr.trade_fail_wrong_side || 0);
      failOther += Number(fr.trade_fail_other || 0);
      const combat = b.combat_telemetry || {};
      const attrition = b.attrition_telemetry || {};
      const opp = b.opportunity_telemetry || {};
      const tq = b.trade_quality_runtime || {};
      const deltaAttr = b.delta_attribution_telemetry || {};
      combatSeen += Number(combat.combat_context_seen || 0);
      underAttackReports += Number(combat.under_attack_reports || 0);
      unknownDelta += Number(deltaAttr.delta_unknown || 0);
      combatDelta += Number(deltaAttr.delta_combat || 0);
      attritionCredits += Number(attrition.credits_loss_nontrade || 0);
      oppSeen += Number(opp.opportunities_seen || 0);
      oppExecuted += Number(opp.opportunities_executed || 0);
      blockedUnknownSide += Number(tq.blocked_unknown_side || 0);
      blockedNoPort += Number(tq.blocked_no_port || 0);
      blockedLowScore += Number(tq.blocked_low_score || 0);
      blockedBudgetExhausted += Number(tq.blocked_budget_exhausted || 0);
      rerouteWrongSide += Number(tq.reroute_wrong_side || 0);
      rerouteNoPort += Number(tq.reroute_no_port || 0);
      rerouteNoInteraction += Number(tq.reroute_no_interaction || 0);
      verifiedLanes += Number(tq.verified_lanes_count || 0);
      acceptRateHint += Number(tq.opportunity_score_avg_accepted || 0);
      if (!liveStates.has(state)) continue;
      activeBots += 1;
      const started = Number(b.started_at || 0);
      if (started > 0 && started < runStart) runStart = started;
    }

    return {
      runStart: isFinite(runStart) ? runStart : null,
      turns,
      trades,
      activeBots,
      totalNetWorth,
      totalLiquid,
      totalBanked,
      totalCargoFuelOre,
      totalCargoOrganics,
      totalCargoEquipment,
      tradeAttempts,
      tradeSuccesses,
      failNoPort,
      failNoInteraction,
      failWrongSide,
      failOther,
      laggards,
      combatSeen,
      underAttackReports,
      unknownDelta,
      combatDelta,
      attritionCredits,
      oppSeen,
      oppExecuted,
      blockedUnknownSide,
      blockedNoPort,
      blockedLowScore,
      blockedBudgetExhausted,
      rerouteWrongSide,
      rerouteNoPort,
      rerouteNoInteraction,
      verifiedLanes,
      acceptRateHint,
    };
  }

  function computeRunDeltas(run) {
    const baseCredits = Number(runBaselineNetWorth != null ? runBaselineNetWorth : run.totalNetWorth);
    const baseTurns = Number(runBaselineTurns != null ? runBaselineTurns : run.turns);
    const baseTrades = Number(runBaselineTrades != null ? runBaselineTrades : run.trades);
    const deltaTurns = Math.max(0, Number(run.turns || 0) - baseTurns);
    const deltaTrades = Math.max(0, Number(run.trades || 0) - baseTrades);
    const deltaCredits = Number(run.totalNetWorth || 0) - baseCredits;
    const trueCpt = deltaTurns > 0 ? (deltaCredits / deltaTurns) : 0;
    const tradesPer100 = deltaTurns > 0 ? ((deltaTrades * 100) / deltaTurns) : 0;
    const returnPerTrade = deltaTrades > 0 ? (deltaCredits / deltaTrades) : 0;
    return { deltaTurns, deltaTrades, deltaCredits, trueCpt, tradesPer100, returnPerTrade };
  }

  function computeRecentRunDeltas(fallback, windowSeconds = 900) {
    const tail = runMetricHistory.slice(-240);
    if (!Array.isArray(tail) || tail.length < 2) return fallback;

    const end = tail[tail.length - 1];
    const endTs = Number(end.ts || 0);
    if (!isFinite(endTs) || endTs <= 0) return fallback;

    const cutoff = endTs - Math.max(60, Number(windowSeconds || 900));
    let start = tail[0];
    for (let i = tail.length - 2; i >= 0; i--) {
      const ts = Number(tail[i].ts || 0);
      if (ts <= cutoff) {
        start = tail[i];
        break;
      }
      start = tail[i];
    }

    const deltaTurns = Number(end.turns || 0) - Number(start.turns || 0);
    if (!isFinite(deltaTurns) || deltaTurns <= 0) return fallback;
    const deltaTrades = Math.max(0, Number(end.trades || 0) - Number(start.trades || 0));
    const endNetWorth = Number(
      end.netWorth != null ? end.netWorth : (Number(end.credits || 0) + Number(end.banked || 0))
    );
    const startNetWorth = Number(
      start.netWorth != null ? start.netWorth : (Number(start.credits || 0) + Number(start.banked || 0))
    );
    const deltaCredits = endNetWorth - startNetWorth;
    const trueCpt = deltaCredits / deltaTurns;
    const tradesPer100 = (deltaTrades * 100) / deltaTurns;
    const returnPerTrade = deltaTrades > 0 ? (deltaCredits / deltaTrades) : 0;
    return { deltaTurns, deltaTrades, deltaCredits, trueCpt, tradesPer100, returnPerTrade };
  }

  async function refreshSummary15(force = false) {
    const nowMs = Date.now();
    if (!force && summary15Cache && (nowMs - summary15CacheTs) < SUMMARY15_CACHE_MS) {
      return summary15Cache;
    }
    if (summary15Inflight) return summary15Inflight;
    summary15Inflight = fetch("/swarm/timeseries/summary?window_minutes=15")
      .then((resp) => (resp.ok ? resp.json() : null))
      .then((data) => {
        summary15Cache = data;
        summary15CacheTs = Date.now();
        return data;
      })
      .catch(() => summary15Cache)
      .finally(() => {
        summary15Inflight = null;
      });
    return summary15Inflight;
  }

  function canonicalDisplayDelta(localDelta) {
    const delta = (summary15Cache && summary15Cache.delta) ? summary15Cache.delta : null;
    if (!delta) return localDelta;
    const turns = Number(delta.turns || 0);
    if (!isFinite(turns) || turns <= 0) return localDelta;
    const nwpt = Number(delta.net_worth_per_turn || 0);
    const t100 = Number(delta.trades_per_100_turns || 0);
    const trades = Number(delta.trades_executed || 0);
    const netWorthDelta = Number(delta.net_worth_estimate || 0);
    const rpt = trades > 0 ? (netWorthDelta / trades) : 0;
    return {
      deltaTurns: turns,
      deltaTrades: trades,
      deltaCredits: netWorthDelta,
      trueCpt: nwpt,
      tradesPer100: t100,
      returnPerTrade: rpt,
      roiConfidence: Number(delta.roi_confidence || 0),
      roiLowConfidence: !!delta.roi_low_confidence,
      roiConfidenceReasons: Array.isArray(delta.roi_confidence_reasons) ? delta.roi_confidence_reasons : [],
    };
  }

  async function hydrateRunHistoryFromTimeseries() {
    if (runHistoryHydrated || runMetricHistory.length > 1) return;
    runHistoryHydrated = true;
    try {
      const resp = await fetch("/swarm/timeseries/recent?limit=180");
      if (!resp.ok) return;
      const payload = await resp.json();
      const rows = Array.isArray(payload.rows) ? payload.rows : [];
      if (rows.length < 2) return;
      rows.sort((a, b) => Number(a.ts || 0) - Number(b.ts || 0));
      const first = rows[0];
      const baseTurns = Number(first.total_turns || 0);
      const baseTrades = Number(((first.trade_outcomes_overall || {}).trades_executed) || 0);
      let lastKeepTs = 0;
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const rowTs = Number(row.ts || 0);
        const isLast = i === (rows.length - 1);
        if (!isLast && lastKeepTs > 0 && (rowTs - lastKeepTs) < RUN_TREND_SAMPLE_INTERVAL_S) {
          continue;
        }
        const turns = Number(row.total_turns || 0);
        const credits = Number(row.total_credits || 0);
        const banked = Number(row.total_bank_credits || 0);
        const trades = Number(((row.trade_outcomes_overall || {}).trades_executed) || 0);
        const deltaTurns = turns >= baseTurns ? (turns - baseTurns) : turns;
        const deltaTrades = trades >= baseTrades ? (trades - baseTrades) : trades;
        runMetricHistory.push({
          ts: Number(row.ts || 0),
          turns: deltaTurns,
          trades: deltaTrades,
          netWorth: Number(row.total_net_worth_estimate || 0),
          credits,
          banked,
          fuelOre: Number(row.total_cargo_fuel_ore || 0),
          organics: Number(row.total_cargo_organics || 0),
          equipment: Number(row.total_cargo_equipment || 0),
        });
        lastKeepTs = rowTs;
      }
      while (runMetricHistory.length > 240) runMetricHistory.shift();
      const last = runMetricHistory[runMetricHistory.length - 1];
      if (last) lastRunMetricSampleTs = Number(last.ts || 0);
    } catch (_) {
      // Optional hydration: ignore errors and rely on live samples.
    }
  }

  function renderRunTrend(runtimeSec, metrics) {
    const _ = runtimeSec;
    const blockedUnknownSide = Number(metrics.blockedUnknownSide || 0);
    const blockedNoPort = Number(metrics.blockedNoPort || 0);
    const blockedLowScore = Number(metrics.blockedLowScore || 0);
    const blockedBudgetExhausted = Number(metrics.blockedBudgetExhausted || 0);
    const rerouteWrongSide = Number(metrics.rerouteWrongSide || 0);
    const rerouteNoPort = Number(metrics.rerouteNoPort || 0);
    const rerouteNoInteraction = Number(metrics.rerouteNoInteraction || 0);
    const verifiedLanes = Number(metrics.verifiedLanes || 0);
    const oppSeen = Number(metrics.oppSeen || 0);
    const oppExecuted = Number(metrics.oppExecuted || 0);
    const acceptRate = oppSeen > 0 ? (oppExecuted * 100.0 / oppSeen) : 0;

    if (runTradeAttemptsEl) {
      runTradeAttemptsEl.textContent = formatCredits(Math.round(blockedUnknownSide));
      runTradeAttemptsEl.style.color = blockedUnknownSide > 0 ? "var(--yellow)" : "var(--fg-dim)";
    }
    if (runTradeFailuresEl) {
      runTradeFailuresEl.textContent = formatCredits(Math.round(blockedNoPort));
      runTradeFailuresEl.style.color = blockedNoPort > 0 ? "var(--red)" : "var(--fg-dim)";
    }
    if (runFailNoPortEl) {
      runFailNoPortEl.textContent = formatCredits(Math.round(blockedLowScore));
      runFailNoPortEl.style.color = blockedLowScore > 0 ? "var(--yellow)" : "var(--fg-dim)";
    }
    if (runFailNoInteractEl) {
      runFailNoInteractEl.textContent = formatCredits(Math.round(blockedBudgetExhausted));
      runFailNoInteractEl.style.color = blockedBudgetExhausted > 0 ? "var(--yellow)" : "var(--fg-dim)";
    }
    if (runFailWrongSideEl) {
      runFailWrongSideEl.textContent = formatCredits(Math.round(verifiedLanes));
      runFailWrongSideEl.style.color = verifiedLanes > 0 ? "var(--green)" : "var(--fg-dim)";
    }
    if (runLaggardsEl) {
      runLaggardsEl.textContent = `${acceptRate.toFixed(1)}%`;
      runLaggardsEl.style.color = acceptRate >= 50 ? "var(--green)" : (acceptRate >= 20 ? "var(--yellow)" : "var(--red)");
    }

    const resourceRows = [
      { el: runOreNowEl, value: Number(metrics.totalCargoFuelOre || 0) },
      { el: runOrgNowEl, value: Number(metrics.totalCargoOrganics || 0) },
      { el: runEquipNowEl, value: Number(metrics.totalCargoEquipment || 0) },
    ];
    for (const row of resourceRows) {
      if (!row.el) continue;
      const v = Math.max(0, Math.round(Number(row.value || 0)));
      row.el.textContent = formatCredits(v);
      row.el.classList.remove("empty", "has");
      row.el.classList.add(v > 0 ? "has" : "empty");
    }

    const tail = runMetricHistory.slice(-180);
    renderRunChart(runCreditsChartSvgEl, tail, [
      { key: "credits", label: "Credits", lineClass: "run-chart-line-credits", dotClass: "run-chart-dot-credits", minSpan: 30 },
      { key: "banked", label: "Banked", lineClass: "run-chart-line-banked", dotClass: "run-chart-dot-banked", minSpan: 10 },
    ]);
    renderRunChart(runResourcesChartSvgEl, tail, [
      { key: "fuelOre", label: "Ore", lineClass: "run-chart-line-ore", dotClass: "run-chart-dot-ore", minSpan: 2 },
      { key: "organics", label: "Org", lineClass: "run-chart-line-org", dotClass: "run-chart-dot-org", minSpan: 2 },
      { key: "equipment", label: "Equip", lineClass: "run-chart-line-equip", dotClass: "run-chart-dot-equip", minSpan: 2 },
    ]);
  }

  function robustBounds(values, zeroRef, minSpan) {
    const vals = values.filter((v) => isFinite(v)).slice().sort((a, b) => a - b);
    if (!vals.length) return [zeroRef - (minSpan / 2), zeroRef + (minSpan / 2)];
    const q = (p) => vals[Math.max(0, Math.min(vals.length - 1, Math.floor((vals.length - 1) * p)))];
    let lo = Math.min(q(0.05), zeroRef);
    let hi = Math.max(q(0.95), zeroRef);
    if ((hi - lo) < minSpan) {
      const mid = (hi + lo) / 2;
      lo = mid - (minSpan / 2);
      hi = mid + (minSpan / 2);
    }
    return [lo, hi];
  }

  function renderRunChart(svgEl, tail, series) {
    if (!svgEl) return;
    if (!Array.isArray(tail) || tail.length < 2) {
      const emptyW = Math.max(420, Math.round((svgEl.clientWidth || 0)));
      const emptyH = Math.max(48, Math.round((svgEl.clientHeight || 0)));
      svgEl.setAttribute("viewBox", `0 0 ${emptyW} ${emptyH}`);
      svgEl.setAttribute("preserveAspectRatio", "none");
      svgEl.innerHTML = `<text x="${(emptyW / 2).toFixed(1)}" y="${(emptyH / 2).toFixed(1)}" text-anchor="middle" class="run-chart-empty">Collecting run samples...</text>`;
      return;
    }
    const w = Math.max(420, Math.round(svgEl.clientWidth || 0));
    const h = Math.max(48, Math.round(svgEl.clientHeight || 0));
    svgEl.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svgEl.setAttribute("preserveAspectRatio", "none");
    const padX = Math.max(10, Math.round(w * 0.02));
    const padY = Math.max(8, Math.round(h * 0.16));
    const n = tail.length;
    const xAt = (i) => padX + (((w - (padX * 2)) * (n <= 1 ? 0 : i / (n - 1))));
    const parts = [];
    const labelStep = Math.max(12, Math.round((h - (padY * 2)) / Math.max(1, series.length)));

    for (let idx = 0; idx < series.length; idx++) {
      const lane = series[idx];
      const values = tail.map((entry) => Number(entry[lane.key] || 0));
      const baselineRef = values.length ? Number(values[0] || 0) : 0;
      const [minV, maxV] = robustBounds(values, baselineRef, Number(lane.minSpan || 2));
      const span = Math.max(0.0001, maxV - minV);
      const yAt = (v) => padY + (((maxV - v) / span) * (h - (padY * 2)));
      const points = values.map((v, i) => `${xAt(i).toFixed(2)},${yAt(v).toFixed(2)}`);
      const baselineY = yAt(baselineRef).toFixed(2);
      const lastX = xAt(n - 1).toFixed(2);
      const lastY = yAt(values[n - 1]).toFixed(2);
      const lastVal = Math.round(values[n - 1] || 0);
      const labelY = (padY + 2 + (idx * labelStep));

      parts.push(`<line class="run-chart-baseline" x1="${padX}" y1="${baselineY}" x2="${(w - padX)}" y2="${baselineY}"></line>`);
      parts.push(`<polyline class="run-chart-line ${lane.lineClass}" points="${points.join(" ")}"></polyline>`);
      parts.push(`<circle class="run-chart-dot ${lane.dotClass}" cx="${lastX}" cy="${lastY}"></circle>`);
      parts.push(`<text class="run-chart-label" x="${padX + 1}" y="${labelY.toFixed(2)}">${esc(String(lane.label))}</text>`);
      parts.push(`<text class="run-chart-label" text-anchor="end" x="${w - padX - 1}" y="${labelY.toFixed(2)}">${esc(formatCredits(lastVal))}</text>`);
    }

    svgEl.innerHTML = parts.join("");
  }

  function shortBotId(botId) {
    const s = String(botId || "");
    if (s.length <= 14) return s;
    return s.slice(0, 6) + "…" + s.slice(-6);
  }

  function getActivityBadge(context) {
    if (!context) return "IDLE";
    const lower = context.toLowerCase();
    // Simplify activity names (no emojis)
    if (lower.includes("trading") || lower.includes("bank")) return "TRADING";
    if (lower.includes("retreat") || lower.includes("evad")) return "EVADING";
    if (lower.includes("battle") || lower.includes("combat")) return "BATTLING";
    if (lower.includes("attack") || lower.includes("threat")) return "BATTLING";
    if (lower.includes("explore") || lower.includes("navigation") || lower.includes("warp")) return "EXPLORING";
    if (lower.includes("thinking")) return "THINKING";
    if (lower.includes("orienting")) return context.replace("ORIENTING: ", "Orient: ");
    if (lower.includes("upgrading")) return "UPGRADING";
    if (lower.includes("sector_command")) return "AT PROMPT";
    if (lower.includes("port")) return "AT PORT";
    if (lower.includes("planet")) return "AT PLANET";
    if (lower.includes("queued")) return "QUEUED";
    if (lower.includes("disconnected")) return "DISCONNECTED";
    return context.toUpperCase();
  }

  function getActivityClass(activity) {
    const lower = (activity || "").toLowerCase();
    if (lower.includes("trade")) return "trading";
    if (lower.includes("battle")) return "battling";
    if (lower.includes("evad")) return "battling";
    if (lower.includes("explore")) return "exploring";
    if (lower.includes("orient")) return "orienting";
    if (lower.includes("select")) return "selecting";
    if (lower.includes("log") || lower.includes("connect")) return "connecting";
    if (lower.includes("block")) return "blocked";
    if (lower.includes("recover")) return "recovering";
    if (lower.includes("disconnect")) return "dead";
    if (lower.includes("queue")) return "queued";
    if (lower.includes("completed") || lower.includes("error") || lower.includes("stopped")) return "dead";
    return "idle";
  }

  function compactStatusText(status) {
    const raw = String(status || "").trim();
    if (!raw || raw === "-") return "";
    const normalized = raw
      .replaceAll(" | ", " · ")
      .replace(/\bRECOVERING\b/g, "REC")
      .replace(/\bDISCONNECTED\b/g, "DISC")
      .replace(/\bCOMPLETED\b/g, "DONE")
      .replace(/\bHIJACKED\b/g, "HJK")
      .replace(/\bORIENTING:/g, "ORI:")
      .replace(/\bprompt\./g, "");
    const limit = 34;
    if (normalized.length <= limit) return normalized;
    return `${normalized.slice(0, limit - 1)}…`;
  }

  function getStrategyLabel(bot) {
    const strategy =
      (bot.strategy && String(bot.strategy).trim()) ||
      ((bot.strategy_id ? String(bot.strategy_id).trim() : "") +
        (bot.strategy_mode ? `(${String(bot.strategy_mode).trim()})` : ""));
    return strategy || "-";
  }

  function parseStrategyKey(key) {
    const raw = String(key || "").trim();
    const m = raw.match(/^([^()]+?)(?:\(([^)]+)\))?$/);
    if (!m) return { id: raw || "unknown", mode: "" };
    return {
      id: String(m[1] || "").trim() || "unknown",
      mode: String(m[2] || "").trim(),
    };
  }

  function strategyLabelFull(token) {
    return String(token || "")
      .replace(/_/g, " ")
      .trim();
  }

  function getStrategyCompact(bot) {
    const rawId = String(bot.strategy_id || bot.strategy || "").trim();
    const rawMode = String(bot.strategy_mode || "").trim();
    const id = rawId ? rawId.toUpperCase() : "-";
    const mode = ({
      conservative: "con",
      balanced: "bal",
      aggressive: "agg",
      unknown: "unk",
    }[rawMode] || rawMode || "");
    return { id, mode, full: getStrategyLabel(bot) };
  }

  function getStrategyNote(bot) {
    const candidates = [
      bot.strategy_intent,
      bot.strategy_note,
      bot.strategy_reason,
      bot.last_trade_note,
      bot.last_action,
    ];
    for (const candidate of candidates) {
      const note = String(candidate || "").trim();
      if (note) return note;
    }
    return "";
  }

  function normalizeStrategyToken(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function getLatestRecentAction(bot) {
    const actions = Array.isArray(bot.recent_actions) ? bot.recent_actions : [];
    let latest = null;
    let latestTime = -1;
    for (const raw of actions) {
      if (!raw || typeof raw !== "object") continue;
      const actionTime = Number(raw.time || 0);
      if (latest === null || actionTime >= latestTime) {
        latest = raw;
        latestTime = actionTime;
      }
    }
    return latest;
  }

  function formatDecisionSourceLabel(source) {
    const normalized = normalizeStrategyToken(source);
    switch (normalized) {
      case "llm_managed":
        return "llm-managed";
      case "llm_direct":
        return "llm-direct";
      case "supervisor_autopilot":
        return "autopilot";
      case "goal_contract":
        return "goal-contract";
      case "fallback":
        return "fallback";
      default:
        return String(source || "")
          .trim()
          .replace(/_/g, "-");
    }
  }

  function getAiDecisionInfo(bot) {
    const strategyNorm = normalizeStrategyToken(bot.strategy_id || bot.strategy || "");
    const roleNorm = normalizeStrategyToken(bot.swarm_role || "");
    const latest = getLatestRecentAction(bot);
    const decisionSource = String((latest && latest.decision_source) || "").trim();
    const sourceNorm = normalizeStrategyToken(decisionSource);
    const sourceLooksAi = (
      sourceNorm.startsWith("llm")
      || sourceNorm === "supervisor_autopilot"
      || sourceNorm === "goal_contract"
      || sourceNorm === "fallback"
    );
    const latestAction = String((latest && latest.action) || "").trim().toUpperCase();
    const isAi = (
      strategyNorm === "ai_strategy"
      || strategyNorm === "ai"
      || latestAction.startsWith("AI:")
      || sourceLooksAi
      || (roleNorm === "ai" && sourceLooksAi)
    );
    if (!isAi) return { isAi: false, summary: "", detail: "", tooltip: "" };

    const selectedStrategy = String(
      (latest && (latest.strategy_id || latest.strategy))
      || bot.strategy_id
      || bot.strategy
      || "unknown"
    ).trim();
    const sourceLabel = formatDecisionSourceLabel(decisionSource || "managed");
    const wakeReason = String((latest && latest.wake_reason) || "").trim();
    const reviewTurns = Number(latest && latest.review_after_turns);
    const summaryParts = [`AI ${sourceLabel}`, `-> ${selectedStrategy}`];
    if (wakeReason) summaryParts.push(`wake=${wakeReason}`);
    if (Number.isFinite(reviewTurns) && reviewTurns > 0) summaryParts.push(`review=${Math.round(reviewTurns)}t`);
    const summary = summaryParts.join(" | ");

    const reason = String((latest && (latest.why || latest.details)) || "").trim();
    const actionLabel = latestAction ? latestAction.replace(/^AI:/, "") : "";
    const detailParts = [];
    if (actionLabel) detailParts.push(`act=${actionLabel}`);
    if (reason) detailParts.push(reason);
    const detail = detailParts.join(" | ");

    const tooltipParts = [summary];
    if (detail) tooltipParts.push(detail);
    if (latest && latest.time) tooltipParts.push(`updated ${formatRelativeStamp(latest.time)}`);
    return {
      isAi: true,
      summary,
      detail,
      tooltip: tooltipParts.join(" | "),
    };
  }

  function matchesTextFilter(bot, q) {
    if (!q) return true;
    const fields = [
      bot.bot_id,
      bot.state,
      bot.activity_context,
      bot.status_detail,
      bot.hostile_fighters,
      bot.under_attack,
      bot.prompt_id,
      bot.strategy,
      bot.strategy_id,
      bot.strategy_mode,
      bot.strategy_intent,
      bot.sector,
    ];
    return fields.some((f) => String(f || "").toLowerCase().includes(q));
  }

  function noTrade120(bot) {
    const turns = Number(bot.turns_executed || 0);
    const trades = Number(bot.trades_executed || 0);
    return turns >= 120 && trades === 0 && String(bot.state || "") === "running";
  }

  function syncStrategyFilterOptions(bots) {
    if (!filterStrategyEl) return;
    const labels = Array.from(
      new Set(
        bots
          .map((b) => getStrategyLabel(b))
          .filter((v) => v && v !== "-")
      )
    ).sort((a, b) => a.localeCompare(b));

    let changed = false;
    for (const label of labels) {
      if (strategyFilterOptionSet.has(label)) continue;
      const opt = document.createElement("option");
      opt.value = label;
      opt.textContent = `strategy: ${label}`;
      filterStrategyEl.appendChild(opt);
      strategyFilterOptionSet.add(label);
      changed = true;
    }
    if (!changed && filterStrategyEl.options.length > 1) return;
  }

  function applyFilters(bots) {
    const stateFilter = filterStateEl ? String(filterStateEl.value || "all") : "all";
    const strategyFilter = filterStrategyEl ? String(filterStrategyEl.value || "all") : "all";
    const searchFilter = filterSearchEl ? String(filterSearchEl.value || "").trim().toLowerCase() : "";
    const noTradeFilter = !!(filterNoTradeEl && filterNoTradeEl.checked);

    return bots.filter((bot) => {
      if (stateFilter !== "all" && String(bot.state || "") !== stateFilter) return false;
      if (strategyFilter !== "all" && getStrategyLabel(bot) !== strategyFilter) return false;
      if (noTradeFilter && !noTrade120(bot)) return false;
      if (!matchesTextFilter(bot, searchFilter)) return false;
      return true;
    });
  }

  // --- Bot table rendering ---
	  function update(data) {
      refreshSummary15();
	    lastData = data;
      latestBotsById.clear();
      for (const b of (data.bots || [])) {
        const botId = String((b && b.bot_id) || "");
        if (botId) latestBotsById.set(botId, b);
        const credits = Number((b && b.credits) ?? -1);
        if (botId && isFinite(credits) && credits >= 0) {
          lastKnownCreditsByBotId.set(botId, credits);
        }
      }
	    // Update stats immediately (lightweight)
	    $("#running").textContent = data.running;
	    $("#total").textContent = data.total_bots;
      $("#completed").textContent = data.completed;
      $("#errors").textContent = data.errors;
      const totalCredits = Number(data.total_credits || 0);
      const totalBankCredits = Number(data.total_bank_credits || 0);
      const totalNetWorth = Number(data.total_net_worth_estimate ?? totalCredits);
      const netWorthEl = $("#net-worth");
      if (netWorthEl) netWorthEl.textContent = formatCredits(totalNetWorth);
      const creditsSubEl = $("#credits-sub");
      if (creditsSubEl) {
        creditsSubEl.textContent = `liquid ${formatCredits(totalCredits)} · bank ${formatCredits(totalBankCredits)}`;
        const avgPerBot = Number(data.total_bots || 0) > 0
          ? ((totalCredits + totalBankCredits) / Number(data.total_bots || 1))
          : (totalCredits + totalBankCredits);
        creditsSubEl.style.color = creditColor(avgPerBot) || "";
      }
      const legacyCreditsEl = $("#credits");
      if (legacyCreditsEl) legacyCreditsEl.textContent = formatCredits(totalCredits);
	    $("#turns").textContent = formatCredits(data.total_turns);
      const run = computeRunMetrics(data);

      const returnPerTurnEl = $("#return-per-turn");
      const returnPerTradeEl = $("#return-per-trade");
      const tradeSuccessSubEl = $("#trade-success-sub");
      const tradesPer100El = $("#trades-per-100");
      const profitableRateSubEl = $("#profitable-rate-sub");
      const runDelta = computeRunDeltas(run);
      let displayDelta = computeRecentRunDeltas(runDelta);
      displayDelta = canonicalDisplayDelta(displayDelta);
      if (returnPerTurnEl) {
        const cptText = formatSigned(displayDelta.trueCpt, 2);
        returnPerTurnEl.textContent = displayDelta.roiLowConfidence ? `~${cptText}` : cptText;
        returnPerTurnEl.style.color = runCptColor(displayDelta.trueCpt) || "";
        if (displayDelta.roiLowConfidence) {
          const reasons = (displayDelta.roiConfidenceReasons || []).join(", ") || "insufficient data quality";
          returnPerTurnEl.title = `Low confidence ROI (${Number(displayDelta.roiConfidence || 0).toFixed(2)}): ${reasons}`;
        } else {
          returnPerTurnEl.title = "";
        }
      }
      if (returnPerTradeEl) {
        const summaryDelta = (summary15Cache && summary15Cache.delta) ? summary15Cache.delta : null;
        const summarySuccessRate = summaryDelta ? Number(summaryDelta.trade_success_rate || 0) : NaN;
        const successRate = isFinite(summarySuccessRate)
          ? summarySuccessRate
          : (Number(run.tradeAttempts || 0) > 0
            ? (Number(run.tradeSuccesses || 0) / Number(run.tradeAttempts || 1))
            : 0);
        returnPerTradeEl.textContent = `${(successRate * 100).toFixed(1)}%`;
        returnPerTradeEl.style.color = successRate >= 0.4 ? "var(--green)" : (successRate >= 0.15 ? "var(--yellow)" : "var(--red)");
        if (tradeSuccessSubEl) {
          const attempts = summaryDelta ? Number(summaryDelta.trade_attempts || 0) : Number(run.tradeAttempts || 0);
          const successes = summaryDelta ? Number(summaryDelta.trade_successes || 0) : Number(run.tradeSuccesses || 0);
          tradeSuccessSubEl.textContent = `successful attempts · ${formatCredits(Math.round(successes))}/${formatCredits(Math.round(attempts))} · ${displayDelta.tradesPer100.toFixed(2)}/100 turns`;
        }
      }
      if (tradesPer100El) {
        tradesPer100El.textContent = `${displayDelta.tradesPer100.toFixed(2)}`;
        tradesPer100El.style.color = displayDelta.tradesPer100 >= 3 ? "var(--green)" : (displayDelta.tradesPer100 >= 1.5 ? "var(--yellow)" : "var(--red)");
      }
      if (profitableRateSubEl) {
        const bots = data.bots || [];
        let active = 0;
        let profitable = 0;
        const activeStates = new Set(["running", "recovering", "blocked"]);
        for (const b of bots) {
          const state = String(b.state || "").toLowerCase();
          if (!activeStates.has(state)) continue;
          active += 1;
          if (Number(b.credits_delta || 0) > 0) profitable += 1;
        }
        const pct = active > 0 ? ((profitable * 100) / active) : 0;
        profitableRateSubEl.textContent = `profitable: ${pct.toFixed(1)}% (${profitable}/${active || 0})`;
      }

    const uptimeText = formatUptime(data.uptime_seconds);
    const uptimeEl = $("#uptime");
    if (uptimeEl) uptimeEl.textContent = " | " + uptimeText;
    const connectedForEl = $("#connected-for");
    if (connectedForEl) connectedForEl.textContent = uptimeText;

      const nowS = Date.now() / 1000;
      let resetRun = false;
      const totalBotsNow = Number(data.total_bots || 0);
      if (totalBotsNow === 0) {
        resetRun = true;
        activeRunStartTs = null;
      }
      if (run.runStart && activeRunStartTs && run.runStart > (activeRunStartTs + 120)) resetRun = true;
      if (lastRunTotalTurns > 0 && run.turns < (lastRunTotalTurns * 0.25)) resetRun = true;
      if (lastRunTotalBots > 0 && totalBotsNow < (lastRunTotalBots * 0.25)) resetRun = true;
      if (resetRun) {
        runMetricHistory.length = 0;
        lastRunMetricSampleTs = 0;
        runBaselineNetWorth = null;
        runBaselineTurns = null;
        runBaselineTrades = null;
      }
      if (run.runStart) activeRunStartTs = run.runStart;
      if (!run.runStart) activeRunStartTs = null;
      runtimeHasActiveBots = Number(run.activeBots || 0) > 0;
      lastRunTotalTurns = run.turns;
      lastRunTotalBots = totalBotsNow;
      if (run.activeBots > 0 && runBaselineNetWorth == null) {
        runBaselineNetWorth = Number(run.totalNetWorth || 0);
        runBaselineTurns = Number(run.turns || 0);
        runBaselineTrades = Number(run.trades || 0);
      }
      if (run.activeBots <= 0) {
        activeRunStartTs = null;
        runtimeHasActiveBots = false;
        runBaselineNetWorth = null;
        runBaselineTurns = null;
        runBaselineTrades = null;
      }

      const runtimeSec = (activeRunStartTs && runtimeHasActiveBots) ? Math.max(0, nowS - activeRunStartTs) : 0;
      renderRuntimeTick(nowS);

      if (runMetricHistory.length < 2) {
        hydrateRunHistoryFromTimeseries();
      }

      const shouldSample =
        run.activeBots > 0
        && (
          runMetricHistory.length === 0
          || (nowS - lastRunMetricSampleTs) >= RUN_TREND_SAMPLE_INTERVAL_S
        );
      if (shouldSample) {
        const liveDelta = computeRunDeltas(run);
        runMetricHistory.push({
          ts: nowS,
          turns: Number(liveDelta.deltaTurns || 0),
          trades: Number(liveDelta.deltaTrades || 0),
          netWorth: Number(run.totalNetWorth || 0),
          credits: Number(run.totalLiquid || 0),
          banked: Number(run.totalBanked || 0),
          fuelOre: Number(run.totalCargoFuelOre || 0),
          organics: Number(run.totalCargoOrganics || 0),
          equipment: Number(run.totalCargoEquipment || 0),
        });
        while (runMetricHistory.length > 240) runMetricHistory.shift();
        lastRunMetricSampleTs = nowS;
      }
      displayDelta = canonicalDisplayDelta(computeRecentRunDeltas(runDelta));
      renderRunTrend(runtimeSec, { ...run, ...displayDelta });

      const metrics = computeAggregateMetrics(data);
      const acceptEl = $("#accept-rate");
      const highEl = $("#too-high-rate");
      const lowEl = $("#too-low-rate");
      const noTrade30El = $("#no-trade-30");
      const noTrade60El = $("#no-trade-60");
      const noTrade90El = $("#no-trade-90");
      const noTrade120El = $("#no-trade-120");
      if (acceptEl) acceptEl.textContent = percent(metrics.acceptRate);
      if (highEl) highEl.textContent = percent(metrics.tooHighRate);
      if (lowEl) lowEl.textContent = percent(metrics.tooLowRate);
      if (noTrade30El) noTrade30El.textContent = String(metrics.noTrade30);
      if (noTrade60El) noTrade60El.textContent = String(metrics.noTrade60);
      if (noTrade90El) noTrade90El.textContent = String(metrics.noTrade90);
      if (noTrade120El) noTrade120El.textContent = String(metrics.noTrade120);
      renderStrategyCpt(metrics.strategyRows);

	    // Throttle (not debounce) table re-render.
	    // Under high-frequency status broadcasts, a debounce can starve the table
	    // and it will never render. Keep lastData and render at most every 300ms.
	    if (updateTimer) return;
	    updateTimer = setTimeout(() => {
	      updateTimer = null;
	      renderOrDeferTable(lastData || data);
	    }, 300);
	  }

  function applyUpdate(data) {
    try {
      update(data);
    } catch (err) {
      dot.className = "dot disconnected";
      connStatus.textContent = "Update error (see console)";
      console.error("dashboard_update_error", err);
    }
  }

  function renderBotTable(data) {
    const allBots = data.bots || [];
    syncStrategyFilterOptions(allBots);
    const filteredBots = applyFilters(allBots);
    if (botListMeta) {
      botListMeta.textContent = `${filteredBots.length} visible / ${allBots.length} total`;
    }

    const inactiveStates = new Set(["stopped", "completed", "error", "disconnected", "dead"]);
    const isInactiveBot = (bot) => inactiveStates.has(String(bot.state || "").toLowerCase());

    const bots = filteredBots.slice().sort((a, b) => {
      const ai = isInactiveBot(a) ? 1 : 0;
      const bi = isInactiveBot(b) ? 1 : 0;
      if (ai !== bi) return ai - bi;

      let va = a[sortKey] ?? "";
      let vb = b[sortKey] ?? "";
      if (typeof va === "number" || typeof vb === "number") {
        const na = Number(va ?? 0);
        const nb = Number(vb ?? 0);
        if (isFinite(na) && isFinite(nb)) {
          if (na !== nb) return sortReverse ? nb - na : na - nb;
          return String(a.bot_id || "").localeCompare(String(b.bot_id || ""));
        }
      }
      va = String(va);
      vb = String(vb);
      const cmp = sortReverse ? vb.localeCompare(va) : va.localeCompare(vb);
      if (cmp !== 0) return cmp;
      return String(a.bot_id || "").localeCompare(String(b.bot_id || ""));
    });

    const tbody = $("#bot-table");
    tbody.innerHTML = bots
      .map((b) => {
        const isRunning = b.state === "running";
        const isQueued = b.state === "queued";

        // For all bots, preserve last known activity context
        // Show exit_reason separately, not as main activity
        let activity;
        let exitInfo = "";

        const strategyIntent = String(b.strategy_intent || "");
        const isUnderAttack = !!b.under_attack;
        if (b.state === "completed") {
          activity = b.completed_at ? "FINISHED" : "COMPLETED";
        } else if (b.state === "stopped") {
          activity = b.activity_context ? getActivityBadge(b.activity_context) : "STOPPED";
        } else if (b.state === "error") {
          // CRITICAL FIX: Show last activity, not exit_reason
          activity = b.activity_context ? getActivityBadge(b.activity_context) : "ERROR";
          // Show exit_reason as secondary info if not generic exit code
          if (b.exit_reason && !b.exit_reason.toLowerCase().includes("exit_code")) {
            exitInfo = ` (${b.exit_reason})`;
          }
        } else {
          activity = getActivityBadge(b.activity_context || (isQueued ? "QUEUED" : "IDLE"));
        }
        if (isUnderAttack) {
          activity = "BATTLING";
        } else if (strategyIntent.toUpperCase().startsWith("RETREAT")) {
          activity = "EVADING";
        }

        const activityClass = getActivityClass(activity);
        const activityPrimary = `<span class="activity-badge ${activityClass}">${esc(activity)}</span>`;

        const stateClass = String(b.state || "unknown").toLowerCase();
        const stateHtml = `<span class="state-dot ${esc(stateClass)}" title="${esc(String(b.state || "unknown"))}"></span>`;

        // Status: phase/prompt detail (Paused, Username/Password, Port Haggle, etc.)
        // Hijack is additive; it shouldn't replace the bot's true activity.
        const detailParts = [];
        const detail = (b.status_detail || "").trim();
        const isStaleOrientFailed =
          detail === "ORIENTING:FAILED" &&
          b.state === "running" &&
          !["CONNECTING", "LOGGING_IN", "INITIALIZING"].includes(String(activity || "").toUpperCase());
        if (detail) {
          if (!isStaleOrientFailed) {
            detailParts.push(detail);
          }
        } else if (b.prompt_id) {
          // Avoid showing "prompt.sector_command" etc. as status; Status is for meaningful blocking phases.
          const safePrompts = new Set([
            "prompt.sector_command",
            "prompt.planet_command",
            "prompt.port_menu",
            "prompt.corporate_listings",
          ]);
          const isInteresting = !safePrompts.has(b.prompt_id);
          const isBadState = ["error", "blocked", "recovering", "disconnected"].includes(b.state);
          if (isBadState && isInteresting) {
            detailParts.push(b.prompt_id);
          }
        }
        const statusText = detailParts.length ? detailParts.join(" | ") : "-";
        const compactStatus = compactStatusText(`${statusText}${exitInfo ? " " + exitInfo : ""}`);
        const activityLine2 = compactStatus || "—";
        const activityHtml = `<div class="activity-cell" onclick="window._openInspector('${esc(b.bot_id)}','activity')" title="${esc(statusText)}"><span class="activity-primary">${activityPrimary}</span><span class="activity-secondary${compactStatus ? "" : " subtle-empty"}">${esc(activityLine2)}</span></div>`;

        const turnsDisplay = `${b.turns_executed}`;
        const tradesDisplay = `${Number(b.trades_executed || 0)}`;
        const updatedDisplay = b.last_action_time ? formatRelativeTime(b.last_action_time) : "-";

        // Display "-" for uninitialized numeric fields
        const botId = String(b.bot_id || "");
        const liveCredits = Number(b.credits);
        const hasLiveCredits = isFinite(liveCredits) && liveCredits >= 0;
        const cachedCredits = botId ? lastKnownCreditsByBotId.get(botId) : undefined;
        const hasCachedCredits = isFinite(Number(cachedCredits)) && Number(cachedCredits) >= 0;
        const useRecoveredCredits = !hasLiveCredits && hasCachedCredits;
        const creditsValue = hasLiveCredits ? liveCredits : (useRecoveredCredits ? Number(cachedCredits) : null);
        const creditsDisplay = creditsValue != null ? formatCredits(creditsValue) : "-";
        const fuelValue = (b.cargo_fuel_ore === null || b.cargo_fuel_ore === undefined) ? null : Number(b.cargo_fuel_ore);
        const orgValue = (b.cargo_organics === null || b.cargo_organics === undefined) ? null : Number(b.cargo_organics);
        const equipValue = (b.cargo_equipment === null || b.cargo_equipment === undefined) ? null : Number(b.cargo_equipment);
        const fuelDisplay = fuelValue === null ? "-" : formatCredits(fuelValue);
        const orgDisplay = orgValue === null ? "-" : formatCredits(orgValue);
        const equipDisplay = equipValue === null ? "-" : formatCredits(equipValue);
        const fuelStateClass = fuelValue !== null && fuelValue > 0 ? "hold-active" : "hold-empty";
        const orgStateClass = orgValue !== null && orgValue > 0 ? "hold-active" : "hold-empty";
        const equipStateClass = equipValue !== null && equipValue > 0 ? "hold-active" : "hold-empty";

        const compact = getStrategyCompact(b);
        const aiDecision = getAiDecisionInfo(b);
        const strategyNote = getStrategyNote(b);
        const strategyLine2 = aiDecision.summary || strategyNote || "—";
        const strategyLine3 = aiDecision.detail || "";
        const strategyTitle = [compact.full, strategyNote, aiDecision.tooltip].filter(Boolean).join(" | ") || compact.full;
        const roleToken = String(b.swarm_role || "").trim().toLowerCase();
        const roleLabel = roleToken === "scout" ? "SCOUT" : (roleToken === "harvester" ? "HARVESTER" : (roleToken === "ai" ? "AI" : ""));
        const roleChip = roleLabel ? `<span class="chip role ${esc(roleToken || "unknown")}">${esc(roleLabel)}</span>` : "";
        const hijackChip = b.is_hijacked ? `<span class="chip role hijacked">HIJACKED</span>` : "";
        const aiChip = aiDecision.isAi ? `<span class="chip aictrl">AI-CTRL</span>` : "";
        const cptMeta = computeBotCptPresentation(b);
        const runCptStyle = cptMeta.runColor ? ` style="color:${cptMeta.runColor}"` : "";
        const adjCptStyle = cptMeta.adjustedColor ? ` style="color:${cptMeta.adjustedColor}"` : "";
        const strategyHtml = `<div class="strategy-cell" title="${esc(strategyTitle)}">` +
            `<span class="strategy-chip-row">` +
              `<span class="chip sid">${esc(compact.id || "-")}</span>` +
              (compact.mode ? `<span class="chip mode">${esc(compact.mode)}</span>` : "") +
              aiChip +
              roleChip +
              hijackChip +
            `</span>` +
            `<div class="strategy-intent${strategyLine2 === "—" ? " subtle-empty" : ""}">${esc(strategyLine2)}</div>` +
            (strategyLine3 ? `<div class="strategy-ai-meta">${esc(strategyLine3)}</div>` : "") +
          `</div>`;
        const cptHtml = `<div class="cpt-cell">` +
            `<span class="cpt-primary">` +
              `<span class="cpt-label">Run</span><strong${runCptStyle}>${esc(cptMeta.runText)}</strong>` +
            `</span>` +
            `<span class="cpt-secondary${cptMeta.baselineText === "base pending" ? " subtle-empty" : ""}">` +
              `<span class="cpt-label">Adj Δ</span><strong${adjCptStyle}>${esc(cptMeta.adjustedDeltaText)}</strong>` +
              `<span class="cpt-base">${esc(cptMeta.baselineText)}</span>` +
            `</span>` +
          `</div>`;

        const creditsColor = hasLiveCredits ? creditColor(liveCredits) : "";
        const creditCellClass = useRecoveredCredits ? "credit-cell credit-cell-unverified" : "credit-cell";
        const creditCellTitle = useRecoveredCredits
          ? "Last known credits shown while reconnecting; waiting for fresh verification."
          : "";
        return `<tr>
	        <td title="${esc(b.bot_id)}">${esc(String(b.bot_id || "-"))}</td>
	        <td>${stateHtml}</td>
	        <td>${activityHtml}</td>
	        <td>${strategyHtml}</td>
	        <td class="numeric">${b.sector}</td>
	        <td class="numeric ${creditCellClass}"${creditsColor ? ` style="color:${creditsColor}"` : ""}${creditCellTitle ? ` title="${esc(creditCellTitle)}"` : ""}><span class="credit-glyph">${esc(creditGlyph())}</span>${creditsDisplay}</td>
	        <td>${cptHtml}</td>
	        <td class="numeric cargo-fuel-cell ${fuelStateClass}">${fuelDisplay}</td>
	        <td class="numeric cargo-org-cell ${orgStateClass}">${orgDisplay}</td>
	        <td class="numeric cargo-equip-cell ${equipStateClass}">${equipDisplay}</td>
	        <td class="numeric">${turnsDisplay}</td>
	        <td class="numeric">${tradesDisplay}</td>
	        <td class="timecell">${updatedDisplay}</td>
	        <td class="actions">
	          <button type="button" class="btn more" onclick="window._openInspector('${esc(b.bot_id)}')" title="Inspect" aria-label="Inspect bot menu">⋯</button>
        </td>
      </tr>`;
      })
      .join("");

    // Update terminal stats if open
    updateTermStats();
  }

  // --- Sort headers ---
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) {
        sortReverse = !sortReverse;
      } else {
        sortKey = key;
        sortReverse = false;
      }
	      // Immediate re-render on sort (cancel debounced update)
	      if (lastData) {
	        clearTimeout(updateTimer);
	        renderOrDeferTable(lastData);
	      }
	    });
	  });

  [filterStateEl, filterStrategyEl, filterNoTradeEl, filterLayoutEl].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", () => {
      if (el === filterLayoutEl) {
        applyTableView(filterLayoutEl.value, true, false);
      }
      if (lastData) renderOrDeferTable(lastData);
    });
  });

  if (filterSearchEl) {
    filterSearchEl.addEventListener("input", () => {
      if (lastData) renderOrDeferTable(lastData);
    });
  }

  // --- Error modal ---
  const errorModalOverlay = $("#error-modal-overlay");
  const errorModalTitle = $("#error-modal-title");
  const errorModalContent = $("#error-modal-content");

  window._openErrorModal = function (botId) {
    if (!lastData || !lastData.bots) return;
    const bot = lastData.bots.find(b => b.bot_id === botId);
    if (!bot) return;
    if (errorModalTitle) errorModalTitle.textContent = "Error Details";

    let html = `
      <div class="field">
        <div class="label">Bot ID</div>
        <div class="value">${esc(bot.bot_id)}</div>
      </div>
      <div class="field">
        <div class="label">State</div>
        <div class="value">${esc(bot.state)}</div>
      </div>
      <div class="field">
        <div class="label">Activity</div>
        <div class="value">${esc(bot.activity_context || "None")}</div>
      </div>`;

    if (bot.state === "error") {
      const timestamp = bot.error_timestamp
        ? new Date(bot.error_timestamp * 1000).toLocaleString()
        : "Unknown";
      html += `
      <div class="field">
        <div class="label">Error Type</div>
        <div class="value" style="color: var(--red);">${esc(bot.error_type || "Unknown")}</div>
      </div>
      <div class="field">
        <div class="label">Error Message</div>
        <div class="value" style="color: var(--red);">${esc(bot.error_message || "No message")}</div>
      </div>
      <div class="field">
        <div class="label">Error Timestamp</div>
        <div class="value">${esc(timestamp)}</div>
      </div>
      <div class="field">
        <div class="label">Exit Reason</div>
        <div class="value">${esc(bot.exit_reason || "exception")}</div>
      </div>`;
    }

    html += `
      <div class="field">
        <div class="label">Last Action</div>
        <div class="value">${esc(bot.last_action || "None")}</div>
      </div>
      ${(bot.recent_actions && bot.recent_actions.length > 0) ? `
      <div class="field">
        <div class="label">Recent Actions</div>
        <div class="value">
          ${bot.recent_actions.slice(-5).map(a => {
            const time = new Date(a.time * 1000).toLocaleTimeString();
            return `${time} ${a.action} (${a.sector}): ${a.result}`;
          }).join("\\n")}
        </div>
      </div>
      ` : ""}
    `;

    errorModalContent.innerHTML = html;
    errorModalOverlay.classList.add("open");
  };

  window._openMetrics = function (botId) {
    if (!lastData || !lastData.bots) return;
    const bot = lastData.bots.find(b => b.bot_id === botId);
    if (!bot) return;

    const haggleAccept = Number(bot.haggle_accept || 0);
    const haggleCounter = Number(bot.haggle_counter || 0);
    const haggleHigh = Number(bot.haggle_too_high || 0);
    const haggleLow = Number(bot.haggle_too_low || 0);
    const haggleTotal = haggleAccept + haggleCounter + haggleHigh + haggleLow;
    const acceptRate = haggleTotal > 0 ? ((haggleAccept / haggleTotal) * 100).toFixed(1) + "%" : "0.0%";
    const creditsDelta = Number(bot.credits_delta || 0);
    const cptMeta = computeBotCptPresentation(bot);
    const aiDecision = getAiDecisionInfo(bot);
    const llmWakeups = Number(bot.llm_wakeups || 0);
    const autopilotTurns = Number(bot.autopilot_turns || 0);
    const contractFailures = Number(bot.goal_contract_failures || 0);
    const llmWakeupsPer100 = Number(bot.llm_wakeups_per_100_turns || 0);
    const showAiStats = aiDecision.isAi || llmWakeups > 0 || autopilotTurns > 0 || contractFailures > 0;

    if (errorModalTitle) errorModalTitle.textContent = "Bot Metrics";
    errorModalContent.innerHTML = `
      <div class="field"><div class="label">Bot ID</div><div class="value">${esc(bot.bot_id)}</div></div>
      <div class="field"><div class="label">Strategy</div><div class="value">${esc((bot.strategy || bot.strategy_id || "-") + (bot.strategy_mode ? " (" + bot.strategy_mode + ")" : ""))}</div></div>
      ${showAiStats ? `<div class="field"><div class="label">AI Decision</div><div class="value">${esc(aiDecision.summary || "-")}</div></div>` : ""}
      ${showAiStats && aiDecision.detail ? `<div class="field"><div class="label">AI Detail</div><div class="value">${esc(aiDecision.detail)}</div></div>` : ""}
      ${showAiStats ? `<div class="field"><div class="label">LLM Wakeups</div><div class="value">${esc(String(llmWakeups))} (${esc(llmWakeupsPer100.toFixed(2))}/100t)</div></div>` : ""}
      ${showAiStats ? `<div class="field"><div class="label">Autopilot Turns</div><div class="value">${esc(String(autopilotTurns))}</div></div>` : ""}
      ${showAiStats ? `<div class="field"><div class="label">Goal Contract Failures</div><div class="value">${esc(String(contractFailures))}</div></div>` : ""}
      <div class="field"><div class="label">Trades Executed</div><div class="value">${esc(String(bot.trades_executed || 0))}</div></div>
      <div class="field"><div class="label">Credits Delta</div><div class="value">${esc(String(creditsDelta))}</div></div>
      <div class="field"><div class="label">Run CPT</div><div class="value">${esc(cptMeta.runText)}</div></div>
      <div class="field"><div class="label">Adjusted CPT</div><div class="value">${esc(cptMeta.adjustedText)}</div></div>
      <div class="field"><div class="label">CPT Baseline</div><div class="value">${esc(cptMeta.baselineText)}</div></div>
      <div class="field"><div class="label">Haggle Accept</div><div class="value">${esc(String(haggleAccept))}</div></div>
      <div class="field"><div class="label">Haggle Counter</div><div class="value">${esc(String(haggleCounter))}</div></div>
      <div class="field"><div class="label">Haggle Too High</div><div class="value">${esc(String(haggleHigh))}</div></div>
      <div class="field"><div class="label">Haggle Too Low</div><div class="value">${esc(String(haggleLow))}</div></div>
      <div class="field"><div class="label">Haggle Accept Rate</div><div class="value">${esc(acceptRate)}</div></div>
    `;
    errorModalOverlay.classList.add("open");
  };

  function closeErrorModal() {
    errorModalOverlay.classList.remove("open");
  }

  $("#error-modal-close").addEventListener("click", closeErrorModal);
  errorModalOverlay.addEventListener("click", function (e) {
    if (e.target === errorModalOverlay) closeErrorModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && errorModalOverlay.classList.contains("open")) {
      closeErrorModal();
    }
  });

  // --- Bot actions ---
  window._killBot = async function (botId) {
    if (!confirm("Kill bot " + botId + "?")) return;
    try {
      const resp = await fetch("/bot/" + encodeURIComponent(botId), { method: "DELETE" });
      const data = await resp.json();
      if (resp.ok) {
        showToast("Killed " + botId, "success");
      } else {
        showToast(data.error || "Failed", "error");
      }
    } catch (e) {
      showToast("Network error", "error");
    }
  };

  window._restartBot = async function (botId) {
    if (!confirm("Restart bot " + botId + "?")) return;
    try {
      const resp = await fetch("/bot/" + encodeURIComponent(botId) + "/restart", { method: "POST" });
      const data = await resp.json();
      if (resp.ok) {
        showToast("Restarted " + botId + " (PID " + data.pid + ")", "success");
      } else {
        showToast(data.error || "Failed", "error");
      }
    } catch (e) {
      showToast("Network error", "error");
    }
  };

  // --- Inspector modal ---
  let logWs = null;
  let logAutoScroll = true;
  let currentLogBotId = null;
  let currentInspectorTab = "activity";

  const logModal = $("#log-modal");
  const logModalPanel = $("#log-modal-panel");
  const logTitle = $("#log-title");
  const logStatus = $("#log-status");
  const logContent = $("#log-content");
  const logTabActivity = $("#log-tab-activity");
  const logTabLogs = $("#log-tab-logs");
  const logTabMetrics = $("#log-tab-metrics");
  const logTabTerminal = $("#log-tab-terminal");

  function setInspectorTab(tab) {
    currentInspectorTab = tab;
    if (!logModalPanel) return;
    if (tab === "activity") logModalPanel.classList.add("activity-mode");
    else logModalPanel.classList.remove("activity-mode");
    [
      [logTabActivity, "activity"],
      [logTabLogs, "logs"],
      [logTabMetrics, "metrics"],
      [logTabTerminal, "terminal"],
    ].forEach(([el, key]) => {
      if (!el) return;
      el.classList.toggle("active", tab === key);
    });
  }

  // Track scroll position for auto-scroll
  logContent.addEventListener("scroll", function () {
    const atBottom = logContent.scrollHeight - logContent.scrollTop - logContent.clientHeight < 30;
    logAutoScroll = atBottom;
  });

  function appendLogLines(lines) {
    const fragment = document.createDocumentFragment();
    for (const line of lines) {
      const div = document.createElement("div");
      div.className = "log-line";
      div.textContent = line;
      fragment.appendChild(div);
    }
    logContent.appendChild(fragment);

    // Cap at 5000 lines
    while (logContent.children.length > 5000) {
      logContent.removeChild(logContent.firstChild);
    }

    if (logAutoScroll) {
      logContent.scrollTop = logContent.scrollHeight;
    }
  }

  function closeLogStream() {
    if (!logWs) return;
    try { logWs.close(); } catch (_) {}
    logWs = null;
  }

  function openLogsStream(botId) {
    closeLogStream();
    logContent.innerHTML = "";
    logStatus.innerHTML = "Connecting log stream...";
    logAutoScroll = true;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = proto + "//" + location.host + "/ws/bot/" + encodeURIComponent(botId) + "/logs";

    logWs = new WebSocket(wsUrl);

    logWs.onopen = function () {
      logStatus.innerHTML = '<span class="live">&#9679; Live</span>';
    };

    logWs.onmessage = function (e) {
      try {
        const msg = JSON.parse(e.data);
        if (msg.lines) {
          if (msg.type === "initial" || msg.type === "truncated") {
            logContent.innerHTML = "";
          }
          appendLogLines(msg.lines);
        }
        if (msg.error) {
          logStatus.textContent = "Error: " + msg.error;
        }
      } catch (_) {}
    };

    logWs.onclose = function () {
      if (currentInspectorTab === "logs") logStatus.textContent = "Log stream disconnected";
      logWs = null;
    };

    logWs.onerror = function () {
      logStatus.textContent = "Connection error";
    };
  }

  function renderInspectorMetrics(botId) {
    if (!lastData || !lastData.bots) {
      logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--red);\">Metrics unavailable</div>";
      return;
    }
    const bot = lastData.bots.find((b) => b.bot_id === botId);
    if (!bot) {
      logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--red);\">Bot not found</div>";
      return;
    }
    const haggleAccept = Number(bot.haggle_accept || 0);
    const haggleCounter = Number(bot.haggle_counter || 0);
    const haggleHigh = Number(bot.haggle_too_high || 0);
    const haggleLow = Number(bot.haggle_too_low || 0);
    const haggleTotal = haggleAccept + haggleCounter + haggleHigh + haggleLow;
    const acceptRate = haggleTotal > 0 ? ((haggleAccept / haggleTotal) * 100).toFixed(1) + "%" : "0.0%";
    const creditsDelta = Number(bot.credits_delta || 0);
    const cptMeta = computeBotCptPresentation(bot);
    const aiDecision = getAiDecisionInfo(bot);
    const llmWakeups = Number(bot.llm_wakeups || 0);
    const autopilotTurns = Number(bot.autopilot_turns || 0);
    const contractFailures = Number(bot.goal_contract_failures || 0);
    const llmWakeupsPer100 = Number(bot.llm_wakeups_per_100_turns || 0);
    const showAiStats = aiDecision.isAi || llmWakeups > 0 || autopilotTurns > 0 || contractFailures > 0;
    logContent.innerHTML = `
      <div class="field"><div class="label">Bot ID</div><div class="value">${esc(bot.bot_id)}</div></div>
      <div class="field"><div class="label">State</div><div class="value">${esc(bot.state || "-")}</div></div>
      <div class="field"><div class="label">Strategy</div><div class="value">${esc(getStrategyLabel(bot))}</div></div>
      ${showAiStats ? `<div class="field"><div class="label">AI Decision</div><div class="value">${esc(aiDecision.summary || "-")}</div></div>` : ""}
      ${showAiStats && aiDecision.detail ? `<div class="field"><div class="label">AI Detail</div><div class="value">${esc(aiDecision.detail)}</div></div>` : ""}
      ${showAiStats ? `<div class="field"><div class="label">LLM Wakeups</div><div class="value">${esc(String(llmWakeups))} (${esc(llmWakeupsPer100.toFixed(2))}/100t)</div></div>` : ""}
      ${showAiStats ? `<div class="field"><div class="label">Autopilot Turns</div><div class="value">${esc(String(autopilotTurns))}</div></div>` : ""}
      ${showAiStats ? `<div class="field"><div class="label">Goal Contract Failures</div><div class="value">${esc(String(contractFailures))}</div></div>` : ""}
      <div class="field"><div class="label">Trades Executed</div><div class="value">${esc(String(bot.trades_executed || 0))}</div></div>
      <div class="field"><div class="label">Credits Delta</div><div class="value">${esc(String(creditsDelta))}</div></div>
      <div class="field"><div class="label">Run CPT</div><div class="value">${esc(cptMeta.runText)}</div></div>
      <div class="field"><div class="label">Adjusted CPT</div><div class="value">${esc(cptMeta.adjustedText)}</div></div>
      <div class="field"><div class="label">CPT Baseline</div><div class="value">${esc(cptMeta.baselineText)}</div></div>
      <div class="field"><div class="label">Haggle Accept</div><div class="value">${esc(String(haggleAccept))}</div></div>
      <div class="field"><div class="label">Haggle Counter</div><div class="value">${esc(String(haggleCounter))}</div></div>
      <div class="field"><div class="label">Haggle Too High</div><div class="value">${esc(String(haggleHigh))}</div></div>
      <div class="field"><div class="label">Haggle Too Low</div><div class="value">${esc(String(haggleLow))}</div></div>
      <div class="field"><div class="label">Haggle Accept Rate</div><div class="value">${esc(acceptRate)}</div></div>
    `;
  }

  async function loadInspectorTab(botId, tab) {
    setInspectorTab(tab);
    if (tab !== "logs") closeLogStream();
    logTitle.textContent = "Inspector: " + botId;

    if (tab === "activity") {
      logStatus.textContent = "Loading activity...";
      logAutoScroll = false;
      logContent.innerHTML = "";
      try {
        const resp = await fetch("/bot/" + encodeURIComponent(botId) + "/events");
        if (!resp.ok) {
          logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--red);\">Error: " + resp.status + " " + resp.statusText + "</div>";
          logStatus.textContent = "Error";
          return;
        }
        const data = await resp.json();
        const events = data.events || [];
        renderActivityLedger(events);
        logStatus.textContent = "Loaded " + events.length + " events";
      } catch (e) {
        logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--red);\">Network error: " + e.message + "</div>";
        logStatus.textContent = "Error";
      }
      return;
    }

    if (tab === "logs") {
      openLogsStream(botId);
      return;
    }

    if (tab === "metrics") {
      logStatus.textContent = "Metrics";
      renderInspectorMetrics(botId);
      return;
    }

    if (tab === "terminal") {
      // Direct handoff to live terminal; no extra click in inspector.
      closeLogs();
      window._openTerminal(botId);
      return;
    }
  }

  async function openInspector(botId, tab) {
    currentLogBotId = botId;
    logModal.classList.add("open");
    await loadInspectorTab(botId, tab || "activity");
  }

  function closeLogs() {
    logModal.classList.remove("open");
    if (logModalPanel) logModalPanel.classList.remove("activity-mode");
    currentLogBotId = null;
    currentInspectorTab = "activity";
    closeLogStream();
  }

  window._openInspector = function (botId, tab) {
    void openInspector(botId, tab || "activity");
  };

  window._openLogs = function (botId) {
    void openInspector(botId, "logs");
  };

  $("#log-close").addEventListener("click", closeLogs);
  logModal.addEventListener("click", function (e) {
    if (e.target === logModal) closeLogs();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && logModal.classList.contains("open")) {
      closeLogs();
    }
  });

  [logTabActivity, logTabLogs, logTabMetrics, logTabTerminal].forEach((el) => {
    if (!el) return;
    el.addEventListener("click", () => {
      if (!currentLogBotId) return;
      const tab = el.id.replace("log-tab-", "");
      void loadInspectorTab(currentLogBotId, tab);
    });
  });

  function formatEventType(event) {
    if (event.type === "action") return "ACTION";
    if (event.type === "status_update") return "STATUS";
    if (event.type === "error") return "ERROR";
    return String(event.type || "EVENT").toUpperCase();
  }

  function buildEventWhat(event) {
    if (event.type === "action") {
      const atSector = event.sector ? " @ " + event.sector : "";
      const repeats = Number(event.repeat_count || 1);
      const repeatSuffix = repeats > 1 ? " x" + String(repeats) : "";
      return (event.action || "UNKNOWN") + atSector + repeatSuffix;
    }
    if (event.type === "status_update") {
      const activity = event.activity || "idle";
      return (event.state || "unknown").toUpperCase() + " | " + activity;
    }
    if (event.type === "error") {
      return event.error_type || "ERROR";
    }
    return "-";
  }

  function buildEventWhy(event) {
    if (event.type === "action") {
      const parts = [];
      if (event.why) parts.push(event.why);
      else if (event.details) parts.push(event.details);
      if (event.wake_reason) parts.push("wake=" + event.wake_reason);
      if (event.review_after_turns != null) parts.push("review=" + String(event.review_after_turns));
      if (event.decision_source) parts.push("src=" + event.decision_source);
      if (Number(event.repeat_count || 1) > 1) parts.push("repeated");
      return parts.join(" | ");
    }
    if (event.type === "error") return event.error_message || "";
    if (event.type === "status_update") {
      if (event.strategy_intent) return event.strategy_intent;
      if (event.status_detail) return event.status_detail;
      return "";
    }
    return "";
  }

  function buildEventStrategy(event) {
    const sid = event.strategy_id || event.strategy || "";
    const mode = event.strategy_mode || "";
    if (sid && mode) return sid + "(" + mode + ")";
    return sid || "-";
  }

  function _actionSignature(event) {
    if (!event || event.type !== "action") return "";
    return [
      String(event.action || "").toUpperCase(),
      String(event.sector || ""),
      String(event.result || "").toLowerCase(),
      String(event.why || event.details || ""),
      String(event.strategy_id || event.strategy || ""),
      String(event.strategy_mode || ""),
      String(event.strategy_intent || ""),
    ].join("|");
  }

  function _compactActivityEvents(events) {
    const compacted = [];
    for (const raw of events || []) {
      const event = { ...raw };
      const prev = compacted.length > 0 ? compacted[compacted.length - 1] : null;
      if (prev && event.type === "action" && prev.type === "action" && _actionSignature(prev) === _actionSignature(event)) {
        prev.repeat_count = Number(prev.repeat_count || 1) + 1;
        prev.repeat_first_timestamp = Number(event.timestamp || prev.repeat_first_timestamp || 0);
        if (event.credits_before != null) prev.credits_before = event.credits_before;
        if (event.turns_before != null) prev.turns_before = event.turns_before;
        const prevDelta = Number(prev.result_delta || 0);
        const curDelta = Number(event.result_delta || 0);
        if (Number.isFinite(prevDelta) && Number.isFinite(curDelta)) {
          prev.result_delta = prevDelta + curDelta;
        }
        continue;
      }
      event.repeat_count = 1;
      event.repeat_first_timestamp = Number(event.timestamp || 0);
      compacted.push(event);
    }
    return compacted;
  }

  function _formatActivityCredits(event) {
    if (event.type === "action") {
      const before = Number(event.credits_before);
      const after = Number(event.credits_after);
      if (Number.isFinite(before) && Number.isFinite(after) && before >= 0 && after >= 0) {
        if (before === after) return formatCredits(after);
        return `${formatCredits(before)} -> ${formatCredits(after)}`;
      }
      if (Number.isFinite(after) && after >= 0) return formatCredits(after);
    }
    if (event.credits != null && Number(event.credits) >= 0) return formatCredits(Number(event.credits));
    return "-";
  }

  function _formatActivityTurns(event) {
    if (event.type === "action") {
      const before = Number(event.turns_before);
      const after = Number(event.turns_after);
      if (Number.isFinite(before) && Number.isFinite(after) && before >= 0 && after >= 0) {
        return `${String(before)} -> ${String(after)}`;
      }
      if (Number.isFinite(after) && after >= 0) return String(after);
    }
    if (event.turns_executed != null) return String(event.turns_executed);
    return "-";
  }

  function renderActivityLedger(events) {
    if (!events.length) {
      logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--fg2); padding: 12px 16px;\">No activity events yet</div>";
      return;
    }

    const compactedEvents = _compactActivityEvents(events);
    const rows = compactedEvents
      .map((event) => {
        const time = new Date((event.timestamp || 0) * 1000).toLocaleTimeString();
        const timeAbs = formatAbsoluteTime(event.timestamp || null);
        const firstSeenAbs = formatAbsoluteTime(event.repeat_first_timestamp || null);
        const eventType = formatEventType(event);
        const what = buildEventWhat(event);
        const why = buildEventWhy(event);
        const strategy = buildEventStrategy(event);
        const sector = event.sector != null ? String(event.sector) : "-";
        const credits = _formatActivityCredits(event);
        const turns = _formatActivityTurns(event);
        const startedAt = event.started_at || null;
        const stoppedAt = event.stopped_at || null;
        const startedRel = formatRelativeStamp(startedAt);
        const stoppedRel = formatRelativeStamp(stoppedAt);
        const startedAbs = formatAbsoluteTime(startedAt);
        const stoppedAbs = formatAbsoluteTime(stoppedAt);
        const repeats = Number(event.repeat_count || 1);
        const resultDelta = (event.result_delta != null && Number(event.result_delta) !== 0)
          ? (Number(event.result_delta) > 0 ? ` Δ+${formatCredits(Number(event.result_delta))}` : ` Δ${formatCredits(Number(event.result_delta))}`)
          : "";
        const resultRaw = String(event.result || (event.type === "error" ? "failure" : "")).toLowerCase();
        const resultText = resultRaw || "-";
        const resultRepeat = repeats > 1 ? ` x${String(repeats)}` : "";
        const resultCls =
          resultRaw === "success" ? "activity-result-success" :
          resultRaw === "failure" || resultRaw === "error" ? "activity-result-failure" :
          resultRaw === "pending" ? "activity-result-pending" : "";

        return `<tr>
          <td class="activity-col-time" title="${esc(timeAbs + (repeats > 1 ? " | first=" + firstSeenAbs : ""))}">${esc(time)}</td>
          <td class="activity-col-type">${esc(eventType)}</td>
          <td class="activity-col-what">${esc(what)}</td>
          <td class="activity-col-why" title="${esc(why)}">${esc(why || "-")}</td>
          <td class="activity-col-strategy">${esc(strategy)}</td>
          <td class="activity-col-sector">${esc(sector)}</td>
          <td class="activity-col-credits">${esc(credits)}</td>
          <td class="activity-col-turns">${esc(turns)}</td>
          <td class="activity-col-start" title="${esc(startedAbs)}">${esc(startedRel)}</td>
          <td class="activity-col-stop" title="${esc(stoppedAbs)}">${esc(stoppedRel)}</td>
          <td class="activity-col-result ${resultCls}">${esc(resultText + resultDelta + resultRepeat)}</td>
        </tr>`;
      })
      .join("");

    logContent.innerHTML = `
      <div class="activity-ledger-wrap">
        <table class="activity-ledger-table">
          <thead>
            <tr>
              <th class="activity-col-time">Time</th>
              <th class="activity-col-type">Type</th>
              <th class="activity-col-what">What Happened</th>
              <th class="activity-col-why">Why</th>
              <th class="activity-col-strategy">Strategy</th>
              <th class="activity-col-sector">Sector</th>
              <th class="activity-col-credits">Credits</th>
              <th class="activity-col-turns">Turns</th>
              <th class="activity-col-start">Started</th>
              <th class="activity-col-stop">Stopped</th>
              <th class="activity-col-result">Result</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  // --- Event ledger (columnized activity log) ---
  window._openEventLedger = function (botId) {
    void openInspector(botId, "activity");
  };

  // --- Swarm WebSocket connection ---
  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(proto + "//" + location.host + "/ws/swarm");

    ws.onopen = () => {
      dot.className = "dot connected";
      connStatus.textContent = "Connected";
      if (swarmPingTimer) clearInterval(swarmPingTimer);
      swarmPingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 2000);
    };

    ws.onmessage = (e) => {
      try {
        applyUpdate(JSON.parse(e.data));
      } catch (_) {}
    };

    ws.onclose = () => {
      if (swarmPingTimer) {
        clearInterval(swarmPingTimer);
        swarmPingTimer = null;
      }
      dot.className = "dot disconnected";
      connStatus.textContent = "Disconnected - reconnecting...";
      setTimeout(connect, 2000);
    };

    ws.onerror = () => ws.close();
  }

  // Fallback HTTP polling
  async function poll() {
    try {
      const resp = await fetch("/swarm/status");
      if (resp.ok) applyUpdate(await resp.json());
    } catch (_) {}
  }

  // --- Swarm control buttons ---
  const btnKillAll = $("#btn-kill-all");
  const btnClear = $("#btn-clear");

  if (btnKillAll) {
    btnKillAll.addEventListener("click", async function () {
      if (!confirm("Kill ALL running bots?")) return;
      try {
        const resp = await fetch("/swarm/kill-all", { method: "POST" });
        const data = await resp.json();
        showToast("Killed " + data.count + " bots", "success");
      } catch (e) {
        showToast("Network error", "error");
      }
    });
  }

  if (btnClear) {
    btnClear.addEventListener("click", async function () {
      if (!confirm("Clear ALL bot entries? (running bots will be killed first)")) return;
      try {
        const resp = await fetch("/swarm/clear", { method: "POST" });
        const data = await resp.json();
        showToast("Cleared " + data.cleared + " bots", "success");
      } catch (e) {
        showToast("Network error", "error");
      }
    });
  }

  const btnSpawn = $("#btn-spawn");
  const spawnPreset = $("#spawn-preset");
  const spawnCount = $("#spawn-count");
  const spawnConfig = $("#spawn-config");
  const poolSummary = $("#pool-summary");
  const poolTable = $("#pool-table");
  const poolKpiLeased = $("#pool-kpi-leased");
  const poolKpiAvailable = $("#pool-kpi-available");
  const poolKpiCooldown = $("#pool-kpi-cooldown");
  const poolKpiStale = $("#pool-kpi-stale");
  const poolKpiIdentity = $("#pool-kpi-identity");
  const poolRate = $("#pool-rate");

  let poolLastSample = null;
  let poolAccountLastSample = null;
  const poolAccountRateHistory = new Map();

  function pushAccountRateSample(accountId, rate) {
    const key = String(accountId || "");
    if (!key) return;
    const history = poolAccountRateHistory.get(key) || [];
    history.push(Math.max(0, Number(rate) || 0));
    while (history.length > 18) history.shift();
    poolAccountRateHistory.set(key, history);
  }

  function formatGameName(account) {
    const letter = String(account.game_letter || "").trim().toUpperCase();
    if (letter) return `TW2002-${letter}`;
    return "TW2002";
  }

  function formatSourceName(source) {
    const raw = String(source || "unknown").trim().toLowerCase();
    const label = {
      generated: "gen",
      persisted: "persist",
      config: "config",
      pool: "pool",
      unknown: "unk",
    }[raw] || raw.slice(0, 8);
    return { raw: raw || "unknown", label };
  }

  function buildInlineSparkline(history) {
    const vals = Array.isArray(history) && history.length ? history : [0];
    const n = vals.length;
    const w = 38;
    const h = 12;
    const maxV = Math.max(...vals, 0.0001);
    const points = vals.map((val, i) => {
      const x = n === 1 ? w : (i / (n - 1)) * w;
      const y = h - 1 - (val / maxV) * (h - 4);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    return `<svg class="pool-row-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">` +
      `<line class="baseline" x1="0" y1="${h - 1}" x2="${w}" y2="${h - 1}"></line>` +
      `<polyline points="${points}"></polyline>` +
    `</svg>`;
  }

  function _buildRange(configDir, count, startAt) {
    const out = [];
    const start = Number(startAt || 1);
    const total = Number(count || 0);
    for (let i = 0; i < total; i++) {
      const idx = start + i;
      out.push(`config/${configDir}/bot_${String(idx).padStart(2, "0")}.yaml`);
    }
    return out;
  }

  function currentSpawnPreset() {
    return (spawnPreset && spawnPreset.value) ? String(spawnPreset.value) : "preset_20_mixed";
  }

  function currentSpawnPresetLabel() {
    if (!spawnPreset || !spawnPreset.selectedOptions || !spawnPreset.selectedOptions.length) {
      return currentSpawnPreset();
    }
    return String(spawnPreset.selectedOptions[0].textContent || currentSpawnPreset()).trim();
  }

  function buildSpawnConfigs() {
    const preset = currentSpawnPreset();
    if (preset === "preset_20_mixed") {
      return [
        ..._buildRange("swarm_demo_ai", 5, 1),
        ..._buildRange("swarm_demo", 15, 1),
      ];
    }
    if (preset === "preset_20_dynamic") {
      return _buildRange("swarm_demo", 20, 1);
    }
    if (preset === "preset_5_dynamic") {
      return _buildRange("swarm_demo", 5, 1);
    }
    const count = parseInt(spawnCount.value, 10) || 5;
    const configDir = spawnConfig.value || "swarm_demo";
    return _buildRange(configDir, count, 1);
  }

  function syncSpawnPresetUi() {
    const preset = currentSpawnPreset();
    const custom = preset === "custom";
    if (spawnCount) {
      spawnCount.disabled = !custom;
      const field = spawnCount.closest(".spawn-field");
      if (field) field.classList.toggle("is-disabled", !custom);
    }
    if (spawnConfig) {
      spawnConfig.disabled = !custom;
      const field = spawnConfig.closest(".spawn-field");
      if (field) field.classList.toggle("is-disabled", !custom);
    }
  }

  async function refreshAccountPool() {
    if (!poolSummary || !poolTable) return;
    try {
      const resp = await fetch("/swarm/account-pool");
      if (!resp.ok) {
        poolSummary.textContent = "unavailable";
        if (poolRate) poolRate.textContent = "-";
        return;
      }
      const data = await resp.json();
      const pool = data.pool || {};
      const identities = data.identities || {};
      const allAccounts = Array.isArray(pool.accounts) ? pool.accounts : [];
      const accounts = allAccounts.slice(0, 30);
      const total = Number(pool.accounts_total || 0);
      const leased = Number(pool.leased || 0);
      const leasedActive = Number(pool.leased_active ?? leased);
      const leasedStale = Number(pool.leased_stale ?? Math.max(0, leased - leasedActive));
      const cooldown = Number(pool.cooldown || 0);
      const available = Number(pool.available || 0);
      const identityTotal = Number(identities.total || 0);
      const identityActive = Number(identities.active || 0);

      poolSummary.textContent =
        `accounts ${total} | leased ${leasedActive}/${leased} | stale ${leasedStale} | available ${available} | cooldown ${cooldown} | identities ${identityActive}/${identityTotal}`;

      if (poolKpiLeased) poolKpiLeased.textContent = `${leasedActive}/${leased}`;
      if (poolKpiAvailable) poolKpiAvailable.textContent = String(available);
      if (poolKpiCooldown) poolKpiCooldown.textContent = String(cooldown);
      if (poolKpiStale) poolKpiStale.textContent = String(leasedStale);
      if (poolKpiIdentity) poolKpiIdentity.textContent = `${identityActive}/${identityTotal}`;

      const totalUses = allAccounts.reduce((sum, a) => sum + Number(a.use_count || 0), 0);
      const now = Date.now() / 1000;
      let leasesPerMin = 0;
      if (poolLastSample && now > poolLastSample.time) {
        const dtMin = (now - poolLastSample.time) / 60;
        if (dtMin > 0) leasesPerMin = Math.max(0, (totalUses - poolLastSample.totalUses) / dtMin);
      }
      poolLastSample = { time: now, totalUses };
      if (poolRate) poolRate.textContent = `${leasesPerMin.toFixed(2)}/min`;

      const accountUses = new Map(accounts.map((a) => [String(a.account_id || ""), Number(a.use_count || 0)]));
      const accountRates = new Map();
      if (poolAccountLastSample && now > poolAccountLastSample.time) {
        const dtMin = (now - poolAccountLastSample.time) / 60;
        if (dtMin > 0) {
          for (const a of accounts) {
            const accountId = String(a.account_id || "");
            const currentUses = Number(a.use_count || 0);
            const previousUses = Number(poolAccountLastSample.uses.get(accountId) || 0);
            const perMin = Math.max(0, (currentUses - previousUses) / dtMin);
            accountRates.set(accountId, perMin);
            pushAccountRateSample(accountId, perMin);
          }
        }
      }
      if (!poolAccountLastSample) {
        for (const a of accounts) {
          const accountId = String(a.account_id || "");
          accountRates.set(accountId, 0);
          pushAccountRateSample(accountId, 0);
        }
      }
      poolAccountLastSample = { time: now, uses: accountUses };
      const activeAccountIds = new Set(accounts.map((a) => String(a.account_id || "")));
      for (const accountId of Array.from(poolAccountRateHistory.keys())) {
        if (!activeAccountIds.has(accountId)) poolAccountRateHistory.delete(accountId);
      }

      poolTable.innerHTML = accounts.map((a) => {
        const accountId = String(a.account_id || "");
        const leaseBot = (a.lease && a.lease.bot_id) ? String(a.lease.bot_id) : "-";
        const leasedBotStatus = leaseBot !== "-" ? latestBotsById.get(leaseBot) : null;
        const leaseSecondsRemaining = Number(a.lease_seconds_remaining);
        const ttl = Number.isFinite(leaseSecondsRemaining) ? Math.max(0, Math.round(leaseSecondsRemaining)) : null;
        const isHijacked = !!(
          (a.lease && a.lease.is_hijacked) ||
          (leasedBotStatus && leasedBotStatus.is_hijacked)
        );
        const hijackedBy = String(
          ((a.lease && a.lease.hijacked_by) || (leasedBotStatus && leasedBotStatus.hijacked_by) || "")
        ).trim();
        const statusParts = [];
        const leasedState = String((leasedBotStatus && leasedBotStatus.state) || "").toLowerCase();
        const strategyRaw = String(
          ((leasedBotStatus && (leasedBotStatus.strategy_id || leasedBotStatus.strategy)) || "")
        )
          .trim()
          .toLowerCase();
        const strategyNorm = strategyRaw.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
        const isAi = strategyNorm === "ai_strategy" || strategyNorm === "ai";
        if (isAi) statusParts.push(`<span class="pool-status-pill ai">AI</span>`);
        if (isHijacked) statusParts.push(`<span class="pool-status-pill hijacked">Hijacked</span>`);
        if (leasedState === "running") statusParts.push(`<span class="pool-status-pill running">Running</span>`);
        else if (leasedState) statusParts.push(`<span class="pool-status-pill ${esc(leasedState === "error" ? "error" : "active")}">${esc(leasedState)}</span>`);
        if (!statusParts.length) statusParts.push(`<span class="pool-status-pill">-</span>`);
        const ownerMeta = isHijacked && hijackedBy ? `<span class="pool-status-meta">${esc(hijackedBy)}</span>` : "";
        const ttlMeta = ttl != null ? `<span class="pool-status-meta">${esc(String(ttl))}s</span>` : "";
        const statusCell = `<div class="pool-status-cell">${statusParts.join("")}${ownerMeta}${ttlMeta}</div>`;
        const game = formatGameName(a);
        const source = formatSourceName(a.source);
        const lastUsed = a.last_used_at ? formatAgeSeconds(a.last_used_at) : "-";
        const accountRate = Number(accountRates.get(accountId) || 0);
        const history = poolAccountRateHistory.get(accountId) || [0];
        const rateCell = `<div class="pool-row-rate" title="Leases per minute trend for this account (recent polls)">` +
          `<span class="rate">${accountRate.toFixed(2)}/m</span>` +
          `${buildInlineSparkline(history)}` +
        `</div>`;
        return `<tr>
          <td title="${esc(a.username || "-")}">${esc(a.username || "-")}</td>
          <td title="${esc(leaseBot)}">${esc(leaseBot)}</td>
          <td>${statusCell}</td>
          <td title="${esc(game)}">${esc(game)}</td>
          <td><span class="pool-source-chip ${esc(source.raw)}" title="${esc(source.raw)}">${esc(source.label)}</span></td>
          <td class="num">${esc(String(a.use_count || 0))}</td>
          <td>${rateCell}</td>
          <td class="num">${esc(lastUsed)}</td>
        </tr>`;
      }).join("");
      if (!accounts.length) {
        poolTable.innerHTML = `<tr><td colspan="8" style="color: var(--fg2);">No pooled accounts yet</td></tr>`;
      }
    } catch (_) {
      poolSummary.textContent = "unavailable";
      if (poolRate) poolRate.textContent = "-";
    }
  }

  if (btnSpawn) {
    btnSpawn.addEventListener("click", async function () {
      const preset = currentSpawnPreset();
      const presetLabel = currentSpawnPresetLabel();
      const count = parseInt(spawnCount.value, 10) || 5;

      if (preset === "custom" && (count < 1 || count > 100)) {
        showToast("Count must be between 1 and 100", "error");
        return;
      }

      const configs = buildSpawnConfigs();
      if (!configs.length) {
        showToast("No configs selected", "error");
        return;
      }

      try {
        btnSpawn.disabled = true;
        btnSpawn.textContent = "Spawning...";

        const resp = await fetch("/swarm/spawn-batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            config_paths: configs,
            // Spawn serially; TW2002 capacity/backpressure makes concurrent logins unstable.
            group_size: 1,
            group_delay: 12.0
          })
        });

        const data = await resp.json();
        showToast(
          `Spawning ${data.total_bots} bots (${presetLabel}) in ${data.total_groups} groups (~${Math.floor(data.estimated_time_seconds / 60)}m)`,
          "success"
        );

        setTimeout(() => {
          btnSpawn.disabled = false;
          btnSpawn.textContent = "Spawn";
        }, 2000);
      } catch (e) {
        showToast("Spawn failed: " + e.message, "error");
        btnSpawn.disabled = false;
        btnSpawn.textContent = "Spawn";
      }
    });
  }

  if (spawnPreset) {
    if (!spawnPreset.value || String(spawnPreset.value) === "custom") {
      spawnPreset.value = "preset_20_mixed";
    }
    spawnPreset.addEventListener("change", syncSpawnPresetUi);
    syncSpawnPresetUi();
  }

  initTableView();
  poll();
	  connect();
  if (runtimeUiTimer) clearInterval(runtimeUiTimer);
  runtimeUiTimer = setInterval(() => renderRuntimeTick(), 1000);
  renderRuntimeTick();
  if (swarmPollTimer) clearInterval(swarmPollTimer);
  swarmPollTimer = setInterval(poll, 3000);
	  installTableInteractionGuards();
    refreshAccountPool();
    setInterval(refreshAccountPool, 10000);

  // --- Terminal spy/hijack modal (xterm.js) ---
  let termWs = null;
  let term = null;
  let termBotId = null;
  let hijacked = false;
  let hijackedByMe = false;
  let lastTermSnapshot = null;
  let termHeartbeatTimer = null;

  const termModal = $("#term-modal");
  const termTitle = $("#term-title");
  const termStats = $("#term-stats");
  const termStatus = $("#term-status");
  const termEl = $("#term");
  const btnTermHijack = $("#term-hijack");
  const btnTermStep = $("#term-step");
  const btnTermRelease = $("#term-release");
  const btnTermResync = $("#term-resync");
  const btnTermAnalyze = $("#term-analyze");
  const btnTermClose = $("#term-close");
  const termAnalysis = $("#term-analysis");
  const termAnalysisDetails = $("#term-analysis-details");

	  function updateTermStats() {
	    if (!termBotId || !lastData || !lastData.bots || !termStats) return;
	    const bot = lastData.bots.find(b => b.bot_id === termBotId);
	    if (!bot) return;
	    const turnsDisplay = `${bot.turns_executed || 0}`;
	    const activity = bot.activity_context || bot.state || "-";
	    const promptId = (lastTermSnapshot && lastTermSnapshot.prompt_detected && lastTermSnapshot.prompt_detected.prompt_id)
	      ? lastTermSnapshot.prompt_detected.prompt_id
	      : "-";
	    const creditsDisplay = (bot.credits !== undefined && bot.credits !== null && bot.credits >= 0)
	      ? formatCredits(bot.credits)
	      : "-";
      const cptMeta = computeBotCptPresentation(bot);
      const trades = Number(bot.trades_executed || 0);
      const haggleTotal = Number(bot.haggle_accept || 0) + Number(bot.haggle_counter || 0) + Number(bot.haggle_too_high || 0) + Number(bot.haggle_too_low || 0);
      const runCptStyle = cptMeta.runColor ? ` style="color:${cptMeta.runColor}"` : "";
      const adjCptStyle = cptMeta.adjustedColor ? ` style="color:${cptMeta.adjustedColor}"` : "";
	    termStats.innerHTML = [
	      `<span class="stat"><span class="stat-label">Sector</span><span class="stat-value sector">${bot.sector || "-"}</span></span>`,
	      `<span class="stat"><span class="stat-label">Credits</span><span class="stat-value credits">${esc(creditsDisplay)}</span></span>`,
        `<span class="stat"><span class="stat-label">Turns</span><span class="stat-value turns">${turnsDisplay}</span></span>`,
        `<span class="stat"><span class="stat-label">Trades</span><span class="stat-value">${esc(String(trades))}</span></span>`,
        `<span class="stat"><span class="stat-label">Run CPT</span><span class="stat-value"${runCptStyle}>${esc(cptMeta.runText)}</span></span>`,
        `<span class="stat"><span class="stat-label">Adj CPT</span><span class="stat-value"${adjCptStyle}>${esc(cptMeta.adjustedText)}</span></span>`,
        `<span class="stat"><span class="stat-label">Haggles</span><span class="stat-value">${esc(String(haggleTotal))}</span></span>`,
	      `<span class="stat"><span class="stat-label">Prompt</span><span class="stat-value">${esc(promptId)}</span></span>`,
	      `<span class="stat"><span class="stat-label">Strategy</span><span class="stat-value">${esc((bot.strategy || "").trim() || (bot.strategy_id ? (String(bot.strategy_id).trim() + (bot.strategy_mode ? "(" + String(bot.strategy_mode).trim() + ")" : "")) : "-"))}</span></span>`,
	      `<span class="stat"><span class="stat-label">Intent</span><span class="stat-value">${esc((bot.strategy_intent || "-").trim() || "-")}</span></span>`,
	      `<span class="stat"><span class="stat-label">Activity</span><span class="stat-value">${esc(activity)}</span></span>`,
	    ].join("");
	  }

  function ensureTerm() {
    if (term) return term;
    if (!window.Terminal) {
      const msg = "xterm.js not loaded (CDN failed). Hard refresh and check DevTools console.";
      termStatus.innerHTML = '<span class="bad">&#9679; Error</span> ' + esc(msg);
      showToast(msg, "error");
      throw new Error(msg);
    }
    term = new window.Terminal({
      convertEol: true,
      cursorBlink: true,
      fontFamily: "'SF Mono','Fira Code','Cascadia Code',monospace",
      fontSize: 13,
      theme: { background: "#0b0f14" }
    });
    term.open(termEl);
    term.focus();
    // xterm sometimes opens before layout has settled in a modal.
    try { term.refresh(0, term.rows - 1); } catch (_) {}
    term.onData((data) => {
      if (!termWs || termWs.readyState !== WebSocket.OPEN) return;
      if (!hijackedByMe) return;
      termWs.send(JSON.stringify({ type: "input", data }));
    });
    return term;
  }

  function setTermUiState() {
    if (!termWs || termWs.readyState !== WebSocket.OPEN) {
      btnTermHijack.disabled = true;
      if (btnTermStep) btnTermStep.disabled = true;
      btnTermRelease.disabled = true;
      if (btnTermAnalyze) btnTermAnalyze.disabled = true;
      return;
    }
    if (!hijacked) {
      btnTermHijack.disabled = false;
      if (btnTermStep) btnTermStep.disabled = true;
      btnTermRelease.disabled = true;
      if (btnTermAnalyze) btnTermAnalyze.disabled = false;
      return;
    }
    btnTermHijack.disabled = true;
    if (btnTermStep) btnTermStep.disabled = !hijackedByMe;
    btnTermRelease.disabled = !hijackedByMe;
    if (btnTermAnalyze) btnTermAnalyze.disabled = false;
  }

  function connectTerm(botId) {
    // Close existing connection
    if (termWs) {
      try { termWs.close(); } catch (_) {}
      termWs = null;
    }

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = proto + "//" + location.host + "/ws/bot/" + encodeURIComponent(botId) + "/term";
    termWs = new WebSocket(wsUrl);

    termWs.onopen = () => {
      termStatus.innerHTML = '<span class="live">&#9679; Connected</span> (watch)';
      setTermUiState();
      // Ask for a snapshot immediately
      termWs.send(JSON.stringify({ type: "snapshot_req" }));
      if (termHeartbeatTimer) clearInterval(termHeartbeatTimer);
      termHeartbeatTimer = setInterval(() => {
        if (!termWs || termWs.readyState !== WebSocket.OPEN) return;
        if (!hijackedByMe) return;
        termWs.send(JSON.stringify({ type: "heartbeat" }));
      }, 5000);
    };

    termWs.onmessage = (e) => {
      let msg = null;
      try { msg = JSON.parse(e.data); } catch (_) { return; }
      if (!msg || !msg.type) return;

      if (msg.type === "term" && msg.data) {
        try { ensureTerm().write(msg.data); } catch (_) {}
      } else if (msg.type === "snapshot") {
        lastTermSnapshot = msg;
        updateTermStats();
        try {
          const t = ensureTerm();
          t.reset();
          // Clear + home, then write plain snapshot text
          t.write("\u001b[2J\u001b[H");
          const screen = (msg.screen || "").replace(/\n/g, "\r\n");
          t.write(screen);
        } catch (_) {}
      } else if (msg.type === "analysis") {
        const formatted = msg.formatted || "";
        if (termAnalysis) termAnalysis.textContent = formatted || "(no analysis)";
        if (termAnalysisDetails) termAnalysisDetails.open = true;
      } else if (msg.type === "hello") {
        hijacked = !!msg.hijacked;
        hijackedByMe = !!msg.hijacked_by_me;
        setTermUiState();
      } else if (msg.type === "hijack_state") {
        hijacked = !!msg.hijacked;
        hijackedByMe = msg.owner === "me";
        if (hijacked) {
          termStatus.innerHTML = hijackedByMe
            ? '<span class="warn">&#9679; Hijacked (you)</span>'
            : '<span class="bad">&#9679; Hijacked (other)</span>';
        } else {
          termStatus.innerHTML = '<span class="live">&#9679; Connected</span> (watch)';
        }
        setTermUiState();
      } else if (msg.type === "heartbeat_ack") {
        // no-op: useful for debugging lease extension timing in devtools
      } else if (msg.type === "error") {
        termStatus.innerHTML = '<span class="bad">&#9679; Error</span> ' + esc(msg.message || "unknown");
      }
    };

    termWs.onclose = () => {
      termStatus.textContent = "Disconnected";
      hijacked = false;
      hijackedByMe = false;
      setTermUiState();
      if (termHeartbeatTimer) {
        clearInterval(termHeartbeatTimer);
        termHeartbeatTimer = null;
      }
      termWs = null;
    };

    termWs.onerror = () => {
      try { termWs.close(); } catch (_) {}
    };
  }

  window._openTerminal = function (botId) {
    termBotId = botId;
    termTitle.textContent = "Terminal: " + botId;
    termStatus.textContent = "Connecting...";
    hijacked = false;
    hijackedByMe = false;
    lastTermSnapshot = null;
    if (termAnalysis) termAnalysis.textContent = "";
    if (termAnalysisDetails) termAnalysisDetails.open = false;
    updateTermStats();
    termModal.classList.add("open");
    try {
      const t = ensureTerm();
      t.reset();
      t.write("\u001b[2J\u001b[H");
      t.write("Connecting...\r\n");
    } catch (_) {}
    connectTerm(botId);
  };

  function closeTerm() {
    termModal.classList.remove("open");
    termBotId = null;
    hijacked = false;
    hijackedByMe = false;
    lastTermSnapshot = null;
    if (termAnalysis) termAnalysis.textContent = "";
    if (termAnalysisDetails) termAnalysisDetails.open = false;
    if (termWs) {
      try { termWs.close(); } catch (_) {}
      termWs = null;
    }
    if (termHeartbeatTimer) {
      clearInterval(termHeartbeatTimer);
      termHeartbeatTimer = null;
    }
    setTermUiState();
  }

  if (btnTermClose) btnTermClose.addEventListener("click", closeTerm);
  if (termModal) termModal.addEventListener("click", (e) => { if (e.target === termModal) closeTerm(); });
  if (btnTermResync) btnTermResync.addEventListener("click", () => {
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(JSON.stringify({ type: "snapshot_req" }));
    }
  });
  if (btnTermAnalyze) btnTermAnalyze.addEventListener("click", () => {
    if (!termWs || termWs.readyState !== WebSocket.OPEN) return;
    termWs.send(JSON.stringify({ type: "analyze_req" }));
  });
  if (btnTermHijack) btnTermHijack.addEventListener("click", () => {
    if (!termWs || termWs.readyState !== WebSocket.OPEN) return;
    termWs.send(JSON.stringify({ type: "hijack_request" }));
  });
  if (btnTermStep) btnTermStep.addEventListener("click", () => {
    if (!termWs || termWs.readyState !== WebSocket.OPEN) return;
    if (!hijackedByMe) return;
    termWs.send(JSON.stringify({ type: "hijack_step" }));
    // Best-effort refresh: request snapshot/analysis shortly after the worker acts.
    setTimeout(() => {
      if (termWs && termWs.readyState === WebSocket.OPEN) termWs.send(JSON.stringify({ type: "snapshot_req" }));
    }, 250);
    setTimeout(() => {
      if (termWs && termWs.readyState === WebSocket.OPEN) termWs.send(JSON.stringify({ type: "analyze_req" }));
    }, 450);
    setTimeout(() => {
      if (termWs && termWs.readyState === WebSocket.OPEN) termWs.send(JSON.stringify({ type: "snapshot_req" }));
    }, 1000);
    setTimeout(() => {
      if (termWs && termWs.readyState === WebSocket.OPEN) termWs.send(JSON.stringify({ type: "analyze_req" }));
    }, 1200);
  });
  if (btnTermRelease) btnTermRelease.addEventListener("click", () => {
    if (!termWs || termWs.readyState !== WebSocket.OPEN) return;
    termWs.send(JSON.stringify({ type: "hijack_release" }));
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && termModal && termModal.classList.contains("open")) {
      closeTerm();
    }
  });
})();
