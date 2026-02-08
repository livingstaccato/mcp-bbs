// BBSBot Swarm Dashboard - WebSocket client
(function () {
  "use strict";

  let sortKey = "bot_id";
  let sortReverse = false;
  let lastData = null;

  const $ = (sel) => document.querySelector(sel);
  const dot = $("#dot");
  const connStatus = $("#conn-status");

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
      .map(
        (b) => `<tr>
        <td>${esc(b.bot_id)}</td>
        <td><span class="state ${b.state}">${b.state}</span></td>
        <td class="numeric">${b.sector}</td>
        <td class="numeric">${formatCredits(b.credits)}</td>
        <td class="numeric">${b.turns_executed}</td>
        <td>${esc(b.config || "")}</td>
      </tr>`
      )
      .join("");
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // Sort headers
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

  // WebSocket connection
  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(proto + "//" + location.host + "/ws/swarm");

    ws.onopen = () => {
      dot.className = "dot connected";
      connStatus.textContent = "Connected";
      // Send periodic pings to trigger server broadcasts
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

  // Fallback: poll via HTTP if WS fails
  async function poll() {
    try {
      const resp = await fetch("/swarm/status");
      if (resp.ok) update(await resp.json());
    } catch (_) {}
  }

  // Initial data load via HTTP, then WS
  poll();
  connect();
})();
