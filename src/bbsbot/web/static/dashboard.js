// BBSBot Swarm Dashboard - WebSocket client with log viewer
(function () {
  "use strict";

  let sortKey = "bot_id";
  let sortReverse = false;
  let lastData = null;
  let updateTimer = null;  // Debounce timer for table updates

  const $ = (sel) => document.querySelector(sel);
  const dot = $("#dot");
  const connStatus = $("#conn-status");

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

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
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
	    $("#uptime").textContent = " | " + formatUptime(data.uptime_seconds);

	    // Throttle (not debounce) table re-render.
	    // Under high-frequency status broadcasts, a debounce can starve the table
	    // and it will never render. Keep lastData and render at most every 300ms.
	    if (updateTimer) return;
	    updateTimer = setTimeout(() => {
	      updateTimer = null;
	      renderBotTable(lastData || data);
	    }, 300);
	  }

  function renderBotTable(data) {
    const bots = (data.bots || []).slice().sort((a, b) => {
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
        const isDead = ["completed", "error", "stopped", "disconnected", "blocked"].includes(b.state);
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
        } else if (b.state === "blocked") {
          activity = b.activity_context ? getActivityBadge(b.activity_context) : "BLOCKED";
          if (b.exit_reason) {
            exitInfo = ` (${b.exit_reason})`;
          }
        } else {
          activity = getActivityBadge(b.activity_context || (isQueued ? "QUEUED" : isDead ? b.state : "IDLE"));
        }

        const activityClass = getActivityClass(activity);
        let activityHtml = `<span class="activity-badge ${activityClass}">${esc(activity)}${exitInfo ? `<span style="color: var(--fg2); font-size: 11px;">${esc(exitInfo)}</span>` : ""}</span>`;
        if (b.last_action_time && isRunning) {
          activityHtml += `<br><span style="color: var(--fg2); font-size: 11px;">${formatRelativeTime(b.last_action_time)}</span>`;
        }

        const stateEmoji = {running: "🟢", completed: "🔵", error: "🔴", blocked: "🟠", recovering: "🟡", stopped: "⚫", queued: "🟡", warning: "🟠", disconnected: "🔴"}[b.state] || "⚪";
        let stateHtml = `<span class="state ${b.state}" title="${b.state}" style="cursor:pointer" onclick="window._openErrorModal('${esc(b.bot_id)}')">${stateEmoji}</span>`;

        // Status: phase/prompt detail (Paused, Username/Password, Port Haggle, etc.)
        // Hijack is additive; it shouldn't replace the bot's true activity.
        let statusHtml = "";
        if (b.is_hijacked) {
          const hijackedTime = b.hijacked_at ? new Date(b.hijacked_at * 1000).toLocaleTimeString() : "now";
          statusHtml += `<span class="hijack-badge" title="Hijacked at ${hijackedTime} by ${esc(b.hijacked_by || '-')}" style="margin-right:6px;">🔒 HIJACKED</span>`;
        }
        const detail = (b.status_detail || "").trim();
        if (detail) {
          statusHtml += `<span class="status-detail">${esc(detail)}</span>`;
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
            statusHtml += `<span class="status-detail" style="color: var(--fg2);" title="prompt_id">${esc(b.prompt_id)}</span>`;
          }
        } else if (!statusHtml) {
          statusHtml = "-";
        }

        const turnsDisplay = `${b.turns_executed}`;

        // Display "-" for uninitialized numeric fields
        const creditsDisplay = b.credits >= 0 ? formatCredits(b.credits) : "-";
        const fuelDisplay = (b.cargo_fuel_ore === null || b.cargo_fuel_ore === undefined) ? "-" : formatCredits(b.cargo_fuel_ore);
        const orgDisplay = (b.cargo_organics === null || b.cargo_organics === undefined) ? "-" : formatCredits(b.cargo_organics);
        const equipDisplay = (b.cargo_equipment === null || b.cargo_equipment === undefined) ? "-" : formatCredits(b.cargo_equipment);

        const strategyMain =
          (b.strategy && String(b.strategy).trim()) ||
          ((b.strategy_id ? String(b.strategy_id).trim() : "") +
            (b.strategy_mode ? `(${String(b.strategy_mode).trim()})` : "")) ||
          "-";
        const strategyIntent = (b.strategy_intent || "").trim();
        const strategyHtml =
          `<div class="strategy-cell"><div class="strategy-main">${esc(strategyMain)}</div>` +
          (strategyIntent ? `<div class="strategy-intent" title="${esc(strategyIntent)}">${esc(strategyIntent)}</div>` : "") +
          `</div>`;

        return `<tr>
	        <td title="${esc(b.bot_id)}">${esc(shortBotId(b.bot_id))}</td>
	        <td>${stateHtml}</td>
	        <td>${activityHtml}</td>
	        <td>${statusHtml}</td>
	        <td>${strategyHtml}</td>
	        <td class="numeric">${b.sector}</td>
	        <td class="numeric">${creditsDisplay}</td>
	        <td class="numeric">${fuelDisplay}</td>
	        <td class="numeric">${orgDisplay}</td>
	        <td class="numeric">${equipDisplay}</td>
	        <td class="numeric">${turnsDisplay}</td>
	        <td class="actions">
	          <button class="btn logs" onclick="window._openTerminal('${esc(b.bot_id)}')" title="Terminal">🖥️</button>
          <button class="btn logs" onclick="window._openEventLedger('${esc(b.bot_id)}')" title="Activity">📊</button>
          <button class="btn" onclick="window._openLogs('${esc(b.bot_id)}')" style="border-color:var(--fg2);color:var(--fg2);" title="Logs">📝</button>
          <button class="btn restart" onclick="window._restartBot('${esc(b.bot_id)}')" ${isDead ? "" : "disabled"} title="Restart">🔄</button>
          <button class="btn kill" onclick="window._killBot('${esc(b.bot_id)}')" ${isRunning ? "" : "disabled"} title="Kill">⏹️</button>
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
        renderBotTable(lastData);
      }
    });
  });

  // --- Error modal ---
  const errorModalOverlay = $("#error-modal-overlay");
  const errorModalContent = $("#error-modal-content");

  window._openErrorModal = function (botId) {
    if (!lastData || !lastData.bots) return;
    const bot = lastData.bots.find(b => b.bot_id === botId);
    if (!bot) return;

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

  // --- Log viewer modal ---
  let logWs = null;
  let logAutoScroll = true;

  const logModal = $("#log-modal");
  const logTitle = $("#log-title");
  const logStatus = $("#log-status");
  const logContent = $("#log-content");

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

  window._openLogs = function (botId) {
    // Close existing
    if (logWs) {
      logWs.close();
      logWs = null;
    }

    logContent.innerHTML = "";
    logTitle.textContent = "Logs: " + botId;
    logStatus.innerHTML = "Connecting...";
    logAutoScroll = true;
    logModal.classList.add("open");

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
      logStatus.textContent = "Disconnected";
      logWs = null;
    };

    logWs.onerror = function () {
      logStatus.textContent = "Connection error";
    };
  };

  function closeLogs() {
    logModal.classList.remove("open");
    if (logWs) {
      logWs.close();
      logWs = null;
    }
  }

  $("#log-close").addEventListener("click", closeLogs);
  logModal.addEventListener("click", function (e) {
    if (e.target === logModal) closeLogs();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && logModal.classList.contains("open")) {
      closeLogs();
    }
  });

  // --- Event ledger (simplified activity log) ---
  window._openEventLedger = async function (botId) {
    // Use the same modal as logs but with event ledger content
    if (logWs) {
      logWs.close();
      logWs = null;
    }

    logContent.innerHTML = "";
    logTitle.textContent = "Activity: " + botId;
    logStatus.innerHTML = "Loading...";
    logAutoScroll = true;
    logModal.classList.add("open");

    try {
      const resp = await fetch("/bot/" + encodeURIComponent(botId) + "/events");
      if (!resp.ok) {
        logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--red);\">Error: " + resp.status + " " + resp.statusText + "</div>";
        logStatus.textContent = "Error";
        return;
      }

      const data = await resp.json();
      const events = data.events || [];

      if (events.length === 0) {
        logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--fg2);\">No events yet</div>";
        logStatus.textContent = "Loaded";
        return;
      }

      const lines = [];
      for (const event of events) {
        const time = new Date(event.timestamp * 1000).toLocaleTimeString();
        let line = time + " ";

        if (event.type === "action") {
          line += "[ACTION] " + event.action + " @ sector " + event.sector;
          if (event.result) line += " → " + event.result;
          if (event.details) line += " (" + event.details + ")";
        } else if (event.type === "error") {
          line += "[ERROR] " + (event.error_type || "Unknown error") + ": " + (event.error_message || "");
        } else if (event.type === "status_update") {
          line += "[STATUS] " + event.state + " | " + (event.activity || "idle");
          if (event.sector) line += " @ " + event.sector;
          line += " | Credits: " + formatCredits(event.credits || 0) + " | Turns: " + (event.turns_executed || 0);
        }

        lines.push(line);
      }

      appendLogLines(lines);
      logStatus.textContent = "Loaded " + events.length + " events";
    } catch (e) {
      logContent.innerHTML = "<div class=\"log-line\" style=\"color: var(--red);\">Network error: " + e.message + "</div>";
      logStatus.textContent = "Error";
    }
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
  const spawnCount = $("#spawn-count");
  const spawnConfig = $("#spawn-config");

  if (btnSpawn) {
    btnSpawn.addEventListener("click", async function () {
      const count = parseInt(spawnCount.value) || 5;
      const configDir = spawnConfig.value || "swarm_demo";

      if (count < 1 || count > 100) {
        showToast("Count must be between 1 and 100", "error");
        return;
      }

      // Build list of config paths
      const configs = [];
      for (let i = 1; i <= count; i++) {
        configs.push(`config/${configDir}/bot_${String(i).padStart(2, '0')}.yaml`);
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
        showToast(`Spawning ${data.total_bots} bots in ${data.total_groups} groups (~${Math.floor(data.estimated_time_seconds / 60)}m)`, "success");

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

  poll();
  connect();

  // --- Terminal spy/hijack modal (xterm.js) ---
  let termWs = null;
  let term = null;
  let termBotId = null;
  let hijacked = false;
  let hijackedByMe = false;
  let lastTermSnapshot = null;

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
	    termStats.innerHTML = [
	      `<span class="stat"><span class="stat-label">Sector</span><span class="stat-value sector">${bot.sector || "-"}</span></span>`,
	      `<span class="stat"><span class="stat-label">Credits</span><span class="stat-value credits">${esc(creditsDisplay)}</span></span>`,
	      `<span class="stat"><span class="stat-label">Turns</span><span class="stat-value turns">${turnsDisplay}</span></span>`,
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
      } else if (msg.type === "error") {
        termStatus.innerHTML = '<span class="bad">&#9679; Error</span> ' + esc(msg.message || "unknown");
      }
    };

    termWs.onclose = () => {
      termStatus.textContent = "Disconnected";
      hijacked = false;
      hijackedByMe = false;
      setTermUiState();
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
