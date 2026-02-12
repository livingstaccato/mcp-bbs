// BBSBot Swarm Dashboard - WebSocket client with log viewer
(function () {
  "use strict";

  let sortKey = "bot_id";
  let sortReverse = false;
  let lastData = null;
  let updateTimer = null;  // Debounce timer for table updates
  let tablePointerActive = false;
  let pendingTableData = null;

  const $ = (sel) => document.querySelector(sel);
  const dot = $("#dot");
  const connStatus = $("#conn-status");
  const botListMeta = $("#bot-list-meta");
  const filterStateEl = $("#filter-state");
  const filterStrategyEl = $("#filter-strategy");
  const filterSearchEl = $("#filter-search");
  const filterNoTradeEl = $("#filter-no-trade");
  const strategyFilterOptionSet = new Set();

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
    const hold = () => { tablePointerActive = true; };
    const release = () => {
      tablePointerActive = false;
      flushDeferredTableRender();
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

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function percent(v) {
    if (!isFinite(v)) return "0.0%";
    return (v * 100).toFixed(1) + "%";
  }

  function computeAggregateMetrics(data) {
    const bots = data.bots || [];
    const MIN_TURNS_FOR_CPT = 30;
    const MIN_TRADES_FOR_CPT = 1;
    const MAX_ABS_CPT_PER_BOT = 100.0;
    let accept = 0;
    let counter = 0;
    let tooHigh = 0;
    let tooLow = 0;
    let noTrade120 = 0;
    const nowS = Date.now() / 1000;
    const activeStates = new Set(["running", "recovering", "blocked"]);
    const activeByStrategy = new Map();
    const historicalByStrategy = new Map();

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
      if (turns >= 120 && trades === 0 && String(b.state || "") === "running") {
        noTrade120 += 1;
      }

      const cpt = Number(b.credits_per_turn || 0);
      const turnsExec = Number(b.turns_executed || 0);
      const creditsDelta = Number(b.credits_delta || 0);
      const tradesExec = Number(b.trades_executed || 0);
      const sid = (b.strategy_id || b.strategy || "unknown").toString();
      const mode = (b.strategy_mode || "unknown").toString();
      const key = `${sid}(${mode})`;
      const state = String(b.state || "").toLowerCase();
      const lastUpdate = Number(b.last_update_time || 0);
      const isFresh = lastUpdate > 0 && nowS - lastUpdate <= 120;
      const bucketMap = (activeStates.has(state) && isFresh) ? activeByStrategy : historicalByStrategy;
      if (!bucketMap.has(key)) {
        bucketMap.set(key, { sumCpt: 0, n: 0, sumDelta: 0, sumTurns: 0, samplesSkipped: 0 });
      }
      const bucket = bucketMap.get(key);

      const hasSufficientTurns = isFinite(turnsExec) && turnsExec >= MIN_TURNS_FOR_CPT;
      const hasTrades = isFinite(tradesExec) && tradesExec >= MIN_TRADES_FOR_CPT;
      const hasValidDelta = isFinite(creditsDelta) && isFinite(turnsExec) && turnsExec > 0;
      const perBotCpt = hasValidDelta ? (creditsDelta / turnsExec) : cpt;
      const isOutlier = !isFinite(perBotCpt) || Math.abs(perBotCpt) > MAX_ABS_CPT_PER_BOT;

      if (hasSufficientTurns && hasTrades && hasValidDelta && !isOutlier) {
        bucket.sumCpt += perBotCpt;
        bucket.n += 1;
        bucket.sumTurns += turnsExec;
        bucket.sumDelta += creditsDelta;
      } else {
        bucket.samplesSkipped += 1;
      }
    }

    const offers = accept + counter + tooHigh + tooLow;
    const acceptRate = offers > 0 ? accept / offers : 0;
    const tooHighRate = offers > 0 ? tooHigh / offers : 0;
    const tooLowRate = offers > 0 ? tooLow / offers : 0;

    const toLines = (label, byStrategy) =>
      Array.from(byStrategy.entries())
      .map(([k, v]) => {
        const weighted = v.sumTurns > 0 ? v.sumDelta / v.sumTurns : NaN;
        const unweighted = v.n > 0 ? v.sumCpt / v.n : 0;
        const avg = isFinite(weighted) ? weighted : unweighted;
        return { key: k, avg, n: v.n, turns: v.sumTurns, samplesSkipped: v.samplesSkipped || 0 };
      })
      .filter((x) => x.n > 0)
      .filter((x) => !(x.avg === 0 && x.key.toLowerCase().includes("(unknown)")))
      .sort((a, b) => b.avg - a.avg)
      .slice(0, 3)
      .map((x) => ({
        text: `${label} ${x.key}: ${x.avg.toFixed(2)} (n=${x.n}${x.samplesSkipped ? `, skip=${x.samplesSkipped}` : ""})`,
        lowConfidence: x.n < 3 || x.turns < 200,
      }));

    const strategyLines = [
      ...toLines("ACTIVE", activeByStrategy),
      ...toLines("HIST", historicalByStrategy),
    ];

    return { acceptRate, tooHighRate, tooLowRate, noTrade120, strategyLines };
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
    if (lower.includes("battle") || lower.includes("combat")) return "BATTLING";
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

  function getStrategyCompact(bot) {
    const rawId = String(bot.strategy_id || bot.strategy || "").trim();
    const rawMode = String(bot.strategy_mode || "").trim();
    const id = ({
      profitable_pairs: "pairs",
      opportunistic: "opp",
      ai_strategy: "ai",
    }[rawId] || rawId || "-");
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

  function matchesTextFilter(bot, q) {
    if (!q) return true;
    const fields = [
      bot.bot_id,
      bot.state,
      bot.activity_context,
      bot.status_detail,
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
	    lastData = data;
	    // Update stats immediately (lightweight)
	    $("#running").textContent = data.running;
	    $("#total").textContent = data.total_bots;
	    $("#completed").textContent = data.completed;
	    $("#errors").textContent = data.errors;
	    $("#credits").textContent = formatCredits(data.total_credits);
	    $("#turns").textContent = formatCredits(data.total_turns);
    const uptimeText = formatUptime(data.uptime_seconds);
    const uptimeEl = $("#uptime");
    if (uptimeEl) uptimeEl.textContent = " | " + uptimeText;
    const connectedForEl = $("#connected-for");
    if (connectedForEl) connectedForEl.textContent = uptimeText;

      const metrics = computeAggregateMetrics(data);
      const acceptEl = $("#accept-rate");
      const highEl = $("#too-high-rate");
      const lowEl = $("#too-low-rate");
      const noTradeEl = $("#no-trade-120");
      const strategyEl = $("#strategy-cpt");
      if (acceptEl) acceptEl.textContent = percent(metrics.acceptRate);
      if (highEl) highEl.textContent = percent(metrics.tooHighRate);
      if (lowEl) lowEl.textContent = percent(metrics.tooLowRate);
      if (noTradeEl) noTradeEl.textContent = String(metrics.noTrade120);
      if (strategyEl) {
        if (metrics.strategyLines.length) {
          strategyEl.innerHTML = `<span class="strategy-cpt-lines">${metrics.strategyLines
            .map((line) => {
              const cls = line.lowConfidence ? "strategy-cpt-line low-confidence" : "strategy-cpt-line";
              return `<span class="${cls}" title="${esc(line.text)}">${esc(line.text)}</span>`;
            })
            .join("")}</span>`;
        } else {
          strategyEl.textContent = "-";
        }
      }

	    // Throttle (not debounce) table re-render.
	    // Under high-frequency status broadcasts, a debounce can starve the table
	    // and it will never render. Keep lastData and render at most every 300ms.
	    if (updateTimer) return;
	    updateTimer = setTimeout(() => {
	      updateTimer = null;
	      renderOrDeferTable(lastData || data);
	    }, 300);
	  }

  function renderBotTable(data) {
    const allBots = data.bots || [];
    syncStrategyFilterOptions(allBots);
    const filteredBots = applyFilters(allBots);
    if (botListMeta) {
      botListMeta.textContent = `${filteredBots.length} visible / ${allBots.length} total`;
    }

    const bots = filteredBots.slice().sort((a, b) => {
      let va = a[sortKey] ?? "";
      let vb = b[sortKey] ?? "";
      if (typeof va === "number") {
        return sortReverse ? vb - va : va - vb;
      }
      va = String(va);
      vb = String(vb);
      return sortReverse ? vb.localeCompare(va) : va.localeCompare(vb);
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

        const activityClass = getActivityClass(activity);
        const activityPrimary = `<span class="activity-badge ${activityClass}">${esc(activity)}</span>`;

        const stateClass = String(b.state || "unknown").toLowerCase();
        const stateHtml = `<span class="state-dot ${esc(stateClass)}" title="${esc(String(b.state || "unknown"))}"></span>`;

        // Status: phase/prompt detail (Paused, Username/Password, Port Haggle, etc.)
        // Hijack is additive; it shouldn't replace the bot's true activity.
        const statusParts = [];
        if (b.is_hijacked) {
          statusParts.push("HIJACKED");
        }
        const lifecycleLabel = {
          blocked: "BLOCKED",
          recovering: "RECOVERING",
          disconnected: "DISCONNECTED",
          error: "ERROR",
          stopped: "STOPPED",
          queued: "QUEUED",
          completed: "COMPLETED",
        }[b.state];
        if (lifecycleLabel) {
          const withReason = (b.exit_reason && ["blocked", "error", "disconnected"].includes(b.state))
            ? `${lifecycleLabel} (${b.exit_reason})`
            : lifecycleLabel;
          statusParts.push(withReason);
        }
        const detail = (b.status_detail || "").trim();
        const isStaleOrientFailed =
          detail === "ORIENTING:FAILED" &&
          b.state === "running" &&
          !["CONNECTING", "LOGGING_IN", "INITIALIZING"].includes(String(activity || "").toUpperCase());
        if (detail) {
          if (!isStaleOrientFailed) {
            statusParts.push(detail);
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
            statusParts.push(b.prompt_id);
          }
        }
        const statusText = statusParts.length ? statusParts.join(" | ") : "-";
        const compactStatus = compactStatusText(`${statusText}${exitInfo ? " " + exitInfo : ""}`);
        const activityHtml = `<div class="activity-cell" onclick="window._openInspector('${esc(b.bot_id)}','activity')" title="${esc(statusText)}"><span class="activity-primary">${activityPrimary}</span>${compactStatus ? `<span class="activity-secondary">${esc(compactStatus)}</span>` : ""}</div>`;

        const turnsDisplay = `${b.turns_executed}`;
        const updatedDisplay = b.last_action_time ? formatRelativeTime(b.last_action_time) : "-";

        // Display "-" for uninitialized numeric fields
        const creditsDisplay = b.credits >= 0 ? formatCredits(b.credits) : "-";
        const fuelDisplay = (b.cargo_fuel_ore === null || b.cargo_fuel_ore === undefined) ? "-" : formatCredits(b.cargo_fuel_ore);
        const orgDisplay = (b.cargo_organics === null || b.cargo_organics === undefined) ? "-" : formatCredits(b.cargo_organics);
        const equipDisplay = (b.cargo_equipment === null || b.cargo_equipment === undefined) ? "-" : formatCredits(b.cargo_equipment);

        const compact = getStrategyCompact(b);
        const strategyNote = getStrategyNote(b);
        const strategyTitle = strategyNote ? `${compact.full} | ${strategyNote}` : compact.full;
        const strategyHtml = compact.id === "-"
          ? "-"
          : `<div class="strategy-cell" title="${esc(strategyTitle)}">` +
              `<span class="strategy-chip-row">` +
                `<span class="chip sid">${esc(compact.id)}</span>` +
                (compact.mode ? `<span class="chip mode">${esc(compact.mode)}</span>` : "") +
              `</span>` +
              (strategyNote ? `<div class="strategy-intent">${esc(strategyNote)}</div>` : "") +
            `</div>`;

        return `<tr>
	        <td title="${esc(b.bot_id)}">${esc(shortBotId(b.bot_id))}</td>
	        <td>${stateHtml}</td>
	        <td>${activityHtml}</td>
	        <td>${strategyHtml}</td>
	        <td class="numeric">${b.sector}</td>
	        <td class="numeric">${creditsDisplay}</td>
	        <td class="numeric">${fuelDisplay}</td>
	        <td class="numeric">${orgDisplay}</td>
	        <td class="numeric">${equipDisplay}</td>
	        <td class="numeric">${turnsDisplay}</td>
	        <td class="timecell">${updatedDisplay}</td>
	        <td class="actions">
	          <button class="btn more" onclick="window._openInspector('${esc(b.bot_id)}')" title="Inspect">...</button>
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

  [filterStateEl, filterStrategyEl, filterNoTradeEl].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", () => {
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
    const cpt = Number(bot.credits_per_turn || 0);

    if (errorModalTitle) errorModalTitle.textContent = "Bot Metrics";
    errorModalContent.innerHTML = `
      <div class="field"><div class="label">Bot ID</div><div class="value">${esc(bot.bot_id)}</div></div>
      <div class="field"><div class="label">Strategy</div><div class="value">${esc((bot.strategy || bot.strategy_id || "-") + (bot.strategy_mode ? " (" + bot.strategy_mode + ")" : ""))}</div></div>
      <div class="field"><div class="label">Trades Executed</div><div class="value">${esc(String(bot.trades_executed || 0))}</div></div>
      <div class="field"><div class="label">Credits Delta</div><div class="value">${esc(String(creditsDelta))}</div></div>
      <div class="field"><div class="label">Credits / Turn</div><div class="value">${esc(cpt.toFixed(2))}</div></div>
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
    const cpt = Number(bot.credits_per_turn || 0);
    logContent.innerHTML = `
      <div class="field"><div class="label">Bot ID</div><div class="value">${esc(bot.bot_id)}</div></div>
      <div class="field"><div class="label">State</div><div class="value">${esc(bot.state || "-")}</div></div>
      <div class="field"><div class="label">Strategy</div><div class="value">${esc(getStrategyLabel(bot))}</div></div>
      <div class="field"><div class="label">Trades Executed</div><div class="value">${esc(String(bot.trades_executed || 0))}</div></div>
      <div class="field"><div class="label">Credits Delta</div><div class="value">${esc(String(creditsDelta))}</div></div>
      <div class="field"><div class="label">Credits / Turn</div><div class="value">${esc(cpt.toFixed(2))}</div></div>
      <div class="field"><div class="label">Haggle Accept</div><div class="value">${esc(String(haggleAccept))}</div></div>
      <div class="field"><div class="label">Haggle Counter</div><div class="value">${esc(String(haggleCounter))}</div></div>
      <div class="field"><div class="label">Haggle Too High</div><div class="value">${esc(String(haggleHigh))}</div></div>
      <div class="field"><div class="label">Haggle Too Low</div><div class="value">${esc(String(haggleLow))}</div></div>
      <div class="field"><div class="label">Haggle Accept Rate</div><div class="value">${esc(acceptRate)}</div></div>
    `;
  }

  function renderInspectorTerminalTab(botId) {
    logContent.innerHTML = `
      <div class="field">
        <div class="label">Terminal Control</div>
        <div class="value">Live spy/hijack stays in the dedicated terminal panel.</div>
      </div>
      <div class="field">
        <button class="btn logs" id="inspector-open-terminal">Open Live Terminal</button>
      </div>
    `;
    const btn = $("#inspector-open-terminal");
    if (btn) btn.addEventListener("click", () => window._openTerminal(botId));
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
      logStatus.textContent = "Terminal";
      renderInspectorTerminalTab(botId);
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
      return (event.action || "UNKNOWN") + atSector;
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

  function renderActivityLedger(events) {
    if (!events.length) {
      logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--fg2); padding: 12px 16px;\">No activity events yet</div>";
      return;
    }

    const rows = events
      .map((event) => {
        const time = new Date((event.timestamp || 0) * 1000).toLocaleTimeString();
        const eventType = formatEventType(event);
        const what = buildEventWhat(event);
        const why = buildEventWhy(event);
        const strategy = buildEventStrategy(event);
        const sector = event.sector != null ? String(event.sector) : "-";
        const credits = (event.credits != null && Number(event.credits) >= 0)
          ? formatCredits(Number(event.credits))
          : "-";
        const turns = event.turns_executed != null ? String(event.turns_executed) : "-";
        const startedAt = event.started_at || null;
        const stoppedAt = event.stopped_at || null;
        const startedRel = formatRelativeStamp(startedAt);
        const stoppedRel = formatRelativeStamp(stoppedAt);
        const startedAbs = formatAbsoluteTime(startedAt);
        const stoppedAbs = formatAbsoluteTime(stoppedAt);
        const resultDelta = (event.result_delta != null && Number(event.result_delta) !== 0)
          ? (Number(event.result_delta) > 0 ? ` Δ+${formatCredits(Number(event.result_delta))}` : ` Δ${formatCredits(Number(event.result_delta))}`)
          : "";
        const resultRaw = String(event.result || (event.type === "error" ? "failure" : "")).toLowerCase();
        const resultText = resultRaw || "-";
        const resultCls =
          resultRaw === "success" ? "activity-result-success" :
          resultRaw === "failure" || resultRaw === "error" ? "activity-result-failure" :
          resultRaw === "pending" ? "activity-result-pending" : "";

        return `<tr>
          <td class="activity-col-time">${esc(time)}</td>
          <td class="activity-col-type">${esc(eventType)}</td>
          <td class="activity-col-what">${esc(what)}</td>
          <td class="activity-col-why" title="${esc(why)}">${esc(why || "-")}</td>
          <td class="activity-col-strategy">${esc(strategy)}</td>
          <td class="activity-col-sector">${esc(sector)}</td>
          <td class="activity-col-credits">${esc(credits)}</td>
          <td class="activity-col-turns">${esc(turns)}</td>
          <td class="activity-col-start" title="${esc(startedAbs)}">${esc(startedRel)}</td>
          <td class="activity-col-stop" title="${esc(stoppedAbs)}">${esc(stoppedRel)}</td>
          <td class="activity-col-result ${resultCls}">${esc(resultText + resultDelta)}</td>
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
      setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 2000);
    };

    ws.onmessage = (e) => {
      try {
        update(JSON.parse(e.data));
      } catch (_) {}
    };

    ws.onclose = () => {
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
      if (resp.ok) update(await resp.json());
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

  function buildSpawnConfigs() {
    const preset = (spawnPreset && spawnPreset.value) ? String(spawnPreset.value) : "custom";
    if (preset === "mix_5_ai_35_dynamic") {
      return [
        ..._buildRange("swarm_demo_ai", 5, 1),
        ..._buildRange("swarm_demo", 35, 1),
      ];
    }
    if (preset === "mix_20_ai_20_dynamic") {
      return [
        ..._buildRange("swarm_demo_ai", 20, 1),
        ..._buildRange("swarm_demo", 20, 1),
      ];
    }
    const count = parseInt(spawnCount.value, 10) || 5;
    const configDir = spawnConfig.value || "swarm_demo";
    return _buildRange(configDir, count, 1);
  }

  function syncSpawnPresetUi() {
    const preset = (spawnPreset && spawnPreset.value) ? String(spawnPreset.value) : "custom";
    const custom = preset === "custom";
    if (spawnCount) spawnCount.disabled = !custom;
    if (spawnConfig) spawnConfig.disabled = !custom;
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
      const accounts = Array.isArray(pool.accounts) ? pool.accounts.slice(0, 12) : [];
      const total = Number(pool.accounts_total || 0);
      const leased = Number(pool.leased || 0);
      const cooldown = Number(pool.cooldown || 0);
      const available = Number(pool.available || 0);
      const identityTotal = Number(identities.total || 0);
      const identityActive = Number(identities.active || 0);

      poolSummary.textContent =
        `${total} | leased ${leased} | avail ${available} | cool ${cooldown} | id ${identityActive}/${identityTotal}`;

      if (poolKpiLeased) poolKpiLeased.textContent = `${leased}/${total}`;
      if (poolKpiAvailable) poolKpiAvailable.textContent = String(available);
      if (poolKpiCooldown) poolKpiCooldown.textContent = String(cooldown);
      if (poolKpiIdentity) poolKpiIdentity.textContent = `${identityActive}/${identityTotal}`;

      const totalUses = accounts.reduce((sum, a) => sum + Number(a.use_count || 0), 0);
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
        const leaseBot = (a.lease && a.lease.bot_id) ? a.lease.bot_id : "-";
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
          <td title="${esc(game)}">${esc(game)}</td>
          <td><span class="pool-source-chip ${esc(source.raw)}" title="${esc(source.raw)}">${esc(source.label)}</span></td>
          <td class="num">${esc(String(a.use_count || 0))}</td>
          <td>${rateCell}</td>
          <td class="num">${esc(lastUsed)}</td>
        </tr>`;
      }).join("");
      if (!accounts.length) {
        poolTable.innerHTML = `<tr><td colspan="7" style="color: var(--fg2);">No pooled accounts yet</td></tr>`;
      }
    } catch (_) {
      poolSummary.textContent = "unavailable";
      if (poolRate) poolRate.textContent = "-";
    }
  }

  if (btnSpawn) {
    btnSpawn.addEventListener("click", async function () {
      const preset = (spawnPreset && spawnPreset.value) ? String(spawnPreset.value) : "custom";
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
          `Spawning ${data.total_bots} bots (${preset}) in ${data.total_groups} groups (~${Math.floor(data.estimated_time_seconds / 60)}m)`,
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
    spawnPreset.addEventListener("change", syncSpawnPresetUi);
    syncSpawnPresetUi();
  }

	  poll();
	  connect();
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
      const cpt = Number(bot.credits_per_turn || 0);
      const trades = Number(bot.trades_executed || 0);
      const haggleTotal = Number(bot.haggle_accept || 0) + Number(bot.haggle_counter || 0) + Number(bot.haggle_too_high || 0) + Number(bot.haggle_too_low || 0);
	    termStats.innerHTML = [
	      `<span class="stat"><span class="stat-label">Sector</span><span class="stat-value sector">${bot.sector || "-"}</span></span>`,
	      `<span class="stat"><span class="stat-label">Credits</span><span class="stat-value credits">${esc(creditsDisplay)}</span></span>`,
	      `<span class="stat"><span class="stat-label">Turns</span><span class="stat-value turns">${turnsDisplay}</span></span>`,
        `<span class="stat"><span class="stat-label">Trades</span><span class="stat-value">${esc(String(trades))}</span></span>`,
        `<span class="stat"><span class="stat-label">C/T</span><span class="stat-value">${esc(cpt.toFixed(2))}</span></span>`,
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
