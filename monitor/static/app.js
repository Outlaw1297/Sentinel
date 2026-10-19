let refreshTimer = null;
let lastScheduledRefreshMs = null;
let screenshotTimer = null;
let refreshIntervalMs = 10000;
let refreshIntervalActiveMs = 5000;
let refreshIntervalHiddenMs = 120000;
let screenshotIntervalMs = 60000;
let lastPayload = null;
let commandCatalog = null;
let commandBusy = false;
let accountToggleBusy = false;
let accountSortMode = localStorage.getItem("gnbotsAccountSort") || "running-first";
let logTabMode = localStorage.getItem("gnbotsLogTab") || "issues";
let logLevelFilter = localStorage.getItem("gnbotsLogLevelFilter") || "problems";
let logAccountFilter = localStorage.getItem("gnbotsLogAccountFilter") || "";

const DEFAULT_COMMAND_CATALOG = {
  global: [
    { id: "start", label: "Start", confirm: "Start the bot for all configured sessions?" },
    { id: "stop", label: "Stop", confirm: "Stop the current bot run?" },
    { id: "stopall", label: "Stop All", confirm: "Stop all active sessions?" },
    {
      id: "stopemulators",
      label: "Stop Emulators",
      confirm: "Stop all emulators? This will close every LDPlayer instance.",
    },
  ],
  sessionRunCodes: [],
};

function activeCatalog() {
  return commandCatalog || DEFAULT_COMMAND_CATALOG;
}

let shutdownTimerId = null;
let lastWatcherSnapshot = null;
let lastStackSnapshot = null;
let shutdownAfterMinutesConfig = 0;
const DEFAULT_SHUTDOWN_MINUTES = 30;

const els = {
  profileLabel: document.getElementById("profile-label"),
  gnbotsStatus: document.getElementById("gnbots-status"),
  stackPills: document.getElementById("stack-pills"),
  lastUpdated: document.getElementById("last-updated"),
  refreshBtn: document.getElementById("refresh-btn"),
  stats: document.getElementById("stats"),
  globalControls: document.getElementById("global-controls"),
  commandStatus: document.getElementById("command-status"),
  hostStatus: document.getElementById("host-status"),
  resourcesBody: document.getElementById("resources-body"),
  accountsGrid: document.getElementById("accounts-grid"),
  accountSearch: document.getElementById("account-search"),
  accountSort: document.getElementById("account-sort"),
  logList: document.getElementById("log-list"),
  logSummary: document.getElementById("log-summary"),
  logOcrNotice: document.getElementById("log-ocr-notice"),
  logSearch: document.getElementById("log-search"),
  logLevelFilter: document.getElementById("log-level-filter"),
  logAccountFilter: document.getElementById("log-account-filter"),
  clearErrorsBtn: document.getElementById("clear-errors-btn"),
  accountTemplate: document.getElementById("account-card-template"),
  shutdownCountdown: document.getElementById("shutdown-countdown"),
  screenshotsGrid: document.getElementById("screenshots-grid"),
  screenshotsStatus: document.getElementById("screenshots-status"),
  screenshotsRefreshBtn: document.getElementById("screenshots-refresh-btn"),
  restoreRecommendBanner: document.getElementById("restore-recommend-banner"),
  restoreRecommendText: document.getElementById("restore-recommend-text"),
  restoreRecommendOpen: document.getElementById("restore-recommend-open"),
  restoreRecommendDismiss: document.getElementById("restore-recommend-dismiss"),
  addAccountOpen: document.getElementById("add-account-open"),
};

if (els.shutdownCountdown?.dataset?.shutdownMinutes) {
  shutdownAfterMinutesConfig = Number(els.shutdownCountdown.dataset.shutdownMinutes || 0);
}

function formatCountdown(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function parseWatcherStatusLine(message) {
  const text = String(message || "");
  const idleMatch = text.match(/idleMin=(\d+)/i);
  const runningMatch = text.match(/GnBots\.exe=(True|False)/i);
  const timeMatch = text.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
  let updatedAt = null;
  if (timeMatch) {
    const parsed = new Date(timeMatch[1].replace(" ", "T"));
    if (!Number.isNaN(parsed.getTime())) {
      updatedAt = parsed.toISOString();
    }
  }
  return {
    gnbotsIdleMinutes: idleMatch ? Number(idleMatch[1]) : undefined,
    gnbotsRunning: runningMatch ? runningMatch[1].toLowerCase() === "true" : undefined,
    updatedAt,
  };
}

function normalizeWatcherForShutdown(watcher, stack) {
  const parsed = parseWatcherStatusLine(watcher?.lastMessage);
  const shutdownAfterMinutes =
    watcher?.shutdownAfterMinutes ??
    stack?.idleShutdownMinutes ??
    shutdownAfterMinutesConfig;
  return {
    ...(watcher || {}),
    shutdownAfterMinutes,
    gnbotsIdleMinutes: watcher?.gnbotsIdleMinutes ?? parsed.gnbotsIdleMinutes ?? 0,
    gnbotsRunning:
      typeof watcher?.gnbotsRunning === "boolean"
        ? watcher.gnbotsRunning
        : (parsed.gnbotsRunning ?? stack?.gnbotsExe?.running ?? false),
    updatedAt: watcher?.updatedAt || parsed.updatedAt || null,
  };
}

function gnbotsRunningForShutdown(watcher, stack) {
  if (stack?.gnbotsExe?.stackActive === true) return true;
  if (stack?.gnbotsApi?.healthy) return true;
  if (stack?.gnbotsExe && typeof stack.gnbotsExe.running === "boolean" && stack.gnbotsExe.running) {
    return true;
  }
  if (watcher?.gnbotsStackActive === true) return true;
  return Boolean(watcher?.gnbotsRunning);
}

function shutdownLimitMinutes(watcher, stack) {
  // Explicit 0 means disabled. Do not fall through to DEFAULT_SHUTDOWN_MINUTES.
  for (const value of [
    watcher?.shutdownAfterMinutes,
    stack?.idleShutdownMinutes,
    shutdownAfterMinutesConfig,
  ]) {
    if (value === 0 || value === "0") return 0;
    const n = Number(value);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return DEFAULT_SHUTDOWN_MINUTES;
}

function shutdownRemainingSeconds(watcher, stack) {
  const limitMinutes = shutdownLimitMinutes(watcher, stack);
  if (limitMinutes <= 0) return null;
  if (gnbotsRunningForShutdown(watcher, stack)) return null;

  const idleMinutes = Number(watcher?.gnbotsIdleMinutes || 0);
  const updatedAt = watcher?.updatedAt ? new Date(watcher.updatedAt).getTime() : Date.now();
  const elapsedSeconds = Math.max(0, (Date.now() - updatedAt) / 1000);
  const idleSeconds = idleMinutes * 60 + elapsedSeconds;
  return Math.max(0, limitMinutes * 60 - idleSeconds);
}

function renderShutdownCountdown(watcher, stack = null) {
  if (!els.shutdownCountdown) return;

  const limitMinutes = shutdownLimitMinutes(watcher, stack);
  if (limitMinutes <= 0) {
    els.shutdownCountdown.textContent = "";
    return;
  }

  if (gnbotsRunningForShutdown(watcher, stack)) {
    els.shutdownCountdown.textContent = `If the GnBots stack fully stops, the monitor shuts down after ${limitMinutes} minutes.`;
    return;
  }

  const remaining = shutdownRemainingSeconds(watcher, stack);
  if (remaining == null) {
    els.shutdownCountdown.textContent = `The monitor shuts down after ${limitMinutes} minutes with no GnBots stack activity.`;
    return;
  }

  if (remaining <= 0) {
    els.shutdownCountdown.textContent = "Sentinel shutting down now…";
    return;
  }

  els.shutdownCountdown.textContent = `Sentinel shuts down in ${formatCountdown(remaining)} without GnBots stack activity.`;
}

function scheduleShutdownCountdown(watcher, stack = null) {
  const normalized = normalizeWatcherForShutdown(watcher, stack);
  lastWatcherSnapshot = normalized;
  lastStackSnapshot = stack;
  renderShutdownCountdown(normalized, stack);
  if (shutdownTimerId) {
    clearInterval(shutdownTimerId);
    shutdownTimerId = null;
  }
  if (shutdownRemainingSeconds(normalized, stack) == null) return;
  shutdownTimerId = window.setInterval(() => {
    renderShutdownCountdown(lastWatcherSnapshot, lastStackSnapshot);
  }, 1000);
}

function setHostStatus(message, kind = "info") {
  if (!els.hostStatus) return;
  els.hostStatus.textContent = message || "";
  els.hostStatus.className = `controls-meta ${kind}`;
}

function formatMb(value) {
  if (value == null) return "—";
  return `${Math.round(value).toLocaleString()} MB`;
}

function meterClass(percent) {
  if (percent >= 90) return "bad";
  if (percent >= 75) return "warn";
  return "";
}

function renderStack(stack) {
  if (!els.stackPills) return;
  const gnbots = stack?.gnbotsExe || {};
  const monitor = stack?.monitor || {};
  const watcher = stack?.watcher || {};

  const elevation = stack?.monitorElevation || stack?.elevatedTasks || {};
  const pills = [
    ...(stack?.headless
      ? [{ label: "Headless · low power", className: "ok" }]
      : []),
    {
      label: gnbots.running
        ? `GnBots.exe · PID ${gnbots.pid ?? "?"}`
        : "GnBots.exe · not running",
      className: gnbots.running ? "ok" : "bad",
    },
    {
      label: stack?.gnbotsApi?.healthy
        ? `API · :${stack?.gnbotsApi?.port ?? "?"}`
        : gnbots.running
          ? "API · not responding"
          : "API · offline",
      className: stack?.gnbotsApi?.healthy ? "ok" : gnbots.running ? "bad" : "warn",
    },
    {
      label: monitor.healthy ? `Sentinel · :${monitor.port}` : `Sentinel · down`,
      className: monitor.healthy ? "ok" : "bad",
    },
    {
      label: watcher.running
        ? `Watcher · PID ${watcher.pid ?? "?"}`
        : "Watcher · not running",
      className: watcher.running ? "ok" : "warn",
    },
    {
      label: elevation.requiresAdmin
        ? elevation.isAdmin
          ? "Sentinel · elevated"
          : "Sentinel · needs elevation"
        : "Sentinel · standard",
      className: elevation.ready ? "ok" : "warn",
    },
  ];

  els.stackPills.innerHTML = pills
    .map((pill) => `<span class="stack-pill ${pill.className}">${escapeHtml(pill.label)}</span>`)
    .join("");
}

function renderResources(resources) {
  if (!els.resourcesBody) return;
  const system = resources?.system || {};
  const processes = resources?.processes || [];

  const meters = [
    ["CPU", system.cpuPercent ?? 0, `${system.cpuPercent ?? 0}%`, ""],
    [
      "Memory",
      system.memoryPercent ?? 0,
      `${formatMb(system.memoryUsedMb)} / ${formatMb(system.memoryTotalMb)}`,
      "",
    ],
    [
      "Disk use",
      system.diskBusyPercent ?? 0,
      `R ${system.diskReadPercent ?? 0}% · W ${system.diskWritePercent ?? 0}%`,
      system.diskLabel || "",
    ],
  ];

  const meterHtml = meters
    .map(([label, percent, value, detail]) => {
      const cls = meterClass(Number(percent));
      const detailHtml = detail
        ? `<div class="resource-detail">${escapeHtml(detail)}</div>`
        : "";
      return `
        <div class="resource-meter">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
          ${detailHtml}
          <div class="resource-bar ${cls}"><span style="width:${Math.min(100, Number(percent) || 0)}%"></span></div>
        </div>`;
    })
    .join("");

  const processRows = processes.length
    ? processes
        .map(
          (proc) => `
          <tr>
            <td title="${escapeHtml(proc.rawName ? `${proc.rawName} (PID ${proc.pid})` : `PID ${proc.pid}`)}">${escapeHtml(proc.name || "?")}</td>
            <td>${proc.pid ?? "—"}</td>
            <td>${proc.cpuPercent ?? 0}%</td>
            <td>${formatMb(proc.memoryMb)}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="4" class="empty">No tracked processes running.</td></tr>`;

  els.resourcesBody.innerHTML = `
    <div class="resource-grid">${meterHtml}</div>
    <table class="process-table">
      <thead>
        <tr>
          <th>Process</th>
          <th>PID</th>
          <th>CPU</th>
          <th>Memory</th>
        </tr>
      </thead>
      <tbody>${processRows}</tbody>
    </table>`;
}

function updateHostButtons(stack) {
  const gnbotsRunning = Boolean(
    stack?.gnbotsExe?.running ||
      stack?.gnbotsExe?.stackActive ||
      lastPayload?.gnbotsProcessRunning
  );
  const elevationReady = stack?.capabilities?.gnbotsElevationReady ?? stack?.monitorElevation?.ready ?? true;
  document.querySelectorAll("[data-host-action]").forEach((btn) => {
    const action = btn.dataset.hostAction;
    const needsElevation = action === "start" && !elevationReady;
    btn.disabled =
      commandBusy ||
      needsElevation ||
      (action === "start" && gnbotsRunning) ||
      (action === "stop" && !gnbotsRunning);
    if (needsElevation) {
      btn.title = "GnBots requires Administrator. Restart Sentinel elevated via StartGnBotStack.bat.";
    } else if (action === "start" && gnbotsRunning) {
      btn.title = "GnBots is already running.";
    } else if (action === "stop" && !gnbotsRunning) {
      btn.title = "GnBots is not running.";
    } else {
      btn.title = "";
    }
  });
}

function formatTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleString();
}

function formatCompactTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatRuntime(runtime, account) {
  const action = account?.activeAction || runtime?.latestAction || "";
  if (!action) return "—";
  const when = runtime?.latestAt ? formatCompactTime(runtime.latestAt) : "";
  return when ? `${action} · ${when}` : action;
}

function accountState(account) {
  if (!account.active) return { label: "Disabled", className: "disabled" };
  if (account.isRunning) return { label: "Running", className: "running" };
  if (account.isBooting) return { label: "Booting", className: "booting" };
  if (account.isPaused) return { label: "Paused", className: "paused" };
  if (account.inSession) return { label: "In session", className: "session" };
  return { label: "Idle", className: "idle" };
}

function botIsActive() {
  return Boolean(lastPayload?.botActive);
}

function setCommandStatus(message, kind = "info") {
  els.commandStatus.textContent = message || "";
  els.commandStatus.className = `controls-meta ${kind}`;
}

function describeCommandResult(result) {
  if (result == null) return "Done";
  if (typeof result === "string") return result;
  if (typeof result === "object") {
    if (result.data != null && typeof result.data === "string") return result.data;
    if (result.data != null) return JSON.stringify(result.data);
    return JSON.stringify(result);
  }
  return String(result);
}

const RESTORE_RECOMMEND_DISMISS_KEY = "gnbotsRestoreRecommendDismissed";
const OCR_NOTICE_DISMISS_KEY = "gnbotsDismissedOcrNotices";

function restoreRecommendDismissedToday() {
  const stored = localStorage.getItem(RESTORE_RECOMMEND_DISMISS_KEY);
  if (!stored) return false;
  const today = new Date().toISOString().slice(0, 10);
  return stored === today;
}

function renderRestoreRecommendation(accounts, payload) {
  const banner = els.restoreRecommendBanner;
  if (!banner || !els.restoreRecommendText) return;

  const restoreApi = window.GnBotsRestore;
  const troubled = restoreApi ? restoreApi.troubledRestoreRows(accounts) : [];
  const botRunning = Boolean(payload?.botActive);

  if (!troubled.length || restoreRecommendDismissedToday()) {
    banner.classList.add("hidden");
    return;
  }

  const names = troubled
    .slice(0, 4)
    .map((row) => row.ldName)
    .join(", ");
  const more = troubled.length > 4 ? ` +${troubled.length - 4} more` : "";
  const stopNote = botRunning
    ? " Stop the bot first, then open Settings → Emulator restore."
    : " Open Settings → Emulator restore to restore backups and reinstall the APK.";
  els.restoreRecommendText.textContent = `${troubled.length} instance${troubled.length === 1 ? "" : "s"} need attention (${names}${more}).${stopNote}`;
  if (els.restoreRecommendOpen) {
    els.restoreRecommendOpen.classList.toggle("disabled", botRunning);
    els.restoreRecommendOpen.setAttribute("aria-disabled", botRunning ? "true" : "false");
  }
  banner.classList.remove("hidden");
}

function updateAddAccountShortcut(payload) {
  const link = els.addAccountOpen;
  if (!link) return;
  const botRunning = Boolean(payload?.botActive);
  const offline = payload?.gnbotsOnline === false;
  const blocked = botRunning || offline;
  link.classList.toggle("disabled", blocked);
  link.setAttribute("aria-disabled", blocked ? "true" : "false");
  if (botRunning) {
    link.title = "Stop the bot before adding a new account";
  } else if (offline) {
    link.title = "Launch GnBots first";
  } else {
    link.title = "Create LDPlayer instance and add a GnBots account";
  }
}

async function runCommand(path, options = {}) {
  if (commandBusy) {
    setCommandStatus("Another command is still running…", "warn");
    return null;
  }

  commandBusy = true;
  setCommandStatus(options.pendingMessage || "Sending command…", "pending");
  updateControlsDisabled();

  try {
    const response = await fetch(path, {
      method: options.method || "POST",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    let payload = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      payload = await response.json();
    } else {
      payload = await response.text();
    }

    if (!response.ok) {
      const detail = payload?.detail ?? payload;
      const message = typeof detail === "string" ? detail : JSON.stringify(detail);
      throw new Error(message || `HTTP ${response.status}`);
    }

    setCommandStatus(options.successMessage || describeCommandResult(payload), "ok");
    if (options.refresh !== false) {
      void burstRefresh({ delays: options.burstDelays });
    }
    return payload;
  } catch (error) {
    setCommandStatus(`${options.errorPrefix || "Command failed"}: ${error.message}`, "error");
    return null;
  } finally {
    commandBusy = false;
    updateControlsDisabled();
  }
}

function updateControlsDisabled() {
  const offline = !lastPayload?.gnbotsOnline;
  document.querySelectorAll(".btn-command, .btn-action").forEach((btn) => {
    btn.disabled = offline || commandBusy;
  });
  updateHostButtons(lastPayload?.stack);
}

function renderGlobalControls(catalog) {
  const entries = catalog?.global || [];
  if (!entries.length) return;

  if (els.globalControls.querySelector("[data-command]")) {
    for (const command of entries) {
      const button = els.globalControls.querySelector(`[data-command="${command.id}"]`);
      if (!button) continue;
      if (command.label) button.textContent = command.label;
      if (command.description) button.title = command.description;
    }
    return;
  }

  els.globalControls.innerHTML = entries
    .map((command) => {
      const tone = command.id === "start" ? "primary" : command.id.includes("stop") ? "danger" : "";
      return `
        <button
          class="btn btn-command ${tone}"
          type="button"
          data-command="${command.id}"
          title="${escapeHtml(command.description || "")}"
        >${command.label}</button>`;
    })
    .join("");
}

function accountActionTone(code) {
  const id = String(code.id || code.label || "").toLowerCase();
  if (id.includes("stop") || id.includes("pause") || id.includes("close")) return "stop";
  return "run";
}

function renderAccountActions(container, account, catalog) {
  if (!account.active) {
    container.innerHTML = `<span class="account-actions-muted">Disabled for bot runs</span>`;
    return;
  }

  const codes = catalog?.sessionRunCodes || DEFAULT_COMMAND_CATALOG.sessionRunCodes;
  const actionButtons = codes
    .map((code) => {
      const tone = accountActionTone(code);
      return `
        <button
          class="btn btn-action btn-action-${tone}"
          type="button"
          data-account-id="${account.id}"
          data-run-code="${code.id}"
          title="${escapeHtml(code.description || "")}"
        >${escapeHtml(code.label || code.id)}</button>`;
    })
    .join("");

  const screenshot = account.inSession
    ? `<button
        class="btn btn-action btn-action-shot"
        type="button"
        data-screenshot-id="${account.id}"
        title="Open a live emulator screenshot"
      >Screenshot</button>`
    : "";

  container.innerHTML = `
    <div class="account-action-groups">
      ${actionButtons ? `<div class="account-action-group">${actionButtons}</div>` : ""}
      ${screenshot ? `<div class="account-action-group account-action-group-util">${screenshot}</div>` : ""}
    </div>`;
}

function renderStats(summary, status) {
  const enabled = summary.activeProfileAccounts ?? summary.totalAccounts ?? 0;
  const total = summary.totalAccounts ?? 0;
  const logStats = summary.logStats || {};
  const errorCount = Number(logStats.errors || 0);
  const warnCount = Number(logStats.warnings || 0);
  const cards = [
    { key: "errors", label: "Errors today", value: errorCount, tone: errorCount > 0 ? "bad" : "" },
    { key: "warnings", label: "Warnings today", value: warnCount, tone: warnCount > 0 ? "warn" : "" },
    { key: "accounts", label: "Accounts", value: `${enabled}/${total} enabled`, tone: "" },
    {
      key: "sessions",
      label: "Active sessions",
      value: `${summary.activeSessions ?? 0}/${summary.maxSessions ?? "?"}`,
      tone: "",
    },
    { key: "running", label: "Running", value: summary.running ?? 0, tone: (summary.running ?? 0) > 0 ? "ok" : "" },
    { key: "booting", label: "Booting", value: summary.booting ?? 0, tone: (summary.booting ?? 0) > 0 ? "warn" : "" },
    { key: "state", label: "Bot state", value: status?.State || "—", tone: "" },
  ];

  els.stats.innerHTML = cards
    .map(
      ({ key, label, value, tone }) => `
        <div class="stat-card${tone ? ` stat-card-${tone}` : ""}" data-stat="${key}">
          <div class="stat-card-body">
            <div class="label">${label}</div>
            <div class="value">${escapeHtml(String(value))}</div>
          </div>
        </div>`,
    )
    .join("");
}

function logLineHtml(line) {
  const levelClass = line.level === "ERROR" ? "error" : line.level === "WARN" ? "warn" : "info";
  const accountLabel = line.name || line.account || "Unknown";
  const ocrClass = line.accountSwitchOcr ? " account-switch-ocr" : "";
  return `
    <div class="log-line ${levelClass}${ocrClass}">
      <div class="log-line-marker" aria-hidden="true"></div>
      <div class="log-line-content">
        <span class="time">${line.time}</span>
        <span class="level">[${line.level}]</span>
        <span class="account">${escapeHtml(accountLabel)}</span>
        <span class="message">${escapeHtml(line.message)}</span>
      </div>
    </div>`;
}

function logLineAccountLabel(line) {
  return String(line?.name || line?.account || "").trim();
}

function filterLogLines(lines, { levelFilter, query, accountFilter }) {
  const normalizedQuery = query.trim().toLowerCase();
  const normalizedAccount = accountFilter.trim().toLowerCase();
  return lines.filter((line) => {
    if (levelFilter === "problems" && line.level !== "ERROR" && line.level !== "WARN") {
      return false;
    }
    if (levelFilter === "ERROR" && line.level !== "ERROR") {
      return false;
    }
    if (levelFilter === "WARN" && line.level !== "WARN") {
      return false;
    }
    if (normalizedAccount) {
      const label = logLineAccountLabel(line).toLowerCase();
      if (label !== normalizedAccount) {
        return false;
      }
    }
    if (!normalizedQuery) {
      return true;
    }
    return (
      line.message.toLowerCase().includes(normalizedQuery) ||
      logLineAccountLabel(line).toLowerCase().includes(normalizedQuery) ||
      line.level.toLowerCase().includes(normalizedQuery) ||
      line.time.toLowerCase().includes(normalizedQuery)
    );
  });
}

function renderLogSummary({ tabMode, levelFilter, query, accountFilter, lines, logStats }) {
  if (!els.logSummary) return;

  const stats = logStats || {};
  const segments = Array.isArray(stats.logSegments) ? stats.logSegments.filter(Boolean) : [];
  const logFile = segments.length > 1
    ? ` · ${segments.join(", ")}`
    : stats.logFile
      ? ` · ${stats.logFile}`
      : "";
  const totalErrors = Number(stats.errors || 0);
  const totalWarnings = Number(stats.warnings || 0);
  const visible = lines.length;
  const clearedNote = stats.clearedAt ? " since last clear" : "";

  let headline = "";
  if (tabMode === "issues") {
    if (levelFilter === "ERROR") {
      headline = `${visible} recent error${visible === 1 ? "" : "s"} shown · ${totalErrors} today${clearedNote}${logFile}`;
    } else if (levelFilter === "WARN") {
      headline = `${visible} recent warning${visible === 1 ? "" : "s"} shown · ${totalWarnings} today${clearedNote}${logFile}`;
    } else {
      headline = `${visible} recent issue${visible === 1 ? "" : "s"} shown · ${totalErrors} errors, ${totalWarnings} warnings today${clearedNote}${logFile}`;
    }
  } else {
    headline = `${visible} recent log line${visible === 1 ? "" : "s"}${logFile}`;
  }

  if (query.trim()) {
    headline += ` · filtered by “${query.trim()}”`;
  }
  if (accountFilter.trim()) {
    headline += ` · ${accountFilter.trim()} only`;
  }

  els.logSummary.textContent = headline;
}

function syncLogAccountFilterOptions(accounts) {
  const select = els.logAccountFilter;
  if (!select) return;

  const sorted = [...(accounts || [])].sort((a, b) =>
    String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }),
  );
  const names = sorted.map((account) => String(account.name || "").trim()).filter(Boolean);
  const previous = logAccountFilter;

  select.innerHTML = [
    '<option value="">All accounts</option>',
    ...names.map(
      (name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`,
    ),
  ].join("");

  if (previous && names.some((name) => name.toLowerCase() === previous.toLowerCase())) {
    select.value = names.find((name) => name.toLowerCase() === previous.toLowerCase()) || "";
    logAccountFilter = select.value;
  } else {
    select.value = "";
    logAccountFilter = "";
    if (previous) {
      localStorage.removeItem("gnbotsLogAccountFilter");
    }
  }
}

function accountSwitchOcrNoticeKey(event) {
  return [
    String(event?.accountId || ""),
    String(event?.time || ""),
    String(event?.appliedName || event?.recommendedName || ""),
    event?.applied ? "1" : "0",
  ].join("|");
}

function readDismissedOcrNotices() {
  try {
    const raw = localStorage.getItem(OCR_NOTICE_DISMISS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function isAccountSwitchOcrNoticeDismissed(event) {
  return readDismissedOcrNotices().includes(accountSwitchOcrNoticeKey(event));
}

function dismissAccountSwitchOcrNotice(event) {
  const key = accountSwitchOcrNoticeKey(event);
  const dismissed = readDismissedOcrNotices();
  if (!dismissed.includes(key)) {
    dismissed.unshift(key);
    localStorage.setItem(OCR_NOTICE_DISMISS_KEY, JSON.stringify(dismissed.slice(0, 50)));
  }
}

function renderAccountSwitchOcrNotice(payload) {
  if (!els.logOcrNotice) return;
  const recent = payload.accountSwitchOcr?.recent || [];
  const latest = recent.find((event) => {
    if (isAccountSwitchOcrNoticeDismissed(event)) return false;
    const rec = String(event?.recommendedName || "").trim();
    const cfg = String(event?.configuredName || "").trim();
    if (rec && cfg && rec.toLowerCase() === cfg.toLowerCase() && !event?.applied) {
      return false;
    }
    return true;
  });
  if (!latest) {
    els.logOcrNotice.hidden = true;
    els.logOcrNotice.innerHTML = "";
    return;
  }

  const noticeKey = accountSwitchOcrNoticeKey(latest);
  const accountName = escapeHtml(latest.accountName || latest.accountId || "Account");
  const configured = escapeHtml(latest.configuredName || "—");
  const recommended = escapeHtml(latest.recommendedName || "—");
  const foundPreview = (latest.foundTexts || [])
    .slice(0, 4)
    .map((item) => escapeHtml(item))
    .join(", ");
  const recentNames = (latest.recentNames || [])
    .slice(0, 4)
    .map((item) => escapeHtml(item))
    .join(", ");

  let statusText = "";
  if (latest.applied) {
    statusText = `Auto-updated switch name to <strong>${escapeHtml(latest.appliedName || recommended)}</strong>.`;
  } else if (latest.crossMatchBlocked) {
    const owner = escapeHtml(latest.blockedOwnerAccountName || "another account");
    const rejected = (latest.rejectedCandidates || [])
      .slice(0, 3)
      .map((item) => escapeHtml(item.text || item))
      .join(", ");
    statusText = `OCR saw names belonging to <strong>${owner}</strong> on the same emulator. Keeping <strong>${configured}</strong> for this account.`;
    if (rejected) {
      statusText += ` Ignored: ${rejected}.`;
    }
  } else if (latest.recommendedName) {
    const matched = latest.matchedReference
      ? ` Matched recent name <strong>${escapeHtml(latest.matchedReference)}</strong>.`
      : "";
    statusText = `Recommended switch name: <strong>${recommended}</strong> (was ${configured}).${matched}`;
  } else {
    statusText = `OCR could not match switch name <strong>${configured}</strong>.`;
  }

  const noticeTitle = latest.applied
    ? `Account Switch OCR auto-fix · ${accountName}`
    : `Account Switch OCR mismatch · ${accountName}`;

  els.logOcrNotice.hidden = false;
  els.logOcrNotice.innerHTML = `
    <div class="log-ocr-notice-inner">
      <div class="log-ocr-notice-head">
        <div class="log-ocr-notice-title">${noticeTitle}</div>
        <button
          class="btn btn-small btn-ghost log-ocr-notice-dismiss"
          type="button"
          data-ocr-notice-key="${escapeHtml(noticeKey)}"
          aria-label="Dismiss OCR notice"
        >Dismiss</button>
      </div>
      <div class="log-ocr-notice-body">${statusText}</div>
      ${recentNames ? `<div class="log-ocr-notice-found">Recent names: ${recentNames}</div>` : ""}
      ${foundPreview ? `<div class="log-ocr-notice-found">OCR saw: ${foundPreview}</div>` : ""}
    </div>`;
}

function renderLogs(payload) {
  syncLogAccountFilterOptions(payload.accounts || []);
  const tabMode = logTabMode;
  const levelFilter = logLevelFilter;
  const query = els.logSearch?.value || "";
  const accountFilter = logAccountFilter;
  const source = tabMode === "issues" ? payload.errorLog || [] : payload.logs || [];
  const filtered = filterLogLines(source, {
    levelFilter: tabMode === "issues" ? levelFilter : null,
    query,
    accountFilter,
  });
  const lines = filtered.slice().reverse();

  renderLogSummary({
    tabMode,
    levelFilter,
    query,
    accountFilter,
    lines,
    logStats: payload.summary?.logStats,
  });

  if (!lines.length) {
    const accountNote = accountFilter.trim() ? ` for ${accountFilter.trim()}` : "";
    const emptyMessage =
      tabMode === "issues"
        ? query.trim() || accountFilter.trim()
          ? `No matching issues${accountNote} in the recent error log.`
          : "No errors or warnings in the recent log tail."
        : query.trim() || accountFilter.trim()
          ? `No matching log lines${accountNote}.`
          : "No recent log lines.";
    els.logList.innerHTML = `<div class="empty">${emptyMessage}</div>`;
    return;
  }

  els.logList.innerHTML = lines.map((line) => logLineHtml(line)).join("");
}

function syncLogPanelControls() {
  document.querySelectorAll("[data-log-tab]").forEach((button) => {
    const active = button.dataset.logTab === logTabMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  if (els.logLevelFilter) {
    els.logLevelFilter.disabled = logTabMode !== "issues";
    els.logLevelFilter.value = logLevelFilter;
  }
  if (els.logAccountFilter) {
    els.logAccountFilter.value = logAccountFilter;
  }
}

function accountSortRank(account) {
  if (!account.active) return 9;
  if (account.isRunning) return 0;
  if (account.isBooting) return 1;
  if (account.isPaused) return 2;
  if (account.inSession) return 3;
  return 4;
}

function accountIssueScore(account) {
  const stats = account.logStats || {};
  return (stats.errorsToday || 0) * 10 + (stats.warningsToday || 0);
}

function sortAccounts(accounts, mode) {
  const rows = accounts.slice();
  switch (mode) {
    case "running-first":
      rows.sort((a, b) => {
        const rankDiff = accountSortRank(a) - accountSortRank(b);
        if (rankDiff !== 0) return rankDiff;
        return (a.instanceId ?? 999) - (b.instanceId ?? 999) || a.name.localeCompare(b.name);
      });
      break;
    case "not-running-first":
      rows.sort((a, b) => {
        const rankDiff = accountSortRank(b) - accountSortRank(a);
        if (rankDiff !== 0) return rankDiff;
        return (a.instanceId ?? 999) - (b.instanceId ?? 999) || a.name.localeCompare(b.name);
      });
      break;
    case "issues-first":
      rows.sort((a, b) => {
        const issueDiff = accountIssueScore(b) - accountIssueScore(a);
        if (issueDiff !== 0) return issueDiff;
        return (a.instanceId ?? 999) - (b.instanceId ?? 999) || a.name.localeCompare(b.name);
      });
      break;
    case "name":
      rows.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
      break;
    case "instance":
      rows.sort(
        (a, b) =>
          (a.instanceId ?? 999) - (b.instanceId ?? 999) ||
          a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
      );
      break;
    default:
      break;
  }
  return rows;
}

function formatUptimePercent(value) {
  if (value == null || value === "" || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Math.round(Number(value))}%`;
}

function uptimeTone(percent) {
  if (percent == null || Number.isNaN(Number(percent))) return "";
  if (Number(percent) >= 90) return "stat-ok";
  if (Number(percent) >= 75) return "stat-warn";
  return "stat-error";
}

function switchNameTone(account) {
  const configured = String(account.switchAccountName || "").trim();
  if (!configured) return "";
  const hint = account.switchOcrHint;
  if (!hint || hint.crossMatchBlocked) return "";
  const recommended = String(hint.recommendedName || "").trim();
  if (!recommended) return "";
  if (recommended.toLowerCase() === configured.toLowerCase()) return "";
  return "stat-warn";
}

function formatSwitchName(account) {
  const configured = String(account.switchAccountName || "").trim();
  if (!configured) return "—";
  const hint = account.switchOcrHint;
  if (!hint || hint.crossMatchBlocked) return configured;
  const recommended = String(hint.recommendedName || "").trim();
  if (!recommended || recommended.toLowerCase() === configured.toLowerCase()) {
    return configured;
  }
  return `${configured} → ${recommended}?`;
}

function setAccountStatCell(node, className, value, tone) {
  const cell = node.querySelector(className);
  if (!cell) return;
  cell.textContent = String(value);
  cell.classList.remove("stat-ok", "stat-warn", "stat-error");
  if (tone) {
    cell.classList.add(tone);
  }
}

function renderAccounts(accounts) {
  const query = els.accountSearch.value.trim().toLowerCase();
  const sorted = sortAccounts(accounts, accountSortMode);
  const filtered = sorted.filter((account) => {
    if (!query) return true;
    return (
      account.name.toLowerCase().includes(query) ||
      String(account.instanceId).includes(query) ||
      (account.activeAction || "").toLowerCase().includes(query)
    );
  });

  if (!filtered.length) {
    els.accountsGrid.innerHTML = '<div class="empty">No accounts match your filter.</div>';
    return;
  }

  els.accountsGrid.innerHTML = "";
  for (const account of filtered) {
    const node = els.accountTemplate.content.cloneNode(true);
    const card = node.querySelector(".account-card");
    const state = accountState(account);
    const stateClasses = ["disabled", "running", "booting", "paused", "session", "idle"];
    for (const cls of stateClasses) {
      card.classList.remove(`account-state-${cls}`);
    }
    card.classList.add(`account-state-${state.className}`);

    node.querySelector(".account-name").textContent = account.name;
    const badge = node.querySelector(".state-badge");
    badge.textContent = state.label;
    badge.className = `badge state-badge ${state.className}`;

    const toggle = node.querySelector("[data-account-active-toggle]");
    if (toggle) {
      toggle.checked = Boolean(account.active);
      toggle.dataset.accountId = account.id;
      toggle.disabled = botIsActive() || accountToggleBusy;
      toggle.title = botIsActive()
        ? "Stop the bot to change which accounts are enabled"
        : "Include this account when the bot starts";
    }
    const toggleLabel = node.querySelector(".account-toggle-label");
    if (toggleLabel) {
      toggleLabel.textContent = account.active ? "On" : "Off";
    }

    if (!account.active) {
      card.classList.add("account-card-disabled");
    } else {
      card.classList.remove("account-card-disabled");
    }

    node.querySelector(".instance").textContent = account.instanceId ?? "—";
    node.querySelector(".action").textContent = account.activeAction || "—";
    const stats = account.logStats || {};
    setAccountStatCell(
      node,
      ".uptime-today",
      formatUptimePercent(stats.uptimePercent),
      uptimeTone(stats.uptimePercent),
    );
    setAccountStatCell(
      node,
      ".switch-name",
      formatSwitchName(account),
      switchNameTone(account),
    );
    node.querySelector(".runtime").textContent = formatRuntime(account.runtime, account);
    const runsToday = stats.runsToday || 0;
    const errorsToday = stats.errorsToday || 0;
    const warningsToday = stats.warningsToday || 0;
    setAccountStatCell(node, ".runs-today", runsToday, "");
    setAccountStatCell(
      node,
      ".errors-today",
      errorsToday,
      errorsToday > 0 ? "stat-error" : "stat-ok"
    );
    setAccountStatCell(
      node,
      ".warnings-today",
      warningsToday,
      warningsToday > 0 ? "stat-warn" : "stat-ok"
    );
    card.classList.toggle("has-errors", errorsToday > 0);
    card.classList.toggle("has-warnings", errorsToday === 0 && warningsToday > 0);
    const restore = account.emulatorRestore || {};
    card.classList.toggle("has-restore-offer", Boolean(restore.troubled));
    const troubleNote = node.querySelector(".account-trouble-note");
    if (troubleNote) {
      const reasons = restore.troubleReasons || [];
      if (restore.troubled && reasons.length) {
        troubleNote.textContent = `Emulator trouble: ${reasons.join("; ")}. See Settings → Emulator restore.`;
        troubleNote.classList.remove("hidden");
      } else {
        troubleNote.textContent = "";
        troubleNote.classList.add("hidden");
      }
    }
    const sharedNote = node.querySelector(".account-shared-instance");
    if (sharedNote) {
      const peers = account.sharedInstanceWith || [];
      if (peers.length) {
        sharedNote.textContent = `Shares LD instance ${account.instanceId} with ${peers.join(", ")}. Only one can run per instance at a time.`;
        sharedNote.classList.remove("hidden");
      } else {
        sharedNote.textContent = "";
        sharedNote.classList.add("hidden");
      }
    }
    renderAccountActions(node.querySelector(".account-actions"), account, activeCatalog());

    if (account.inSession) {
      card.style.borderColor = "rgba(59, 130, 246, 0.35)";
    }

    els.accountsGrid.appendChild(node);
  }

  updateControlsDisabled();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

let screenshotCacheBust = Date.now();
let screenshotsBusy = false;
let lastScreenshotAt = 0;
let lastScreenshotCount = 0;
let lastScreenshotTone = "";
const SCREENSHOT_IMG_RETRIES = 4;
const SCREENSHOT_IMG_RETRY_MS = [0, 1500, 3000, 5000];

function bindScreenshotImage(img) {
  const baseUrl = img.dataset.src;
  if (!baseUrl) return;

  let attempt = 0;

  const load = () => {
    img.classList.add("screenshot-image-pending");
    img.classList.remove("screenshot-image-error");
    img.src = attempt === 0 ? baseUrl : `${baseUrl.split("?")[0]}?t=${Date.now()}&r=${attempt}`;
  };

  img.addEventListener("load", () => {
    img.classList.remove("screenshot-image-pending", "screenshot-image-error");
  });

  img.addEventListener("error", () => {
    attempt += 1;
    if (attempt < SCREENSHOT_IMG_RETRIES) {
      setTimeout(load, SCREENSHOT_IMG_RETRY_MS[attempt] || 5000);
      return;
    }
    img.classList.remove("screenshot-image-pending");
    img.classList.add("screenshot-image-error");
  });

  load();
}

function hydrateScreenshotImages() {
  if (!els.screenshotsGrid) return;
  els.screenshotsGrid.querySelectorAll("img.screenshot-image[data-src]").forEach(bindScreenshotImage);
}

function screenshotStateLabel(item) {
  if (item.isBooting) return "Booting";
  if (item.isPaused) return "Paused";
  if (item.isRunning) return "Running";
  return "Active";
}

function setScreenshotsStatus(message, tone = "") {
  if (!els.screenshotsStatus) return;
  els.screenshotsStatus.textContent = message;
  els.screenshotsStatus.className = `controls-meta ${tone}`.trim();
}

function renderScreenshots(items) {
  if (!els.screenshotsGrid) return;
  if (!items.length) {
    els.screenshotsGrid.innerHTML =
      `<p class="screenshots-empty">No active emulator sessions to capture.</p>`;
    return;
  }

  els.screenshotsGrid.innerHTML = items
    .map((item) => {
      const src = `${item.screenshotUrl}?t=${screenshotCacheBust}`;
      const action = item.activeAction ? escapeHtml(item.activeAction) : "—";
      const state = screenshotStateLabel(item);
      const stateClass = state.toLowerCase();
      const name = escapeHtml(item.name || item.accountId);
      const isLive = Boolean(item.isRunning || item.isBooting);
      return `
        <article class="screenshot-card${isLive ? " screenshot-card-live" : ""}">
          <div class="screenshot-card-head">
            <div class="screenshot-card-title">
              ${isLive ? '<span class="live-dot" aria-hidden="true"></span>' : ""}
              <h3>${name}</h3>
            </div>
            <span class="badge state-badge ${stateClass}">${state}</span>
          </div>
          <a class="screenshot-image-link" href="${src}" target="_blank" rel="noopener noreferrer" title="Open full screenshot for ${name}">
            <img
              class="screenshot-image screenshot-image-pending"
              data-src="${src}"
              alt=""
              loading="eager"
              decoding="async"
            >
          </a>
          <dl class="screenshot-meta">
            <div><dt>Instance</dt><dd>${item.instanceId ?? "—"}</dd></div>
            <div><dt>Task</dt><dd>${action}</dd></div>
          </dl>
        </article>`;
    })
    .join("");

  hydrateScreenshotImages();
}

function screenshotRefreshLabel() {
  if (!screenshotIntervalMs) return "manual refresh only";
  const seconds = Math.max(15, Math.round(screenshotIntervalMs / 1000));
  if (window.matchMedia("(max-width: 640px)").matches) {
    return `every ${seconds}s`;
  }
  return `refreshes every ${seconds}s`;
}

function formatScreenshotStatus(count) {
  const compact = window.matchMedia("(max-width: 640px)").matches;
  const base = count ? `${count} active` : compact ? "No active" : "No active emulators";
  if (!lastScreenshotAt) {
    return `${base} · ${screenshotRefreshLabel()}`;
  }
  const ageSeconds = Math.max(0, Math.round((Date.now() - lastScreenshotAt) / 1000));
  if (compact) {
    return `${base} · ${ageSeconds}s ago · ${screenshotRefreshLabel()}`;
  }
  return `${base} · updated ${ageSeconds}s ago · ${screenshotRefreshLabel()}`;
}

async function loadScreenshots({ bust = true } = {}) {
  if (!els.screenshotsGrid) return;
  if (bust) screenshotCacheBust = Date.now();
  if (screenshotsBusy) return;

  screenshotsBusy = true;
  if (els.screenshotsRefreshBtn) els.screenshotsRefreshBtn.disabled = true;
  setScreenshotsStatus("Loading…", "pending");

  try {
    const response = await fetch("/api/screenshots", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    renderScreenshots(payload.screenshots || []);
    lastScreenshotAt = Date.now();
    lastScreenshotCount = payload.count || 0;
    lastScreenshotTone = payload.count ? "ok" : "warn";
    setScreenshotsStatus(
      formatScreenshotStatus(lastScreenshotCount),
      lastScreenshotTone
    );
  } catch (error) {
    const message =
      error?.message === "Failed to fetch" || error?.name === "TypeError"
        ? "Dashboard unreachable — is the monitor running on this PC?"
        : error.message;
    els.screenshotsGrid.innerHTML = `<p class="screenshots-empty">Screenshot error: ${escapeHtml(message)}</p>`;
    setScreenshotsStatus(message, "error");
  } finally {
    screenshotsBusy = false;
    if (els.screenshotsRefreshBtn) els.screenshotsRefreshBtn.disabled = false;
  }
}

function renderError(message, payload) {
  const existing = document.querySelector(".error-banner");
  if (existing) existing.remove();
  if (!message) return;

  const layout = document.querySelector(".layout");
  if (!layout) return;

  const processUp = payload?.gnbotsProcessRunning;
  const banner = document.createElement("div");
  banner.className = "error-banner";
  if (processUp) {
    banner.innerHTML = `
      <div class="alert-stripe" aria-hidden="true"></div>
      <div class="error-banner-copy">
        <p><strong>GnBots is running but the API is not responding.</strong> ${escapeHtml(message)}</p>
        <p class="error-banner-actions">
          <button class="btn btn-small btn-primary-soft" type="button" id="api-reconnect-btn">Recover API</button>
          <button class="btn btn-small btn-ghost" type="button" id="api-restart-btn">Restart GnBots</button>
        </p>
      </div>`;
  } else {
    banner.innerHTML = `
      <div class="alert-stripe" aria-hidden="true"></div>
      <div class="error-banner-copy">
        <p>GnBots API unreachable: ${escapeHtml(message)}. Showing profile/log data from disk.</p>
      </div>`;
  }

  const anchor = layout.querySelector(".compact-panels") || layout.querySelector("header");
  if (anchor) {
    layout.insertBefore(banner, anchor);
  } else {
    layout.prepend(banner);
  }

  const reconnectBtn = banner.querySelector("#api-reconnect-btn");
  if (reconnectBtn) {
    reconnectBtn.addEventListener("click", async () => {
      reconnectBtn.disabled = true;
      setCommandStatus("Recovering GnBots API (may restart GnBots)...", "warn");
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 120000);
      try {
        const response = await fetch("/api/gnbots/reconnect", {
          method: "POST",
          signal: controller.signal,
        });
        const body = await response.json().catch(() => ({}));
        if (!body.ok) throw new Error(body.message || body.detail || `HTTP ${response.status}`);
        setCommandStatus(body.message || "API recovered.", body.restarted ? "warn" : "ok");
        await burstRefresh({ delays: [0, 2000, 6000] });
      } catch (error) {
        const message =
          error.name === "AbortError"
            ? "Recovery timed out after 2 minutes. Check watcher.log and try Restart GnBots."
            : error.message;
        setCommandStatus(`Recovery failed: ${message}`, "error");
      } finally {
        window.clearTimeout(timeoutId);
        reconnectBtn.disabled = false;
      }
    });
  }

  const restartBtn = banner.querySelector("#api-restart-btn");
  if (restartBtn) {
    restartBtn.addEventListener("click", async () => {
      if (!window.confirm("Restart GnBots? This stops the current run and relaunches the app.")) return;
      restartBtn.disabled = true;
      try {
        const response = await fetch("/api/host/gnbots/restart", { method: "POST" });
        const body = await response.json().catch(() => ({}));
        if (!body.ok) throw new Error(body.message || body.detail || `HTTP ${response.status}`);
        setCommandStatus(body.message || "GnBots restart requested.", "ok");
        await burstRefresh({ delays: [0, 2000, 6000, 15000] });
      } catch (error) {
        setCommandStatus(`Restart failed: ${error.message}`, "error");
      } finally {
        restartBtn.disabled = false;
      }
    });
  }
}

function render(payload) {
  lastPayload = payload;
  if (window.GnBotsNotifications) {
    window.GnBotsNotifications.onDashboardUpdate(payload);
  }
  els.profileLabel.textContent = `Profile: ${payload.profile}`;

  const apiOnline = Boolean(payload.gnbotsOnline);
  const processUp = Boolean(payload.gnbotsProcessRunning);
  if (apiOnline) {
    els.gnbotsStatus.textContent = "GnBots online";
    els.gnbotsStatus.className = "status-pill online";
  } else if (processUp) {
    els.gnbotsStatus.textContent = "GnBots API down";
    els.gnbotsStatus.className = "status-pill warn";
  } else {
    els.gnbotsStatus.textContent = "GnBots offline";
    els.gnbotsStatus.className = "status-pill offline";
  }
  els.lastUpdated.textContent = `Updated ${formatTime(payload.updatedAt)}`;

  renderError(apiOnline ? null : payload.gnbotsError, payload);
  renderStack(payload.stack || {});
  renderResources(payload.resources || {});
  renderStats(payload.summary || {}, payload.status || {});
  renderAccounts(payload.accounts || []);
  renderRestoreRecommendation(payload.accounts || [], payload);
  updateAddAccountShortcut(payload);
  renderAccountSwitchOcrNotice(payload);
  renderLogs(payload);
  syncLogPanelControls();
  updateControlsDisabled();
  scheduleShutdownCountdown(payload.stack?.watcher || null, payload.stack || null);
  scheduleRefresh();

  const elevation = payload.stack?.monitorElevation || payload.stack?.elevatedTasks || {};
  if (elevation.message) {
    setHostStatus(elevation.message, elevation.ready ? "ok" : "warn");
  } else if (payload.stack?.watcher?.lastMessage) {
    setHostStatus(payload.stack.watcher.lastMessage, payload.stack.watcher.running ? "ok" : "warn");
  }
}

async function resolveAppVersion(config) {
  if (config?.appVersion) return String(config.appVersion);
  try {
    const response = await fetch(`/static/VERSION?v=${Date.now()}`, { cache: "no-store" });
    if (response.ok) {
      const text = (await response.text()).trim().split(/\r?\n/)[0].trim();
      if (text) return text;
    }
  } catch (_) {
    /* ignore */
  }
  try {
    const response = await fetch("/api/update/status");
    if (response.ok) {
      const body = await response.json();
      if (body.localVersion && body.localVersion !== "0.0.0") return String(body.localVersion);
    }
  } catch (_) {
    /* ignore */
  }
  return "";
}

async function loadConfig() {
  const response = await fetch("/api/config");
  if (!response.ok) return;
  const config = await response.json();
  refreshIntervalMs = (config.refreshIntervalSeconds || 10) * 1000;
  refreshIntervalActiveMs = (config.refreshIntervalActiveSeconds || 5) * 1000;
  refreshIntervalHiddenMs = (config.refreshIntervalHiddenSeconds || 120) * 1000;
  let screenshotSeconds = config.screenshotIntervalSeconds;
  // Older monitor builds forced 0 in headless; config.json still uses screenshot_interval_seconds.
  if (!screenshotSeconds && config.headlessMode) {
    screenshotSeconds = 120;
  }
  screenshotIntervalMs =
    screenshotSeconds === 0
      ? 0
      : Math.max(15000, (screenshotSeconds || 60) * 1000);
  shutdownAfterMinutesConfig = Number(config.watcherShutdownAfterMinutes || 0);
  const versionEl = document.getElementById("app-version");
  if (versionEl) {
    const appVersion = await resolveAppVersion(config);
    if (appVersion) {
      versionEl.textContent = `v${appVersion.replace(/^v/i, "")}`;
      versionEl.hidden = false;
    }
  }
}

function currentRefreshIntervalMs() {
  if (document.hidden) return refreshIntervalHiddenMs;
  if (lastPayload?.botActive) return refreshIntervalActiveMs;
  return refreshIntervalMs;
}

async function loadCommandCatalog() {
  renderGlobalControls(DEFAULT_COMMAND_CATALOG);
  try {
    const response = await fetch("/api/commands");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    commandCatalog = await response.json();
    renderGlobalControls(commandCatalog);
  } catch (error) {
    commandCatalog = null;
    setCommandStatus(`Using built-in controls (${error.message})`, "warn");
  }
}

let refreshInFlight = false;

async function refresh() {
  if (refreshInFlight) {
    return;
  }
  refreshInFlight = true;
  els.refreshBtn.disabled = true;
  try {
    const response = await fetch("/api/dashboard", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    els.profileLabel.textContent = "Profile unavailable";
    renderError(error.message);
  } finally {
    refreshInFlight = false;
    els.refreshBtn.disabled = false;
  }
}

function currentScreenshotIntervalMs() {
  if (document.hidden) return screenshotIntervalMs * 2;
  return screenshotIntervalMs;
}

function scheduleScreenshotRefresh() {
  if (screenshotTimer) clearInterval(screenshotTimer);
  if (!screenshotIntervalMs) return;
  screenshotTimer = setInterval(() => {
    loadScreenshots({ bust: true });
  }, currentScreenshotIntervalMs());
}

async function burstRefresh(options = {}) {
  const delays = options.delays || [0, 2000, 6000];
  for (const delay of delays) {
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    await refresh();
  }
}

function scheduleRefresh() {
  const intervalMs = currentRefreshIntervalMs();
  if (refreshTimer && lastScheduledRefreshMs === intervalMs) {
    return;
  }
  if (refreshTimer) clearInterval(refreshTimer);
  lastScheduledRefreshMs = intervalMs;
  refreshTimer = setInterval(() => {
    refresh();
  }, intervalMs);
}

document.addEventListener("visibilitychange", () => {
  scheduleRefresh();
  scheduleScreenshotRefresh();
});

let screenshotStatusLayout = window.matchMedia("(max-width: 640px)");
screenshotStatusLayout.addEventListener("change", () => {
  if (!els.screenshotsStatus || !lastScreenshotAt) return;
  setScreenshotsStatus(formatScreenshotStatus(lastScreenshotCount), lastScreenshotTone);
});

function findCommandMeta(commandId) {
  return activeCatalog().global.find((entry) => entry.id === commandId);
}

els.refreshBtn.addEventListener("click", refresh);
if (els.screenshotsRefreshBtn) {
  els.screenshotsRefreshBtn.addEventListener("click", () => loadScreenshots({ bust: true }));
}
els.accountSearch.addEventListener("input", () => {
  if (lastPayload) renderAccounts(lastPayload.accounts || []);
});

if (els.accountSort) {
  els.accountSort.value = accountSortMode;
  els.accountSort.addEventListener("change", () => {
    accountSortMode = els.accountSort.value;
    localStorage.setItem("gnbotsAccountSort", accountSortMode);
    if (lastPayload) renderAccounts(lastPayload.accounts || []);
  });
}

document.querySelectorAll("[data-log-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    const nextTab = button.dataset.logTab;
    if (!nextTab || nextTab === logTabMode) return;
    logTabMode = nextTab;
    localStorage.setItem("gnbotsLogTab", logTabMode);
    syncLogPanelControls();
    if (lastPayload) renderLogs(lastPayload);
  });
});

if (els.logAccountFilter) {
  els.logAccountFilter.value = logAccountFilter;
  els.logAccountFilter.addEventListener("change", () => {
    logAccountFilter = els.logAccountFilter.value;
    if (logAccountFilter) {
      localStorage.setItem("gnbotsLogAccountFilter", logAccountFilter);
    } else {
      localStorage.removeItem("gnbotsLogAccountFilter");
    }
    if (lastPayload) renderLogs(lastPayload);
  });
}

if (els.logLevelFilter) {
  els.logLevelFilter.value = logLevelFilter;
  els.logLevelFilter.addEventListener("change", () => {
    logLevelFilter = els.logLevelFilter.value;
    localStorage.setItem("gnbotsLogLevelFilter", logLevelFilter);
    if (lastPayload) renderLogs(lastPayload);
  });
}

if (els.logSearch) {
  els.logSearch.addEventListener("input", () => {
    if (lastPayload) renderLogs(lastPayload);
  });
}

if (els.clearErrorsBtn) {
  els.clearErrorsBtn.addEventListener("click", async () => {
    if (
      !window.confirm(
        "Clear today's error and warning counters?\n\nOlder issues will be hidden from the Issues log until a new log file starts tomorrow."
      )
    ) {
      return;
    }

    els.clearErrorsBtn.disabled = true;
    try {
      const response = await fetch("/api/logs/errors/clear", { method: "POST" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.detail || body.message || `HTTP ${response.status}`);
      }
      if (lastPayload?.summary && body.logStats) {
        lastPayload.summary.logStats = body.logStats;
        lastPayload.errorLog = [];
        renderStats(lastPayload.summary, lastPayload.status || {});
        renderLogs(lastPayload);
      }
      await refresh();
    } catch (error) {
      setCommandStatus(`Could not clear errors: ${error.message}`, "error");
    } finally {
      els.clearErrorsBtn.disabled = false;
    }
  });
}

syncLogPanelControls();

function startCommandConfirm(meta) {
  if (meta?.id !== "start" || !lastPayload?.summary) {
    return meta?.confirm || "Send this command?";
  }
  const total = lastPayload.summary.activeProfileAccounts ?? lastPayload.summary.totalAccounts ?? "?";
  const maxSessions = lastPayload.summary.maxSessions ?? "?";
  return (
    `Start the bot for all ${total} enabled accounts?\n\n` +
    `Up to ${maxSessions} emulators run at once; the rest wait in queue.\n\n` +
    `Use the On/Off toggle on each account card to exclude accounts from the run queue.`
  );
}

els.globalControls.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-command]");
  if (!button) return;

  const commandId = button.dataset.command;
  const meta = findCommandMeta(commandId);
  if (!window.confirm(startCommandConfirm(meta))) return;

  await runCommand(`/api/commands/${commandId}`, {
    successMessage: `${meta?.label || commandId} command sent.`,
    burstDelays:
      commandId === "start"
        ? [0, 500, 1500, 3000, 5000, 8000, 12000, 20000, 30000]
        : commandId === "stopemulators"
          ? [0, 1500, 4000, 8000]
          : commandId === "stop" || commandId === "stopall"
            ? [0, 1000, 3000]
            : undefined,
  });
});

function applyHostActionOptimistic(action, payload) {
  if (!lastPayload) {
    lastPayload = {};
  }
  if (!lastPayload.stack) {
    lastPayload.stack = {};
  }
  if (!lastPayload.stack.gnbotsExe) {
    lastPayload.stack.gnbotsExe = {};
  }
  const details = payload?.details || {};
  const running = action === "start";
  const pid = details.pid || (running ? lastPayload.stack.gnbotsExe.pid : null);
  lastPayload.gnbotsProcessRunning = running;
  lastPayload.stack.gnbotsExe.running = running;
  lastPayload.stack.gnbotsExe.stackActive = running;
  lastPayload.stack.gnbotsExe.pid = running ? pid : null;
  updateHostButtons(lastPayload.stack);
  renderStack(lastPayload.stack);
}

document.querySelectorAll("[data-host-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    const action = button.dataset.hostAction;
    const label = action === "start" ? "Launch GnBots" : "Close GnBots";
    const confirmText =
      action === "start"
        ? "Launch GnBots.exe on the bot PC?"
        : "Close GnBots.exe? This stops the application entirely.";
    if (!window.confirm(confirmText)) return;

    if (commandBusy) return;
    commandBusy = true;
    setHostStatus(`Sending ${label.toLowerCase()} request…`, "pending");
    updateControlsDisabled();

    try {
      const response = await fetch(`/api/host/gnbots/${action}`, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || `HTTP ${response.status}`);
      }
      setHostStatus(payload.message || `${label} request sent.`, "ok");
      applyHostActionOptimistic(action, payload);
      commandBusy = false;
      updateControlsDisabled();
      // Background sync only — do not hold the UI lock across multi-second refreshes.
      void burstRefresh({ delays: [0, 1500, 4000] });
      return;
    } catch (error) {
      setHostStatus(`${label} failed: ${error.message}`, "error");
    } finally {
      commandBusy = false;
      updateControlsDisabled();
    }
  });
});

els.accountsGrid.addEventListener("change", async (event) => {
  const toggle = event.target.closest("[data-account-active-toggle]");
  if (!toggle) return;

  const accountId = toggle.dataset.accountId;
  const active = toggle.checked;
  const account = (lastPayload?.accounts || []).find((row) => row.id === accountId);
  const name = account?.name || accountId;

  if (botIsActive()) {
    toggle.checked = !active;
    setCommandStatus("Stop the bot before changing which accounts are enabled.", "warn");
    return;
  }

  if (!active && account?.inSession) {
    toggle.checked = true;
    setCommandStatus(`${name} is in an active session. Stop the bot first.`, "warn");
    return;
  }

  const actionLabel = active ? "enable" : "disable";
  if (
    !window.confirm(
      `${active ? "Enable" : "Disable"} ${name} for bot runs?\n\nRestart GnBots before starting the bot so this takes effect.`
    )
  ) {
    toggle.checked = !active;
    return;
  }

  accountToggleBusy = true;
  if (lastPayload) renderAccounts(lastPayload.accounts || []);

  try {
    const response = await fetch(`/api/profile/accounts/${accountId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.message || `HTTP ${response.status}`);
    }

    if (lastPayload?.accounts) {
      const row = lastPayload.accounts.find((entry) => entry.id === accountId);
      if (row) row.active = active;
      if (lastPayload.summary) {
        lastPayload.summary.activeProfileAccounts = lastPayload.accounts.filter((entry) => entry.active).length;
      }
      renderStats(lastPayload.summary || {}, lastPayload.status || {});
      renderAccounts(lastPayload.accounts);
    }

    setCommandStatus(payload.message || `${name} ${actionLabel}d. Restart GnBots to apply.`, "ok");
  } catch (error) {
    toggle.checked = !active;
    setCommandStatus(`Could not ${actionLabel} ${name}: ${error.message}`, "error");
    if (lastPayload) renderAccounts(lastPayload.accounts || []);
  } finally {
    accountToggleBusy = false;
    if (lastPayload) renderAccounts(lastPayload.accounts || []);
  }
});

els.accountsGrid.addEventListener("click", async (event) => {
  const screenshotButton = event.target.closest("[data-screenshot-id]");
  if (screenshotButton) {
    const accountId = screenshotButton.dataset.screenshotId;
    window.open(`/api/sessions/${accountId}/screenshot`, "_blank", "noopener,noreferrer");
    return;
  }

  const actionButton = event.target.closest("[data-run-code]");
  if (!actionButton) return;

  const accountId = actionButton.dataset.accountId;
  const runCode = actionButton.dataset.runCode;
  const label = actionButton.textContent.trim();
  if (!window.confirm(`${label} session for this account?`)) return;

  await runCommand(`/api/sessions/${accountId}/run/${runCode}`, {
    successMessage: `${label} command sent.`,
  });
});

els.restoreRecommendDismiss?.addEventListener("click", () => {
  localStorage.setItem(RESTORE_RECOMMEND_DISMISS_KEY, new Date().toISOString().slice(0, 10));
  els.restoreRecommendBanner?.classList.add("hidden");
});

els.logOcrNotice?.addEventListener("click", (event) => {
  const button = event.target.closest(".log-ocr-notice-dismiss");
  if (!button) return;
  const noticeKey = button.getAttribute("data-ocr-notice-key");
  if (!noticeKey) return;
  const recent = lastPayload?.accountSwitchOcr?.recent || [];
  const match = recent.find((item) => accountSwitchOcrNoticeKey(item) === noticeKey);
  if (match) {
    dismissAccountSwitchOcrNotice(match);
  } else {
    const dismissed = readDismissedOcrNotices();
    if (!dismissed.includes(noticeKey)) {
      dismissed.unshift(noticeKey);
      localStorage.setItem(OCR_NOTICE_DISMISS_KEY, JSON.stringify(dismissed.slice(0, 50)));
    }
  }
  if (lastPayload) {
    renderAccountSwitchOcrNotice(lastPayload);
  } else {
    els.logOcrNotice.hidden = true;
    els.logOcrNotice.innerHTML = "";
  }
});

els.restoreRecommendOpen?.addEventListener("click", (event) => {
  if (botIsActive()) {
    event.preventDefault();
    setCommandStatus("Stop the bot before opening emulator restore.", "warn");
  }
});

els.addAccountOpen?.addEventListener("click", (event) => {
  if (botIsActive()) {
    event.preventDefault();
    setCommandStatus("Stop the bot before adding a new account.", "warn");
    return;
  }
  if (lastPayload?.gnbotsOnline === false) {
    event.preventDefault();
    setCommandStatus("Launch GnBots first, then add accounts from Settings.", "warn");
  }
});

(async function init() {
  await loadConfig();
  try {
    const setupRes = await fetch("/api/setup/status");
    if (setupRes.ok) {
      const setup = await setupRes.json();
      const banner = document.getElementById("setup-banner");
      const launchBtn = document.getElementById("setup-banner-link");
      if (banner && !setup.setupComplete) {
        banner.classList.remove("hidden");
      }
      launchBtn?.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/setup/launch-wizard", { method: "POST" });
          const body = await res.json();
          if (!res.ok) throw new Error(body.detail || "Could not launch wizard.");
        } catch (error) {
          setCommandStatus(error.message || "Could not launch setup wizard.", "warn");
        }
      });
    }
  } catch (_) {}
  await loadCommandCatalog();
  if (window.GnBotsNotifications) {
    await window.GnBotsNotifications.initNotifications(document.getElementById("notifications-btn"));
  }
  await loadConfig();
  await refresh();
  await loadScreenshots({ bust: true });
  scheduleScreenshotRefresh();
  scheduleRefresh();
})();
