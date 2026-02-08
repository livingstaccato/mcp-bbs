// BBSBot Swarm Dashboard - WebSocket client with log viewer
(function () {
  "use strict";

  let sortKey = "bot_id";
  let sortReverse = false;
  let lastData = null;

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

  function getActivityBadge(context) {
    if (!context) return "IDLE";
    if (context.includes("trading") || context.includes("bank")) return "TRADING";
    if (context.includes("battle") || context.includes("combat")) return "BATTLING";
    if (context.includes("explore") || context.includes("navigation") || context.includes("warp")) return "EXPLORING";
    return context.toUpperCase();
  }

  function getActivityClass(activity) {
    const lower = (activity || "").toLowerCase();
    if (lower.includes("trade")) return "trading";
    if (lower.includes("battle")) return "battling";
    if (lower.includes("explore")) return "exploring";
    if (lower.includes("select")) return "selecting";
    if (lower.includes("log") || lower.includes("connect")) return "connecting";
    return "idle";
  }

  // --- Bot table rendering ---
  function update(data) {
    lastData = data;
    $("#running").textContent = data.running;
    $("#total").textContent = data.total_bots;
    $("#completed").textContent = data.completed;
    $("#errors").textContent = data.errors;
    $("#credits").textContent = formatCredits(data.total_credits);
    $("#turns").textContent = formatCredits(data.total_turns);
    $("#uptime").textContent = " | " + formatUptime(data.uptime_seconds);

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
        const isDead = ["completed", "error", "stopped"].includes(b.state);
        const activity = b.activity_context || "IDLE";
        const activityClass = getActivityClass(activity);
        const hasError = b.state === "error" && (b.error_message || b.error_type);

        let activityHtml = `<span class="activity-badge ${activityClass}">${esc(activity)}</span>`;
        if (b.last_action_time) {
          activityHtml += `<br><span style="color: var(--fg2); font-size: 11px;">${formatRelativeTime(b.last_action_time)}</span>`;
        }

        let stateHtml = `<span class="state ${b.state}">${b.state}</span>`;
        if (hasError) {
          stateHtml += ` <span class="error-badge" title="Error: ${esc(b.error_type)}" onclick="window._openErrorModal('${esc(b.bot_id)}')">!</span>`;
        }

        const turns_max = b.turns_max || 500;
        const turnsDisplay = `${b.turns_executed} / ${turns_max}`;

        return `<tr>
        <td>${esc(b.bot_id)}</td>
        <td>${stateHtml}</td>
        <td>${activityHtml}</td>
        <td class="numeric">${b.sector}</td>
        <td class="numeric">${formatCredits(b.credits)}</td>
        <td class="numeric" title="${b.turns_executed} of ${turns_max} turns">${turnsDisplay}</td>
        <td>${esc(b.config || "")}</td>
        <td class="actions">
          <button class="btn logs" onclick="window._openLogs('${esc(b.bot_id)}')">Logs</button>
          <button class="btn restart" onclick="window._restartBot('${esc(b.bot_id)}')" ${isDead ? "" : "disabled"}>Restart</button>
          <button class="btn kill" onclick="window._killBot('${esc(b.bot_id)}')" ${isRunning ? "" : "disabled"}>Kill</button>
        </td>
      </tr>`;
      })
      .join("");
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
      if (lastData) update(lastData);
    });
  });

  // --- Error modal ---
  const errorModalOverlay = $("#error-modal-overlay");
  const errorModalContent = $("#error-modal-content");

  window._openErrorModal = function (botId) {
    if (!lastData || !lastData.bots) return;
    const bot = lastData.bots.find(b => b.bot_id === botId);
    if (!bot || bot.state !== "error") return;

    const timestamp = bot.error_timestamp
      ? new Date(bot.error_timestamp * 1000).toLocaleString()
      : "Unknown";

    const html = `
      <div class="field">
        <div class="label">Bot ID</div>
        <div class="value">${esc(bot.bot_id)}</div>
      </div>
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
      </div>
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

  poll();
  connect();
})();
