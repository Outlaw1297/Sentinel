const EMULATOR_UID_LABELS = {
  ldplayer64: "LDPlayer (64-bit)",
  ldplayer32: "LDPlayer (32-bit)",
  memu: "MEmu",
  memu64: "MEmu (64-bit)",
  nox: "Nox",
};

const EMULATOR_LABEL_FOR_UID = {
  ldplayer64: "LDPlayer",
  ldplayer32: "LDPlayer",
  memu: "MEmu",
  memu64: "MEmu",
  nox: "Nox",
};

const SETTINGS_GROUPS = [
  {
    id: "run",
    title: "Bot run",
    description: "Profile selection and run-loop behavior.",
    fields: [
      { key: "SelectedProfile", label: "Selected profile", type: "profile" },
      { key: "Sessions", label: "Max concurrent sessions", type: "number", min: 1, max: 99 },
      {
        key: "AutoRestart",
        label: "Auto restart",
        type: "boolean",
      },
      { key: "FastBootSessions", label: "Fast boot sessions", type: "boolean" },
    ],
  },
  {
    id: "timeouts",
    title: "Timeouts & booting",
    description: "Emulator and action timeout values (seconds unless noted).",
    fields: [
      { key: "TimeoutEmulatorStart", label: "Emulator start", type: "number", min: 30, max: 600 },
      { key: "TimeoutAndroidBoot", label: "Android boot", type: "number", min: 60, max: 900 },
      { key: "TimeoutFirstImage", label: "First image", type: "number", min: 10, max: 600 },
      { key: "TimeoutActivity", label: "Activity", type: "number", min: 30, max: 900 },
      { key: "TimeoutSameScreen", label: "Same screen", type: "number", min: 30, max: 900 },
      { key: "TimeoutMaxAction", label: "Max action", type: "number", min: 5, max: 300 },
      { key: "BootingDelay", label: "Booting delay", type: "number", min: 0, max: 300 },
      { key: "BootingRetries", label: "Booting retries", type: "number", min: 0, max: 20 },
      { key: "BootingSkipThreshold", label: "Booting skip threshold", type: "number", min: 0, max: 50 },
    ],
  },
  {
    id: "emulator",
    title: "Emulator",
    description: "Emulator type and install paths.",
    fields: [
      {
        key: "Emulator",
        label: "Emulator label",
        type: "select",
        options: ["LDPlayer", "MEmu", "Nox"],
        hint: "Display name in GnBots settings. Should match the UID below.",
      },
      {
        key: "LastSelectedEmulatorUID",
        label: "Emulator UID",
        type: "text",
        placeholder: "ldplayer64",
        hint: "This is what GnBots actually uses to launch emulators (e.g. ldplayer64).",
      },
      { key: "LDPath64", label: "LDPlayer 64-bit path", type: "text", placeholder: "C:\\LDPlayer\\LDPlayer9" },
      { key: "LDPath32", label: "LDPlayer 32-bit path", type: "text", placeholder: "C:\\LDPlayer\\LDPlayer9" },
      { key: "NoxPath", label: "Nox path", type: "text", placeholder: "C:\\Program Files\\Nox" },
      { key: "MemuPath", label: "MEmu path", type: "text", placeholder: "C:\\Program Files\\Microvirt\\MEmu" },
    ],
  },
  {
    id: "debug",
    title: "Debugging",
    description: "Verbose logging and simulation flags.",
    fields: [
      { key: "ScriptDebugLogging", label: "Script debug logging", type: "boolean" },
      { key: "ImageDebugging", label: "Image debugging", type: "boolean" },
      { key: "LocalDebugging", label: "Local debugging", type: "boolean" },
      { key: "SimulateActionDebug", label: "Simulate action debug", type: "boolean" },
      { key: "SimulateAppDebug", label: "Simulate app debug", type: "boolean" },
    ],
  },
  {
    id: "misc",
    title: "General",
    description: "Language, logging, and API server options.",
    fields: [
      { key: "Language", label: "Language", type: "text", placeholder: "en" },
      { key: "MaxDisplayedLogs", label: "Max displayed logs", type: "number", min: 100, max: 10000 },
      { key: "ScreenshotCache", label: "Screenshot cache", type: "number", min: 1, max: 200 },
      { key: "UseWebServer", label: "Remote API enabled", type: "boolean", readOnly: true },
      { key: "WebServerPort", label: "Remote API port", type: "number", readOnly: true },
    ],
  },
];

const HIDDEN_KEYS = new Set(
  [
    "License",
    "LocationX",
    "LocationY",
    "SizeWidth",
    "SizeHeight",
    "Maximized",
    "Minimized",
    "AccountFormLocationX",
    "AccountFormLocationY",
    "AccountFormSizeWidth",
    "AccountFormSizeHeight",
    "AccountFormMaximized",
    "AccountFormMinimized",
    "FirstSetup",
    "TrialMode",
    "UpgradeRequired",
    "SubmittedFeedback",
    "LastShownMOTD",
    "TotalRuntime",
    "LastAccountId",
    "LastSelectedAppUID",
    "LastSelectedInstance",
    "MaxInstances",
    "EmulatorPathCollection",
    "IsBotServer",
    "AutoUpdate",
    "DeactivateDpiAwarness",
  ].map((key) => key.toLowerCase()),
);

const els = {
  gnbotsStatus: document.getElementById("gnbots-status"),
  lastUpdated: document.getElementById("last-updated"),
  refreshBtn: document.getElementById("refresh-btn"),
  pageStatus: document.getElementById("page-status"),
  settingsGroups: document.getElementById("settings-groups"),
  settingsRaw: document.getElementById("settings-raw"),
  toggleAdvancedBtn: document.getElementById("toggle-advanced-btn"),
  restartGnBotsBtn: document.getElementById("restart-gnbots-btn"),
  settingsLockedBanner: document.getElementById("settings-locked-banner"),
  settingsSubtitle: document.getElementById("settings-subtitle"),
  settingsTabs: document.querySelectorAll(".settings-tab"),
  tabBot: document.getElementById("tab-bot"),
  tabAccounts: document.getElementById("tab-accounts"),
  tabNames: document.getElementById("tab-names"),
  tabBulk: document.getElementById("tab-bulk"),
  tabProvision: document.getElementById("tab-provision"),
  provisionLockedBanner: document.getElementById("provision-locked-banner"),
  provisionPageStatus: document.getElementById("provision-page-status"),
  provisionFormPanel: document.getElementById("provision-form-panel"),
  provisionFormLoading: document.getElementById("provision-form-loading"),
  provisionForm: document.getElementById("provision-form"),
  provisionSummaryGrid: document.getElementById("provision-summary-grid"),
  provisionAccountName: document.getElementById("provision-account-name"),
  provisionTemplateSelect: document.getElementById("provision-template-select"),
  provisionTemplateHint: document.getElementById("provision-template-hint"),
  provisionStartBtn: document.getElementById("provision-start-btn"),
  provisionJobPanel: document.getElementById("provision-job-panel"),
  provisionJobStatus: document.getElementById("provision-job-status"),
  provisionJobSteps: document.getElementById("provision-job-steps"),
  provisionHistoryPanel: document.getElementById("provision-history-panel"),
  provisionHistoryList: document.getElementById("provision-history-list"),
  namesLockedBanner: document.getElementById("names-locked-banner"),
  namesPageStatus: document.getElementById("names-page-status"),
  accountNamesMeta: document.getElementById("account-names-meta"),
  accountNamesSaveAll: document.getElementById("account-names-save-all"),
  accountNamesList: document.getElementById("account-names-list"),
  bulkLockedBanner: document.getElementById("bulk-locked-banner"),
  bulkPageStatus: document.getElementById("bulk-page-status"),
  bulkActionsMeta: document.getElementById("bulk-actions-meta"),
  bulkActionSelect: document.getElementById("bulk-action-select"),
  bulkFieldSelect: document.getElementById("bulk-field-select"),
  bulkActionsBulkRow: document.getElementById("bulk-actions-bulk-row"),
  bulkApplyControl: document.getElementById("bulk-apply-control"),
  bulkApplySelectedBtn: document.getElementById("bulk-apply-selected-btn"),
  bulkActionsSelectionRow: document.getElementById("bulk-actions-selection-row"),
  bulkSelectAllBtn: document.getElementById("bulk-select-all-btn"),
  bulkSelectNoneBtn: document.getElementById("bulk-select-none-btn"),
  bulkSaveSelectedBtn: document.getElementById("bulk-save-selected-btn"),
  bulkActionsList: document.getElementById("bulk-actions-list"),
  accountPageStatus: document.getElementById("account-page-status"),
  accountLockedBanner: document.getElementById("account-locked-banner"),
  accountSelect: document.getElementById("account-select"),
  accountSettingsMeta: document.getElementById("account-settings-meta"),
  accountTemplatesPanel: document.getElementById("account-templates-panel"),
  accountTemplateSelect: document.getElementById("account-template-select"),
  accountTemplateDescription: document.getElementById("account-template-description"),
  accountTemplateApply: document.getElementById("account-template-apply"),
  accountTemplateCreate: document.getElementById("account-template-create"),
  accountTemplateRemove: document.getElementById("account-template-remove"),
  accountAdvancedPanel: document.getElementById("account-advanced-panel"),
  accountAdvancedBody: document.getElementById("account-advanced-body"),
  accountActionsPanel: document.getElementById("account-actions-panel"),
  accountActionsList: document.getElementById("account-actions-list"),
  tabMonitor: document.getElementById("tab-monitor"),
  tabRestore: document.getElementById("tab-restore"),
  tabAutomation: document.getElementById("tab-automation"),
  restoreLockedBanner: document.getElementById("restore-locked-banner"),
  restoreElevationBanner: document.getElementById("restore-elevation-banner"),
  restorePageStatus: document.getElementById("restore-page-status"),
  restorePathPanel: document.getElementById("restore-path-panel"),
  restoreBackupsDir: document.getElementById("restore-backups-dir"),
  restoreBackupsSave: document.getElementById("restore-backups-save"),
  restoreBackupsMeta: document.getElementById("restore-backups-meta"),
  restoreSummaryPanel: document.getElementById("restore-summary-panel"),
  restoreApkAccountsPanel: document.getElementById("restore-apk-accounts-panel"),
  restoreApkAccountsSummary: document.getElementById("restore-apk-accounts-summary"),
  restoreApkAccountsMeta: document.getElementById("restore-apk-accounts-meta"),
  restoreApkAccountList: document.getElementById("restore-apk-account-list"),
  apkSelectActiveBtn: document.getElementById("apk-select-active-btn"),
  apkSelectAllBtn: document.getElementById("apk-select-all-btn"),
  apkSelectNoneBtn: document.getElementById("apk-select-none-btn"),
  restoreInstanceList: document.getElementById("restore-instance-list"),
  automationPageStatus: document.getElementById("automation-page-status"),
  automationToggles: document.getElementById("automation-toggles"),
  automationMeta: document.getElementById("automation-meta"),
  automationStuckRulesBody: document.getElementById("automation-stuck-rules-body"),
  automationStuckLearnBtn: document.getElementById("automation-stuck-learn-btn"),
  automationReportBody: document.getElementById("automation-report-body"),
  automationAssistantBody: document.getElementById("automation-assistant-body"),
  automationReportDays: document.getElementById("automation-report-days"),
  automationRefreshBtn: document.getElementById("automation-refresh-btn"),
  automationRunTickBtn: document.getElementById("automation-run-tick-btn"),
  automationSuggestBtn: document.getElementById("automation-suggest-btn"),
  monitorPageStatus: document.getElementById("monitor-page-status"),
  monitorConfigPath: document.getElementById("monitor-config-path"),
  monitorSettingsGroups: document.getElementById("monitor-settings-groups"),
  monitorSettingsRaw: document.getElementById("monitor-settings-raw"),
  toggleMonitorRawBtn: document.getElementById("toggle-monitor-raw-btn"),
};

let profileNames = [];
let restartBusy = false;
let profileInUse = "";
let configuredProfile = "";
let runtimeProfile = "";
let botActive = false;
let botState = "";
let profileEditLocked = false;
let settingsActivityPollTimer = null;

const SETTINGS_ACTIVITY_TABS = new Set(["bot", "accounts", "names", "bulk", "provision", "restore"]);

let currentSettings = {};
let gnbotsOnline = false;
let settingsWritable = true;
let busyKeys = new Set();

let activeSettingsTab = "bot";
let profileAccounts = [];
let selectedAccountId = "";
let accountActionsWritable = true;
let currentAccountActions = [];
let currentAccountAdvanced = null;
let currentSwitchNameHistory = [];
let switchNameRows = [];
let switchNamesWritable = true;
let switchNamesBusy = false;
let bulkActionCatalog = [];
let bulkFieldRows = [];
let bulkFieldMeta = null;
let bulkSelectedScriptSuffix = "";
let bulkSelectedFieldKey = "";
let bulkFieldsWritable = true;
let bulkFieldsBusy = false;
let bulkSelectedAccountIds = new Set();
let profileTemplates = [];
let accountSettingsBusy = false;
let accountActionBusyIds = new Set();
let accountActionsBusy = false;

let monitorGroups = [];
let currentMonitorConfig = {};
let monitorResolvedPaths = {};
let ldHealthDefaults = {};
let ldHealthEffective = {};
let monitorBusyKeys = new Set();

let restoreRows = [];
let restoreBackupsBusy = false;
let restoreBackupsDir = "";
let restoreBusy = false;
let restoreProgressByIndex = {};
let activeRestorePollToken = 0;
let restorePollLoopActive = false;
let availableBackups = [];
let backupAssignmentBusyIndex = null;
let provisionPreview = null;
let provisionBusy = false;
let provisionPollTimer = null;
let activeProvisionJobId = "";

const PROVISION_STEP_ORDER = [
  "queued",
  "creating-ld",
  "configuring",
  "syncing-apk",
  "installing-apk",
  "adding-profile",
  "completed",
];

const PROVISION_STEP_LABELS = {
  queued: "Queued",
  "creating-ld": "Create LDPlayer instance",
  configuring: "Apply recommended settings",
  "syncing-apk": "Fetch latest APK",
  "installing-apk": "Install Whiteout Survival",
  "adding-profile": "Add GnBots profile account",
  completed: "Done",
  failed: "Failed",
};

function setProvisionPageStatus(message, tone = "") {
  if (!els.provisionPageStatus) return;
  els.provisionPageStatus.textContent = message || "";
  els.provisionPageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function provisionLocked() {
  return profileEditLocked || provisionPreview?.writable === false;
}

function clearSettingsActivityPoll() {
  if (settingsActivityPollTimer) {
    clearTimeout(settingsActivityPollTimer);
    settingsActivityPollTimer = null;
  }
}

function scheduleSettingsActivityPoll() {
  clearSettingsActivityPoll();
  if (!SETTINGS_ACTIVITY_TABS.has(activeSettingsTab) || document.hidden) {
    return;
  }
  const poll = async () => {
    if (document.hidden || !SETTINGS_ACTIVITY_TABS.has(activeSettingsTab)) {
      clearSettingsActivityPoll();
      return;
    }
    await refreshSettingsActivity();
    if (activeSettingsTab === "restore" || activeSettingsTab === "monitor") {
      await loadCapabilities();
    }
    settingsActivityPollTimer = window.setTimeout(poll, 10000);
  };
  settingsActivityPollTimer = window.setTimeout(poll, 1500);
}

async function refreshSettingsActivity() {
  try {
    const response = await fetch("/api/bot-activity", { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      applyBotActivityFromServer(body);
    }
  } catch {
    // ignore transient poll errors
  }
}

function applyBotActivityFromServer(body) {
  const wasNamesWritable = switchNamesWritable;
  const wasBulkWritable = bulkFieldsWritable;
  const wasAccountsWritable = accountActionsWritable;
  const wasSettingsWritable = settingsWritable;

  profileEditLocked = body.profileEditLocked === true || body.writable === false;
  const writable = body.writable !== false;
  botActive = Boolean(body.botActive);
  botState = body.botState || botState;
  settingsWritable = writable;
  switchNamesWritable = writable;
  bulkFieldsWritable = writable;
  accountActionsWritable = writable;

  if (provisionPreview) {
    provisionPreview = { ...provisionPreview, writable, botActive: profileEditLocked };
  }

  applySettingsLockState();
  applySwitchNamesLockState();
  applyBulkActionsLockState();
  applyAccountLockState();
  applyProvisionLockState();
  applyRestoreLockState();

  if (activeSettingsTab === "names" && wasNamesWritable !== switchNamesWritable && switchNameRows.length) {
    renderAccountNamesList();
    setNamesPageStatus(
      switchNamesLocked()
        ? "Switch account names are read-only while bot sessions are running."
        : `Loaded ${switchNameRows.length} switch account name${switchNameRows.length === 1 ? "" : "s"}. Edit any row, then Save all names.`,
      switchNamesLocked() ? "warn" : "ok",
    );
  } else if (activeSettingsTab === "bot" && wasSettingsWritable !== settingsWritable) {
    renderGroups();
    renderRawSettings();
  } else if (activeSettingsTab === "bulk" && wasBulkWritable !== bulkFieldsWritable && bulkFieldRows.length) {
    renderBulkActionFieldList();
    setBulkPageStatus(
      bulkActionsSessionLocked()
        ? "Bulk action settings are read-only while bot sessions are running."
        : "Select accounts and save changes.",
      bulkActionsSessionLocked() ? "warn" : "ok",
    );
  } else if (activeSettingsTab === "accounts" && wasAccountsWritable !== accountActionsWritable) {
    renderAccountActions(currentAccountActions);
    applyAccountLockState();
  }
}

function applyProvisionLockState() {
  const banner = els.provisionLockedBanner;
  if (banner) {
    if (provisionLocked()) {
      banner.textContent = "Stop the bot from the dashboard before provisioning a new account.";
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  }
  if (els.provisionForm) {
    els.provisionForm.classList.toggle("locked", provisionLocked());
  }
  if (els.provisionStartBtn) {
    const hasCloneSources = provisionHasCloneSources();
    els.provisionStartBtn.disabled = provisionLocked() || provisionBusy || !hasCloneSources;
  }
  if (els.provisionAccountName) {
    els.provisionAccountName.disabled = provisionLocked() || provisionBusy;
  }
  if (els.provisionTemplateSelect) {
    els.provisionTemplateSelect.disabled = provisionLocked() || provisionBusy;
  }
}

function provisionHasCloneSources() {
  const accounts = provisionPreview?.templateAccounts || [];
  const templates = provisionPreview?.profileTemplates || [];
  return accounts.length > 0 || templates.length > 0;
}

function renderProvisionSummary() {
  if (!els.provisionSummaryGrid || !provisionPreview) return;
  const profile = provisionPreview.profile || "—";
  const ldCount = Number(provisionPreview.ldInstanceCount || 0);
  const accounts = provisionPreview.templateAccounts || [];
  const templates = provisionPreview.profileTemplates || [];
  els.provisionSummaryGrid.innerHTML = `
    <div><span class="label">Profile</span><strong>${escapeHtml(profile)}</strong></div>
    <div><span class="label">LDPlayer instances</span><strong>${ldCount}</strong></div>
    <div><span class="label">Profile accounts</span><strong>${accounts.length}</strong></div>
    <div><span class="label">Action templates</span><strong>${templates.length}</strong></div>
  `;
}

function provisionCloneSourceLabel(value) {
  if (!value || !provisionPreview) return value || "";
  if (value.startsWith("account:")) {
    const accountId = value.slice("account:".length);
    const account = (provisionPreview.templateAccounts || []).find((row) => row.id === accountId);
    return account?.name || accountId;
  }
  if (value.startsWith("template:")) {
    const title = value.slice("template:".length);
    const template = (provisionPreview.profileTemplates || []).find((row) => row.title === title);
    return template?.title || title;
  }
  return value;
}

function renderProvisionTemplateOptions() {
  if (!els.provisionTemplateSelect) return;
  const accounts = provisionPreview?.templateAccounts || [];
  const templates = provisionPreview?.profileTemplates || [];
  if (!accounts.length && !templates.length) {
    els.provisionTemplateSelect.innerHTML = `<option value="">No clone sources available</option>`;
    return;
  }

  const accountOptions = accounts
    .map((row) => {
      const suffix = row.active ? "" : " · disabled";
      return `<option value="account:${escapeHtml(row.id)}">${escapeHtml(row.name)} (LD ${row.instanceId})${suffix}</option>`;
    })
    .join("");

  const templateOptions = templates
    .map((row) => {
      const description = row.description ? ` — ${row.description}` : "";
      return `<option value="template:${escapeHtml(row.title)}">${escapeHtml(row.title)}${escapeHtml(description)}</option>`;
    })
    .join("");

  const groups = [];
  if (accountOptions) {
    groups.push(`<option value="" disabled>— Profile accounts —</option>${accountOptions}`);
  }
  if (templateOptions) {
    groups.push(`<option value="" disabled>— Action templates —</option>${templateOptions}`);
  }
  els.provisionTemplateSelect.innerHTML = groups.join("");

  const defaultSource =
    provisionPreview?.defaultCloneSource ||
    (accounts[0] ? `account:${accounts[0].id}` : templates[0] ? `template:${templates[0].title}` : "");
  if (defaultSource) {
    els.provisionTemplateSelect.value = defaultSource;
  }
}

function inferProvisionFailedStep(job) {
  if (job?.account) return "adding-profile";
  if (job?.apkVersion != null) return "installing-apk";
  if (job?.settingsResult) return "configuring";
  if (job?.instanceIndex != null) return "creating-ld";
  return "queued";
}

function provisionStepState(stepId, job) {
  const status = String(job?.status || "");
  if (status === "failed") {
    const failedAt = inferProvisionFailedStep(job);
    const stepIndex = PROVISION_STEP_ORDER.indexOf(stepId);
    const failedIndex = PROVISION_STEP_ORDER.indexOf(failedAt);
    if (stepIndex < failedIndex) return "done";
    if (stepIndex === failedIndex) return "failed";
    return "pending";
  }
  if (status === "completed") return "done";
  const currentIndex = PROVISION_STEP_ORDER.indexOf(status);
  const stepIndex = PROVISION_STEP_ORDER.indexOf(stepId);
  if (stepIndex < 0) return "pending";
  if (currentIndex < 0) return "pending";
  if (stepIndex < currentIndex) return "done";
  if (stepIndex === currentIndex) return "active";
  return "pending";
}

function renderProvisionJob(job) {
  if (!job) return;
  if (els.provisionJobPanel) {
    els.provisionJobPanel.classList.remove("hidden");
  }
  if (els.provisionJobStatus) {
    const tone = job.status === "failed" ? "error" : job.status === "completed" ? "ok" : "pending";
    els.provisionJobStatus.className = `provision-job-message ${tone}`;
    els.provisionJobStatus.textContent = job.message || job.status || "";
  }
  if (els.provisionJobSteps) {
    const steps = PROVISION_STEP_ORDER.filter((step) => step !== "completed");
    els.provisionJobSteps.innerHTML = steps
      .map((stepId) => {
        const state = provisionStepState(stepId, job);
        return `<li class="provision-step ${state}" data-step="${stepId}">${escapeHtml(PROVISION_STEP_LABELS[stepId] || stepId)}</li>`;
      })
      .join("");
  }
}

function renderProvisionHistory(jobs) {
  if (!els.provisionHistoryList) return;
  const rows = Array.isArray(jobs) ? jobs : [];
  if (!rows.length) {
    els.provisionHistoryList.innerHTML = `<p class="settings-loading">No provisioning jobs yet.</p>`;
    return;
  }
  els.provisionHistoryList.innerHTML = rows
    .map((job) => {
      const status = String(job.status || "");
      const tone = status === "failed" ? "error" : status === "completed" ? "ok" : "pending";
      const when = job.finishedAt || job.startedAt || "";
      const account = job.account?.name || job.accountName || "—";
      return `
        <article class="provision-history-card ${tone}">
          <div class="provision-history-head">
            <strong>${escapeHtml(account)}</strong>
            <span class="provision-history-status">${escapeHtml(status)}</span>
          </div>
          <p>${escapeHtml(job.message || "")}</p>
          <p class="provision-history-meta">${escapeHtml(when)}</p>
        </article>
      `;
    })
    .join("");
}

function clearProvisionPoll() {
  if (provisionPollTimer) {
    clearTimeout(provisionPollTimer);
    provisionPollTimer = null;
  }
}

function scheduleProvisionPoll(jobId) {
  clearProvisionPoll();
  if (!jobId) return;
  activeProvisionJobId = jobId;
  const poll = async () => {
    if (activeSettingsTab !== "provision" || document.hidden) {
      clearProvisionPoll();
      return;
    }
    try {
      const response = await fetch(`/api/provision/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (response.ok && body.job) {
        renderProvisionJob(body.job);
        const status = String(body.job.status || "");
        setProvisionPageStatus(body.job.message || "", status === "failed" ? "error" : status === "completed" ? "ok" : "pending");
        if (status === "completed" || status === "failed") {
          provisionBusy = false;
          applyProvisionLockState();
          await loadProvisionHistory();
          if (status === "completed") {
            setProvisionPageStatus(
              `${body.job.message || "Provisioning completed."} Restart GnBots to pick up the new account.`,
              "ok",
            );
          }
          return;
        }
      }
    } catch {
      // keep polling
    }
    provisionPollTimer = setTimeout(poll, 4000);
  };
  provisionPollTimer = setTimeout(poll, 2000);
}

async function loadProvisionHistory() {
  try {
    const response = await fetch("/api/provision/jobs", { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      renderProvisionHistory(body.jobs || []);
    }
  } catch {
    // ignore history errors
  }
}

async function loadProvisionTab() {
  setProvisionPageStatus("Loading provisioning options…", "pending");
  if (els.provisionFormLoading) {
    els.provisionFormLoading.textContent = "Loading provisioning options…";
    els.provisionFormLoading.classList.remove("error", "hidden");
  }
  if (els.provisionForm) {
    els.provisionForm.classList.add("hidden");
  }
  try {
    const previewResponse = await fetch("/api/provision/account/preview", { cache: "no-store" });
    const preview = await previewResponse.json().catch(() => ({}));

    if (!previewResponse.ok) {
      const detail = preview.detail ?? preview.message ?? `HTTP ${previewResponse.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    botActive = Boolean(preview.botActive);
    profileEditLocked = preview.writable === false;
    setGnbotsStatus(true, { writable: !profileEditLocked });

    provisionPreview = preview;
    if (els.provisionFormLoading) els.provisionFormLoading.classList.add("hidden");
    if (els.provisionForm) els.provisionForm.classList.remove("hidden");

    renderProvisionSummary();
    renderProvisionTemplateOptions();
    applyProvisionLockState();

    await loadProvisionHistory();

    if (provisionLocked()) {
      setProvisionPageStatus("Provisioning is disabled while the bot is running. Stop the bot to continue.", "warn");
    } else if (!provisionHasCloneSources()) {
      setProvisionPageStatus("No profile accounts or action templates available to clone from.", "error");
    } else {
      setProvisionPageStatus(
        "Enter a new account name, pick a profile account or action template, then create the LDPlayer instance and profile row.",
        "ok",
      );
    }
    if (els.lastUpdated) {
      els.lastUpdated.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    }
  } catch (error) {
    if (els.provisionFormLoading) {
      els.provisionFormLoading.textContent = error.message || "Failed to load provisioning options.";
      els.provisionFormLoading.classList.add("error");
      els.provisionFormLoading.classList.remove("hidden");
    }
    setProvisionPageStatus(error.message || "Failed to load provisioning options.", "error");
  }
}

async function startProvisionAccount(event) {
  event?.preventDefault();
  if (provisionLocked()) {
    setProvisionPageStatus("Stop the bot before provisioning a new account.", "warn");
    return;
  }
  if (provisionBusy) return;

  const accountName = els.provisionAccountName?.value.trim() || "";
  const cloneSource = els.provisionTemplateSelect?.value.trim() || "";
  if (!accountName) {
    setProvisionPageStatus("Account name is required.", "error");
    return;
  }
  if (!cloneSource) {
    setProvisionPageStatus("Pick a profile account or action template to clone settings from.", "error");
    return;
  }

  const templateLabel = provisionCloneSourceLabel(cloneSource);
  const sourceKind = cloneSource.startsWith("template:") ? "action template" : "profile account";
  const message = [
    `Create LDPlayer instance "${accountName}" with recommended settings?`,
    `Clone action settings from ${sourceKind} "${templateLabel}".`,
    "Install the latest Whiteout Survival APK and add the account to the GnBots profile.",
    "Restart GnBots when the job completes.",
  ].join("\n");
  if (!window.confirm(message)) return;

  provisionBusy = true;
  applyProvisionLockState();
  setProvisionPageStatus(`Starting provisioning for ${accountName}…`, "pending");

  try {
    const response = await fetch("/api/provision/account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        accountName,
        cloneSource,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail ?? body.message ?? `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    const job = body.job || {};
    activeProvisionJobId = job.id || "";
    renderProvisionJob(job);
    await loadProvisionHistory();
    scheduleProvisionPoll(activeProvisionJobId);
    setProvisionPageStatus(job.message || "Provisioning started…", "pending");
  } catch (error) {
    provisionBusy = false;
    applyProvisionLockState();
    setProvisionPageStatus(error.message || "Failed to start provisioning.", "error");
  }
}

let emulatorHealthByIndex = {};
let emulatorHealthLoadError = "";
let emulatorHealthLoading = false;
let fixSettingsBusyIndex = null;
let restoreAllBusy = false;
let fixAllSettingsBusy = false;
let emulatorApkByIndex = {};
let emulatorApkLoadError = "";
let emulatorApkLoading = false;
let updateApkBusyIndex = null;
let updateAllApksBusy = false;
let updateSelectedApksBusy = false;
let forceUpdateSelectedApksBusy = false;
let activeApkUpdatePollToken = 0;
let checkRemoteApkBusy = false;
let remoteApkStatus = null;
let apkUpdateInstances = [];
let apkUpdateSelectedIndexes = new Set();
let apkSelectionSaveTimer = null;
let emulatorApkPollTimer = null;
let dashboardAccounts = [];
let monitorCapabilities = null;

function adminReady() {
  return Boolean(monitorCapabilities?.adminReady ?? monitorCapabilities?.isAdmin);
}

function capability(featureId) {
  return monitorCapabilities?.byId?.[featureId] || null;
}

function elevationLocked(featureId) {
  const row = capability(featureId);
  if (!row) return !adminReady();
  return row.available === false;
}

function fixSettingsLocked() {
  return restoreLocked() || elevationLocked("fix-ldplayer-settings");
}

function monitorFieldAdminLocked(field) {
  if (!field?.requiresAdmin) return false;
  return !adminReady();
}

async function loadCapabilities() {
  try {
    const response = await fetch("/api/capabilities", { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return;
    monitorCapabilities = body;
    updateRestoreElevationBanner();
    applyRestoreLockState();
    if (restoreRows.length) {
      renderRestoreSummary(restoreRows);
      renderRestoreInstanceList(restoreRows);
    }
    if (monitorGroups.length) {
      renderMonitorGroups();
    }
  } catch {
    // ignore background capability poll failures
  }
}

function apkNeedsInstallOrUpdate(apk) {
  return Boolean(
    apk &&
      !apk.error &&
      (apk.updateAvailable || apk.checkState === "not_installed" || apk.gameUpdateRequired),
  );
}

function selectedInstanceIndexes() {
  return [...apkUpdateSelectedIndexes]
    .map((value) => Number(value))
    .filter((index) => !Number.isNaN(index) && index >= 0)
    .sort((a, b) => a - b);
}

function indexesWithApkUpdatesForSelectedInstances() {
  const selected = new Set(selectedInstanceIndexes());
  return indexesWithApkUpdates().filter((index) => selected.has(index));
}

function clearEmulatorApkPoll() {
  if (emulatorApkPollTimer != null) {
    window.clearTimeout(emulatorApkPollTimer);
    emulatorApkPollTimer = null;
  }
}

function scheduleEmulatorApkSync() {
  clearEmulatorApkPoll();
  const booting = Object.entries(emulatorApkByIndex)
    .filter(([, apk]) => apk?.checkState === "booting")
    .map(([index]) => Number(index));
  if (!booting.length || activeSettingsTab !== "restore" || document.hidden) return;

  emulatorApkPollTimer = window.setTimeout(async () => {
    await loadEmulatorApkForIndexes(booting, { merge: true, force: true });
    if (activeSettingsTab === "restore" && !document.hidden) {
      renderRestoreSummary(restoreRows);
      renderRestoreInstanceList(restoreRows);
    }
    scheduleEmulatorApkSync();
  }, 10000);
}

async function refreshEmulatorApkRows(indexes, { force = true } = {}) {
  await loadEmulatorApkForIndexes(indexes, { merge: true, force });
  renderRestoreSummary(restoreRows);
  renderRestoreInstanceList(restoreRows);
}

function formatValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function parseStoredBoolean(value) {
  if (typeof value === "boolean") return value;
  const text = String(value).trim().toLowerCase();
  return text === "true" || text === "1";
}

function settingsLocked() {
  return !settingsWritable;
}

function updateLockedBanner() {
  const banner = els.settingsLockedBanner;
  if (!banner) return;
  if (!settingsLocked()) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.textContent =
    "Settings are read-only while bot sessions are running. Stop the bot from the dashboard, then edit here.";
  banner.classList.remove("hidden");
}

function applySettingsLockState() {
  if (els.settingsGroups) {
    els.settingsGroups.classList.toggle("locked", settingsLocked());
  }
  updateLockedBanner();
}

function setAccountPageStatus(message, tone = "") {
  if (!els.accountPageStatus) return;
  els.accountPageStatus.textContent = message || "";
  els.accountPageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function setMonitorPageStatus(message, tone = "") {
  if (!els.monitorPageStatus) return;
  els.monitorPageStatus.textContent = message || "";
  els.monitorPageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function restoreLocked() {
  return profileEditLocked;
}

function setRestorePageStatus(message, tone = "", progress = null) {
  if (!els.restorePageStatus) return;
  const pct = progress == null ? null : Math.max(0, Math.min(100, Number(progress) || 0));
  if (pct != null) {
    els.restorePageStatus.innerHTML = `
      <div class="restore-progress-panel restore-page-progress">
        <div class="restore-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
          <div class="restore-progress-fill" style="width:${pct}%"></div>
        </div>
        <p class="restore-progress-meta">${escapeHtml(message || "Working…")} <span>${pct}%</span></p>
      </div>`;
  } else {
    els.restorePageStatus.textContent = message || "";
  }
  els.restorePageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function renderRestoreProgressPanel(index) {
  const job = restoreProgressByIndex[index] || {};
  const formatted = window.GnBotsRestore
    ? window.GnBotsRestore.formatRestoreJobStatus(job)
    : { progress: 10, message: "Restoring…" };
  const pct = formatted.progress;
  return `
    <div class="restore-progress-panel" data-restore-progress-index="${index}">
      <div class="restore-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
        <div class="restore-progress-fill" style="width:${pct}%"></div>
      </div>
      <p class="restore-progress-meta">${escapeHtml(formatted.message)} <span>${pct}%</span></p>
    </div>`;
}

function updateRestoreJobProgress(index, job) {
  if (index == null) return;
  restoreProgressByIndex[Number(index)] = job || {};
  const formatted = window.GnBotsRestore
    ? window.GnBotsRestore.formatRestoreJobStatus(job)
    : { progress: 10, message: job?.message || "Restoring…" };
  setRestorePageStatus(formatted.message, "pending", formatted.progress);
  renderRestoreInstanceList(restoreRows);
}

async function resumeActiveRestorePolling(rows) {
  if (!window.GnBotsRestore) return;
  // One loop polls every busy restore job in order so batch restore-all keeps advancing.
  if (restorePollLoopActive) return;

  const pollToken = ++activeRestorePollToken;
  restorePollLoopActive = true;
  restoreBusy = true;
  applyRestoreLockState();
  renderRestoreInstanceList(restoreRows);

  const resolveBusyTargets = async (seedRows) => {
    const fromRows = (seedRows || [])
      .filter((row) => row.restoreBusy && row.restoreJobId)
      .map((row) => ({
        id: row.restoreJobId,
        instanceIndex: row.index,
        instanceName: row.ldName,
      }));
    if (fromRows.length) return fromRows;
    if (typeof window.GnBotsRestore.findActiveRestoreJobs === "function") {
      return window.GnBotsRestore.findActiveRestoreJobs();
    }
    const single = await window.GnBotsRestore.findActiveRestoreJob();
    return single?.id ? [single] : [];
  };

  try {
    let seedRows = rows || restoreRows;
    while (pollToken === activeRestorePollToken) {
      const targets = await resolveBusyTargets(seedRows);
      if (!targets.length) break;

      const active = targets[0];
      const index = Number(active.instanceIndex);
      const label = active.instanceName || `instance ${index}`;
      updateRestoreJobProgress(index, {
        status: "queued",
        message: `Watching restore for ${label}${targets.length > 1 ? ` (${targets.length} queued)` : ""}…`,
        progress: window.GnBotsRestore.progressForRestoreStatus("queued"),
      });

      try {
        const job = await window.GnBotsRestore.pollRestoreJob(active.id, {
          onStatus: (jobStatus) => updateRestoreJobProgress(index, jobStatus),
        });
        if (pollToken !== activeRestorePollToken) return;
        const warnings = job.warnings || [];
        if (warnings.length) {
          setRestorePageStatus(
            `Restore finished for ${label} with ${warnings.length} warning(s): ${warnings[0]}`,
            "warn",
            100,
          );
        } else {
          setRestorePageStatus(`Restore completed for ${label}.`, "ok", 100);
        }
        delete restoreProgressByIndex[index];
      } catch (error) {
        if (pollToken !== activeRestorePollToken) return;
        setRestorePageStatus(error.message || "Restore failed.", "error");
        delete restoreProgressByIndex[index];
      }

      await refreshRestoreTabAfterJob();
      seedRows = restoreRows;
    }
  } finally {
    restorePollLoopActive = false;
    if (pollToken === activeRestorePollToken) {
      restoreBusy = false;
      applyRestoreLockState();
    }
  }
}

function updateRestoreElevationBanner() {
  const banner = els.restoreElevationBanner;
  if (!banner) return;
  if (adminReady() || restoreLocked()) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  const row = capability("fix-ldplayer-settings");
  banner.textContent =
    row?.reason ||
    "Fix settings and post-restore health checks require Sentinel running as Administrator. Restart via StartGnBotStack.bat and approve UAC.";
  banner.classList.remove("hidden");
}

function updateRestoreLockedBanner() {
  const banner = els.restoreLockedBanner;
  if (!banner) return;
  if (!restoreLocked()) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.textContent = `Bot is ${botState || "active"} — stop the bot from the dashboard before restoring emulators or fixing settings.`;
  banner.classList.remove("hidden");
}

function applyRestoreLockState() {
  updateRestoreLockedBanner();
  updateRestoreElevationBanner();
  if (els.restoreInstanceList) {
    els.restoreInstanceList.classList.toggle("locked", restoreLocked());
  }
  if (els.restoreSummaryPanel) {
    els.restoreSummaryPanel.classList.toggle("locked", restoreLocked());
  }
  if (els.restoreApkAccountsPanel) {
    els.restoreApkAccountsPanel.classList.toggle("locked", restoreLocked());
  }
  renderApkAccountSelection();
}

function renderRestorePathPanel(summary) {
  if (!els.restoreBackupsDir) return;

  const backupsDir = String(summary?.backupsDir || restoreBackupsDir || "").trim();
  const backupCount = Number(summary?.backupCount);
  const countLabel = Number.isFinite(backupCount)
    ? `${backupCount} .ldbk file${backupCount === 1 ? "" : "s"} found`
    : "—";

  els.restoreBackupsDir.value = backupsDir;
  if (els.restoreBackupsMeta) {
    els.restoreBackupsMeta.textContent = backupsDir
      ? `${countLabel} in this folder.`
      : "Set the absolute path to your emulator backup folder.";
  }
  if (els.restoreBackupsSave) {
    els.restoreBackupsSave.disabled = restoreBackupsBusy;
  }
}

async function saveRestoreBackupsDir() {
  if (!els.restoreBackupsDir || restoreBackupsBusy) return;

  const value = els.restoreBackupsDir.value.trim();
  if (!value) {
    setRestorePageStatus("Backups folder path is required.", "error");
    return;
  }

  restoreBackupsBusy = true;
  if (els.restoreBackupsSave) els.restoreBackupsSave.disabled = true;
  setRestorePageStatus("Saving backups folder…", "pending");

  try {
    const response = await fetch(
      `/api/monitor-config/ldplayer_backups_dir/update?value=${encodeURIComponent(value)}`,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail || body.error || response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    restoreBackupsDir = String(body.value || value);
    els.restoreBackupsDir.value = restoreBackupsDir;
    if (currentMonitorConfig) {
      currentMonitorConfig.ldplayer_backups_dir = restoreBackupsDir;
    }

    const emulatorsResponse = await fetch("/api/emulators", { cache: "no-store" });
    const emulatorsPayload = await emulatorsResponse.json().catch(() => ({}));
    if (emulatorsResponse.ok) {
      renderRestorePathPanel(emulatorsPayload.summary || {});
    } else {
      renderRestorePathPanel({ backupsDir: restoreBackupsDir });
    }

    const dashboardResponse = await fetch("/api/dashboard", { cache: "no-store" });
    const dashboardPayload = await dashboardResponse.json().catch(() => ({}));
    if (dashboardResponse.ok) {
      dashboardAccounts = dashboardPayload.accounts || [];
      restoreRows = window.GnBotsRestore
        ? window.GnBotsRestore.buildRestoreInstanceRows(dashboardAccounts)
        : [];
      renderRestoreSummary(restoreRows);
      renderRestoreInstanceList(restoreRows);
    }

    setRestorePageStatus(body.message || "Saved backups folder.", "ok");
  } catch (error) {
    setRestorePageStatus(error.message || "Failed to save backups folder.", "error");
  } finally {
    restoreBackupsBusy = false;
    if (els.restoreBackupsSave) els.restoreBackupsSave.disabled = false;
  }
}

function apkInstanceLabel(index) {
  if (index < 0) return "No LDPlayer instance";
  const row = restoreRows.find((entry) => entry.index === index);
  if (row?.ldName) return `${row.ldName} #${index}`;
  return `Instance #${index}`;
}

function groupApkAccountsByInstance(instances) {
  return (instances || [])
    .map((group) => ({
      index: Number(group.index),
      accounts: (group.accounts || []).slice().sort((a, b) =>
        String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }),
      ),
    }))
    .filter((group) => !Number.isNaN(group.index) && group.index >= 0)
    .sort((a, b) => a.index - b.index);
}

function updateApkAccountsSummaryText(instanceCount, totalInstances) {
  const summaryText =
    totalInstances > 0
      ? `${instanceCount}/${totalInstances} instance${totalInstances === 1 ? "" : "s"} selected`
      : "No instances loaded";
  if (els.restoreApkAccountsSummary) {
    els.restoreApkAccountsSummary.textContent = summaryText;
  }
}

function renderApkAccountSelection() {
  if (!els.restoreApkAccountList) return;
  const locked = restoreLocked() || updateAllApksBusy || updateSelectedApksBusy || checkRemoteApkBusy;
  const groups = groupApkAccountsByInstance(apkUpdateInstances);
  const instanceCount = selectedInstanceIndexes().length;
  updateApkAccountsSummaryText(instanceCount, groups.length);
  if (!groups.length) {
    els.restoreApkAccountList.innerHTML = `<p class="settings-loading">No emulator instances found.</p>`;
    if (els.restoreApkAccountsMeta) {
      els.restoreApkAccountsMeta.textContent =
        "No emulator instances are mapped to profile accounts yet.";
    }
    if (els.apkSelectActiveBtn) els.apkSelectActiveBtn.disabled = locked;
    if (els.apkSelectAllBtn) els.apkSelectAllBtn.disabled = locked;
    if (els.apkSelectNoneBtn) els.apkSelectNoneBtn.disabled = locked;
    return;
  }
  if (els.restoreApkAccountsMeta) {
    els.restoreApkAccountsMeta.textContent =
      `${instanceCount} emulator instance${instanceCount === 1 ? "" : "s"} selected. Updating an instance updates Whiteout for every account on it. Selection is saved in monitor config.`;
  }
  els.restoreApkAccountList.innerHTML = groups
    .map((group) => {
      const checked = apkUpdateSelectedIndexes.has(group.index) ? " checked" : "";
      const accountRows = group.accounts
        .map((account) => {
          const activeBadge = account.active
            ? '<span class="badge state-badge ok">Active</span>'
            : '<span class="badge state-badge">Inactive</span>';
          return `
            <div class="restore-apk-account-row">
              <span class="restore-apk-account-sublabel">${escapeHtml(account.name)}</span>
              ${activeBadge}
            </div>`;
        })
        .join("");
      const accountSummary = group.accounts.map((account) => account.name).filter(Boolean).join(", ");
      return `
        <section class="restore-apk-instance-group${checked ? " is-selected" : ""}" data-apk-instance-index="${group.index}">
          <label class="restore-apk-instance-head${locked ? " is-disabled" : ""}">
            <input
              type="checkbox"
              class="restore-apk-instance-checkbox"
              data-apk-instance-index="${group.index}"
              ${checked}
              ${locked ? "disabled" : ""}
            >
            <div class="restore-apk-instance-copy">
              <h3 class="restore-apk-instance-title">${escapeHtml(apkInstanceLabel(group.index))}</h3>
              <p class="restore-apk-instance-sublabel">${escapeHtml(accountSummary || "No mapped accounts")}</p>
            </div>
          </label>
          <div class="restore-apk-instance-accounts" aria-label="Accounts on this instance">
            ${accountRows}
          </div>
        </section>`;
    })
    .join("");
  if (els.apkSelectActiveBtn) els.apkSelectActiveBtn.disabled = locked;
  if (els.apkSelectAllBtn) els.apkSelectAllBtn.disabled = locked;
  if (els.apkSelectNoneBtn) els.apkSelectNoneBtn.disabled = locked;
}

function scheduleApkSelectionSave() {
  if (apkSelectionSaveTimer != null) {
    window.clearTimeout(apkSelectionSaveTimer);
  }
  apkSelectionSaveTimer = window.setTimeout(() => {
    apkSelectionSaveTimer = null;
    void saveApkUpdateSelection();
  }, 350);
}

async function loadApkUpdateSelection() {
  try {
    const response = await fetch("/api/emulators/apk/selection", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return;
    }
    apkUpdateInstances = payload.instances || [];
    apkUpdateSelectedIndexes = new Set(
      (payload.selectedInstanceIndexes || []).map((index) => Number(index)).filter((index) => !Number.isNaN(index)),
    );
    if (payload.cacheVersion && !remoteApkStatus) {
      remoteApkStatus = {
        localVersion: payload.cacheVersion,
        apkReady: true,
        updateAvailable: false,
        persistedOnly: true,
        persistedAt: payload.cacheCheckedAt || null,
      };
    }
    renderApkAccountSelection();
    renderRestoreSummary(restoreRows);
  } catch {
    // ignore selection load failures
  }
}

async function saveApkUpdateSelection() {
  const instanceIndexes = selectedInstanceIndexes();
  try {
    const response = await fetch("/api/emulators/apk/selection", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instanceIndexes }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return;
    }
    apkUpdateInstances = payload.instances || apkUpdateInstances;
    apkUpdateSelectedIndexes = new Set(
      (payload.selectedInstanceIndexes || instanceIndexes)
        .map((index) => Number(index))
        .filter((index) => !Number.isNaN(index)),
    );
    renderApkAccountSelection();
    renderRestoreSummary(restoreRows);
  } catch {
    // ignore save failures
  }
}

function setApkUpdateSelection(instanceIndexes) {
  apkUpdateSelectedIndexes = new Set(
    instanceIndexes.map((index) => Number(index)).filter((value) => !Number.isNaN(value) && value >= 0),
  );
  renderApkAccountSelection();
  renderRestoreSummary(restoreRows);
  scheduleApkSelectionSave();
}

function renderRestoreSummary(rows) {
  if (!els.restoreSummaryPanel) return;
  const troubled = rows.filter((row) => row.troubled);
  const missing = rows.filter((row) => row.missing);
  const unmatched = rows.filter((row) => !row.backupAvailable);
  const manual = rows.filter((row) => row.backupMatchSource === "manual");
  const ldIssueInstances = Object.values(emulatorHealthByIndex).filter(
    (health) => health && !health.error && Number(health.issueCount) > 0,
  ).length;
  const apkUpdateInstances = Object.values(emulatorApkByIndex).filter((apk) =>
    apkNeedsInstallOrUpdate(apk),
  ).length;
  const selectedApkUpdateInstances = indexesWithApkUpdatesForSelectedInstances().length;
  const selectedInstanceCount = selectedInstanceIndexes().length;
  const gameUpdateStuck = Object.values(emulatorApkByIndex).filter((apk) => apk?.gameUpdateRequired).length;
  const cachedVersion =
    remoteApkStatus?.localVersion || rows.find((row) => row.apkVersion)?.apkVersion;
  const thirdParty = remoteApkStatus?.thirdParty;
  const thirdPartyLabel =
    thirdParty?.enabled && thirdParty?.remoteVersion
      ? `${thirdParty.provider || "3rd party"} ${thirdParty.remoteVersion}${
          thirdParty.updateAvailable ? " (newer)" : ""
        }`
      : thirdParty?.enabled
        ? thirdParty.error
          ? `3rd party error`
          : "3rd party on"
        : "";
  const remoteApkLabel = remoteApkStatus
    ? remoteApkStatus.localAheadOfRemote
      ? `Local newer (${remoteApkStatus.remoteVersion || "old zip"})`
      : remoteApkStatus.updateAvailable
        ? remoteApkStatus.source?.startsWith("third_party")
          ? `Newer 3rd-party APK (${remoteApkStatus.remoteVersion || "unknown"})`
          : "Newer zip available"
        : remoteApkStatus.apkReady
          ? remoteApkStatus.remoteVersion && remoteApkStatus.localVersion
            ? `Cache ${remoteApkStatus.localVersion}${thirdPartyLabel ? ` · ${thirdPartyLabel}` : ""}`
            : thirdPartyLabel || "Cache ready"
          : "Cache incomplete"
    : "—";
  const troubledWithBackup = rows.filter((row) => row.troubled && row.backupAvailable);
  const fixAllDisabled =
    fixSettingsLocked() || restoreBusy || restoreAllBusy || fixAllSettingsBusy || fixSettingsBusyIndex != null;
  const updateAllDisabled =
    restoreLocked() ||
    restoreBusy ||
    restoreAllBusy ||
    updateAllApksBusy ||
    updateSelectedApksBusy ||
    forceUpdateSelectedApksBusy ||
    checkRemoteApkBusy ||
    updateApkBusyIndex != null ||
    fixAllSettingsBusy ||
    fixSettingsBusyIndex != null;
  const restoreAllDisabled = restoreLocked() || restoreBusy || restoreAllBusy || !troubledWithBackup.length;
  const actionButtons = [];
  if (troubledWithBackup.length > 0) {
    actionButtons.push(
      `<button
        type="button"
        class="btn btn-small btn-restore-all"
        id="restore-all-btn"
        ${restoreAllDisabled ? "disabled" : ""}
      >${restoreAllBusy ? "Restoring all…" : `Restore all recommended (${troubledWithBackup.length})`}</button>`,
    );
  }
  if (apkUpdateInstances > 0) {
    actionButtons.push(
      `<button
        type="button"
        class="btn btn-small btn-update-all-apks"
        id="update-all-apks-btn"
        ${updateAllDisabled ? "disabled" : ""}
      >${updateAllApksBusy ? "Updating all…" : `Update/install all APKs (${apkUpdateInstances})`}</button>`,
    );
  }
  const selectedButtonDisabled = updateAllDisabled || !selectedInstanceCount;
  actionButtons.push(
    `<button
      type="button"
      class="btn btn-small btn-update-selected-apks"
      id="update-selected-apks-btn"
      ${selectedButtonDisabled ? "disabled" : ""}
    >${updateSelectedApksBusy ? "Updating selected…" : `Update selected instances (${selectedApkUpdateInstances || selectedInstanceCount})`}</button>`,
  );
  actionButtons.push(
    `<button
      type="button"
      class="btn btn-small btn-force-update-selected-apks"
      id="force-update-selected-apks-btn"
      ${selectedButtonDisabled ? "disabled" : ""}
    >${forceUpdateSelectedApksBusy ? "Force updating…" : `Force update selected (${selectedInstanceCount})`}</button>`,
  );
  actionButtons.push(
    `<button
      type="button"
      class="btn btn-small btn-check-remote-apk"
      id="check-remote-apk-btn"
      ${updateAllDisabled ? "disabled" : ""}
    >${checkRemoteApkBusy ? "Checking…" : "Check for newer APK"}</button>`,
  );
  if (remoteApkStatus?.updateAvailable && !remoteApkStatus?.localAheadOfRemote) {
    actionButtons.push(
      `<button
        type="button"
        class="btn btn-small btn-sync-remote-apk"
        id="sync-remote-apk-btn"
        ${updateAllDisabled ? "disabled" : ""}
      >${checkRemoteApkBusy ? "Downloading…" : "Download latest APK"}</button>`,
    );
  }
  if (ldIssueInstances > 0) {
    actionButtons.push(
      `<button
        type="button"
        class="btn btn-small btn-fix-all-settings"
        id="fix-all-settings-btn"
        ${fixAllDisabled ? "disabled" : ""}
      >${fixAllSettingsBusy ? "Fixing all…" : `Fix all settings (${ldIssueInstances})`}</button>`,
    );
  }
  const summaryActions = actionButtons.length
    ? `<div class="restore-summary-actions">${actionButtons.join("")}</div>`
    : "";
  els.restoreSummaryPanel.innerHTML = `
    <div class="restore-summary-grid restore-summary-grid-wide">
      <div><span class="label">Instances with backups</span><strong>${rows.filter((row) => row.backupAvailable).length}</strong></div>
      <div><span class="label">Need backup pick</span><strong>${unmatched.length}</strong></div>
      <div><span class="label">Manual mappings</span><strong>${manual.length}</strong></div>
      <div><span class="label">Missing in LDPlayer</span><strong>${missing.length}</strong></div>
      <div><span class="label">Recommended restore</span><strong>${troubled.length}</strong></div>
      <div><span class="label">LD settings issues</span><strong>${ldIssueInstances}</strong></div>
      <div><span class="label">APK updates</span><strong>${apkUpdateInstances}</strong></div>
      <div><span class="label">Selected instance updates</span><strong>${selectedApkUpdateInstances}</strong></div>
      <div><span class="label">Instances selected</span><strong>${selectedInstanceCount}</strong></div>
      <div><span class="label">Game update stuck</span><strong>${gameUpdateStuck}</strong></div>
      <div><span class="label">Remote APK</span><strong>${escapeHtml(remoteApkLabel)}</strong></div>
      <div><span class="label">Latest APK cache</span><strong>${escapeHtml(cachedVersion || "—")}</strong></div>
    </div>
    ${summaryActions}`;
}

function renderLdHealthPanel(health, index) {
  if (!health) {
    const loading = emulatorHealthLoading
      ? `<p class="settings-loading">Loading LDPlayer settings…</p>`
      : emulatorHealthLoadError
        ? `<p class="settings-loading error">${escapeHtml(emulatorHealthLoadError)}</p>`
        : `<p class="settings-loading">Open to load settings…</p>`;
    return `
      <details class="ld-health-details" data-health-index="${index}">
        <summary>LDPlayer Settings</summary>
        ${loading}
      </details>`;
  }
  if (health.error) {
    return `
      <details class="ld-health-details">
        <summary class="warn">LDPlayer Settings (unavailable)</summary>
        <p class="settings-loading error">${escapeHtml(health.error)}</p>
      </details>`;
  }

  const issueCount = Number(health.issueCount) || 0;
  const summaryClass = issueCount > 0 ? "warn" : "ok";
  const summaryText =
    issueCount > 0
      ? `LDPlayer Settings (${issueCount} issue${issueCount === 1 ? "" : "s"})`
      : "LDPlayer Settings (OK)";

  const rows = (health.checks || [])
    .map((check) => {
      const tone = check.ok ? "ok" : "bad";
      return `
        <div class="ld-health-row ${tone}">
          <span class="ld-health-label">${escapeHtml(check.label)}</span>
          <span class="ld-health-expected" title="Expected">${escapeHtml(check.expected)}</span>
          <span class="ld-health-actual" title="Current">${escapeHtml(check.actual)}</span>
        </div>`;
    })
    .join("");

  const configNote = health.configPath
    ? `<p class="ld-health-source">Config: <code>${escapeHtml(health.configPath)}</code></p>`
    : "";

  const panelIndex = health.index ?? index;
  const fixDisabled = fixSettingsLocked() || restoreBusy || fixAllSettingsBusy || fixSettingsBusyIndex === panelIndex;
  const fixButton =
    issueCount > 0
      ? `<div class="ld-health-actions">
          <button
            type="button"
            class="btn btn-small btn-fix-settings"
            data-fix-settings-index="${panelIndex}"
            ${fixDisabled ? "disabled" : ""}
          >${fixSettingsBusyIndex === panelIndex ? "Fixing…" : "Fix settings"}</button>
        </div>`
      : "";

  return `
    <details class="ld-health-details" data-health-index="${panelIndex}">
      <summary class="${summaryClass}">${escapeHtml(summaryText)}</summary>
      <div class="ld-health-panel">
        <div class="ld-health-head" aria-hidden="true">
          <span>Setting</span>
          <span>Expected</span>
          <span>Current</span>
        </div>
        <div class="ld-health-table">${rows || '<p class="settings-loading">No comparable settings found.</p>'}</div>
        ${fixButton}
        ${configNote}
      </div>
    </details>`;
}

function renderEmulatorApkPanel(apk, index) {
  if (!apk) {
    const loading = emulatorApkLoading
      ? `<p class="settings-loading">Checking Whiteout APK…</p>`
      : emulatorApkLoadError
        ? `<p class="settings-loading error">${escapeHtml(emulatorApkLoadError)}</p>`
        : `<p class="settings-loading">APK check pending…</p>`;
    return `<div class="emulator-apk-panel">${loading}</div>`;
  }
  if (apk.error) {
    return `<div class="emulator-apk-panel"><p class="settings-loading error">${escapeHtml(apk.error)}</p></div>`;
  }

  const latest = apk.latestVersion || "—";
  let installedText = "—";
  let installedClass = "";
  if (apk.checkState === "not_installed") {
    installedText = "Not installed";
    installedClass = "bad";
  } else if (apk.installedVersion) {
    installedText = apk.installedVersion;
    if (apk.versionConfirmed === false) {
      installedClass = apk.updateAvailable ? "bad" : "warn";
    } else {
      installedClass = apk.updateAvailable ? "bad" : "ok";
    }
  } else if (apk.checkState === "booting") {
    installedText = "Booting…";
    installedClass = "warn";
  } else if (apk.checkState === "offline") {
    installedText = apk.installed ? "Installed (unknown)" : "Not installed";
    installedClass = apk.installed ? "warn" : "bad";
  } else if (apk.checkState === "unavailable") {
    installedText = apk.running ? "Unknown" : "Unavailable";
    installedClass = "warn";
  }

  const panelIndex = apk.index ?? index;
  const showUpdate =
    Boolean(apk.updateAvailable) ||
    Boolean(apk.gameUpdateRequired) ||
    (apk.apkReady && (apk.checkState === "unavailable" || apk.checkState === "offline"));
  const updateDisabled =
    restoreLocked() ||
    restoreBusy ||
    updateAllApksBusy ||
    updateSelectedApksBusy ||
    updateApkBusyIndex === panelIndex ||
    fixAllSettingsBusy ||
    fixSettingsBusyIndex != null ||
    !apk.apkReady ||
    apk.checkState === "booting";
  const unavailableNote =
    apk.checkState === "unavailable" && !apk.running
      ? `<p class="emulator-apk-note">Start the emulator to verify the installed version. You can still update now.</p>`
      : apk.checkState === "offline"
        ? `<p class="emulator-apk-note">Whiteout is installed but the version could not be read without ADB. Start the emulator to compare versions.</p>`
        : apk.checkState === "booting"
          ? `<p class="emulator-apk-note">Emulator is starting — version check will update once Android is ready.</p>`
          : apk.gameUpdateRequired
            ? `<p class="emulator-apk-note warn">Whiteout is showing the in-game update prompt. Sideload the latest APK to clear the reboot loop.</p>`
            : apk.updateAvailable && apk.installedVersion && apk.latestVersion && apk.installedVersion === apk.latestVersion && !apk.versionConfirmed
              ? `<p class="emulator-apk-note warn">Installed version is unconfirmed — start the emulator to verify, or force update if the game still shows an older build.</p>`
            : apk.persistedVersion
              ? `<p class="emulator-apk-note">Installed version from the last restore, provision, or APK update (start emulator to confirm).</p>`
              : "";
  const updateButton = showUpdate
    ? `<button
        type="button"
        class="btn btn-small btn-update-apk"
        data-update-apk-index="${panelIndex}"
        ${updateDisabled ? "disabled" : ""}
      >${updateApkBusyIndex === panelIndex ? "Updating…" : apk.gameUpdateRequired ? "Fix update loop" : apk.updateAvailable ? "Update APK" : "Install APK"}</button>`
    : `<span class="emulator-apk-ok">Up to date</span>`;

  return `
    <div class="emulator-apk-panel" data-apk-index="${panelIndex}">
      <div class="emulator-apk-head" aria-hidden="true">
        <span>Whiteout APK</span>
        <span>Latest</span>
        <span>Installed</span>
      </div>
      <div class="emulator-apk-row">
        <span class="emulator-apk-label">Version</span>
        <span class="emulator-apk-latest">${escapeHtml(latest)}</span>
        <span class="emulator-apk-installed ${installedClass}">${escapeHtml(installedText)}</span>
      </div>
      <div class="emulator-apk-actions">
        ${updateButton}
      </div>
      ${unavailableNote}
    </div>`;
}

function renderBackupSelect(row) {
  const locked =
    restoreLocked() ||
    restoreBusy ||
    row.restoreBusy ||
    backupAssignmentBusyIndex === row.index;
  const autoLabel = row.backupAutoFile
    ? `Auto — ${row.backupAutoFile}`
    : "Auto — no match found";
  const selectedManual = row.backupManualFile || "";
  const usedByIndex = new Map();
  for (const other of restoreRows) {
    const file = other.backupManualFile || (other.backupMatchSource === "manual" ? other.backupFile : null);
    if (file) usedByIndex.set(file, other.index);
  }

  const options = [
    `<option value=""${selectedManual ? "" : " selected"}>${escapeHtml(autoLabel)}</option>`,
  ];
  for (const backup of availableBackups) {
    const selected = selectedManual === backup.filename ? " selected" : "";
    const usedIndex = usedByIndex.get(backup.filename);
    const usedNote =
      usedIndex != null && usedIndex !== row.index ? ` · used by #${usedIndex}` : "";
    options.push(
      `<option value="${escapeHtml(backup.filename)}"${selected}>${escapeHtml(backup.filename)} (${backup.sizeMb} MB)${escapeHtml(usedNote)}</option>`,
    );
  }

  let hint = "Choose a backup file or leave on Auto-match.";
  if (row.backupMatchSource === "manual") {
    hint = "Manual selection saved in monitor config.";
  } else if (row.backupMatchSource === "auto" && row.backupAutoFile) {
    hint = `Auto-matched to ${row.backupAutoFile}. Pick another file to override.`;
  } else if (row.backupMatchSource === "none") {
    hint = "No automatic match — pick a backup file.";
  }

  return `
    <div class="restore-backup-row">
      <label class="account-settings-label" for="restore-backup-${row.index}">Backup file</label>
      <select
        class="setting-select restore-backup-select"
        id="restore-backup-${row.index}"
        data-backup-index="${row.index}"
        ${locked ? "disabled" : ""}
      >${options.join("")}</select>
      <p class="restore-backup-hint">${escapeHtml(hint)}</p>
    </div>`;
}

function renderRestoreInstanceList(rows) {
  if (!els.restoreInstanceList) return;
  if (!rows.length) {
    els.restoreInstanceList.innerHTML =
      `<p class="settings-loading">No emulator backups matched to LDPlayer instances.</p>`;
    return;
  }

  const locked = restoreLocked();
  els.restoreInstanceList.innerHTML = rows
    .map((row) => {
      const reasons = (row.troubleReasons || []).join("; ");
      const accounts = (row.accounts || []).join(", ");
      const disabled = locked || row.restoreBusy || restoreBusy || !row.backupAvailable;
      const tone = row.troubled ? "troubled" : "";
      const missingBadge = row.missing
        ? '<span class="badge state-badge bad">Missing in LDPlayer</span>'
        : "";
      const restoreLabel = row.restoreBusy
        ? "Restoring…"
        : row.missing
          ? "Recreate & restore"
          : "Restore emulator";
      const showProgress = row.restoreBusy || restoreProgressByIndex[row.index];
      return `
        <article class="restore-instance-card ${tone}${disabled ? " is-disabled" : ""}${row.missing ? " missing-instance" : ""}">
          <div class="restore-instance-head">
            <div>
              <h3>${escapeHtml(row.ldName)} <span class="restore-instance-index">#${row.index}</span></h3>
              <p class="restore-instance-meta">${escapeHtml(accounts || "No mapped accounts")}</p>
            </div>
            <div class="restore-instance-badges">
              ${row.troubled && !row.missing ? '<span class="badge state-badge warn">Recommended</span>' : ""}
              ${missingBadge}
            </div>
          </div>
          <dl class="restore-instance-details">
            <div><dt>Size</dt><dd>${row.backupSizeMb ? `${row.backupSizeMb} MB` : "—"}</dd></div>
            <div><dt>Issue</dt><dd>${escapeHtml(reasons || "—")}</dd></div>
          </dl>
          ${renderBackupSelect(row)}
          ${renderEmulatorApkPanel(emulatorApkByIndex[row.index], row.index)}
          ${renderLdHealthPanel(emulatorHealthByIndex[row.index], row.index)}
          ${showProgress ? renderRestoreProgressPanel(row.index) : ""}
          <button
            class="btn btn-restore"
            type="button"
            data-restore-index="${row.index}"
            ${disabled ? "disabled" : ""}
          >${restoreLabel}</button>
        </article>`;
    })
    .join("");
}

async function loadEmulatorHealthForRows(rows) {
  emulatorHealthByIndex = {};
  emulatorHealthLoadError = "";
  if (!rows.length) return;

  emulatorHealthLoading = true;
  const indexes = rows.map((row) => row.index).join(",");
  try {
    const healthResponse = await fetch(
      `/api/emulators/health?indexes=${encodeURIComponent(indexes)}`,
      { cache: "no-store" },
    );
    const healthPayload = await healthResponse.json().catch(() => ({}));
    if (!healthResponse.ok) {
      const detail = healthPayload.detail || healthPayload.message || `HTTP ${healthResponse.status}`;
      emulatorHealthLoadError =
        typeof detail === "string" ? detail : "Could not load LDPlayer settings.";
      return;
    }
    for (const healthRow of healthPayload.instances || []) {
      if (healthRow?.index != null) {
        emulatorHealthByIndex[Number(healthRow.index)] = healthRow;
      }
    }
  } catch (error) {
    emulatorHealthLoadError = error.message || "Could not load LDPlayer settings.";
  } finally {
    emulatorHealthLoading = false;
  }
}

async function loadEmulatorApkForIndexes(indexes, { merge = false, force = false } = {}) {
  const list = [...new Set(indexes.map((value) => Number(value)).filter((value) => !Number.isNaN(value)))];
  if (!list.length) return;

  if (!merge) {
    emulatorApkByIndex = {};
  }
  emulatorApkLoadError = "";
  emulatorApkLoading = true;
  try {
    const query = new URLSearchParams({ indexes: list.join(",") });
    if (force) query.set("force", "1");
    query.set("check_game_update", "1");
    const response = await fetch(`/api/emulators/apk?${query.toString()}`, {
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      emulatorApkLoadError = typeof detail === "string" ? detail : "Could not check Whiteout APK versions.";
      return;
    }
    for (const apkRow of payload.instances || []) {
      if (apkRow?.index != null) {
        emulatorApkByIndex[Number(apkRow.index)] = apkRow;
      }
    }
  } catch (error) {
    emulatorApkLoadError = error.message || "Could not check Whiteout APK versions.";
  } finally {
    emulatorApkLoading = false;
    scheduleEmulatorApkSync();
  }
}

async function loadEmulatorApkForRows(rows, { force = false } = {}) {
  if (!rows.length) {
    emulatorApkByIndex = {};
    clearEmulatorApkPoll();
    return;
  }
  await loadEmulatorApkForIndexes(
    rows.map((row) => row.index),
    { merge: false, force },
  );
}

async function loadEmulatorHealthForIndex(index) {
  if (emulatorHealthByIndex[index]) return emulatorHealthByIndex[index];
  const response = await fetch(`/api/emulators/${index}/health`, { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || payload.message || `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : "Could not load LDPlayer settings.");
  }
  const health = payload.health || null;
  if (health) {
    emulatorHealthByIndex[Number(index)] = health;
  }
  return health;
}

async function refreshRestoreTabAfterJob() {
  try {
    const [emulatorsResponse, activityResponse] = await Promise.all([
      fetch("/api/emulators", { cache: "no-store" }),
      fetch("/api/bot-activity", { cache: "no-store" }),
    ]);
    const emulatorsPayload = await emulatorsResponse.json().catch(() => ({}));
    const activityPayload = await activityResponse.json().catch(() => ({}));

    if (activityResponse.ok) {
      applyBotActivityFromServer(activityPayload);
    }

    if (!emulatorsResponse.ok) {
      throw new Error(emulatorsPayload.detail || `HTTP ${emulatorsResponse.status}`);
    }

    const emulatorSummary = emulatorsPayload.summary || {};
    renderRestorePathPanel(emulatorSummary);
    availableBackups = emulatorsPayload.backups || [];
    const accountMeta = window.GnBotsRestore
      ? window.GnBotsRestore.buildAccountMetaByInstance(dashboardAccounts)
      : new Map();
    restoreRows = window.GnBotsRestore
      ? window.GnBotsRestore.mergeRestoreRowsFromEmulators(
          emulatorsPayload.instances || [],
          accountMeta,
        )
      : [];

    await Promise.all([
      loadEmulatorHealthForRows(restoreRows),
      loadEmulatorApkForRows(restoreRows, { force: true }),
    ]);

    applyRestoreLockState();
    renderRestoreSummary(restoreRows);
    renderRestoreInstanceList(restoreRows);
    setRestorePageStatus("Restore finished — refreshed emulator health and APK status.", "ok");
    els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    await loadRestoreTab();
  }
}

async function loadRestoreTab({ forceApk = false } = {}) {
  await loadCapabilities();
  setRestorePageStatus("Loading emulator restore options…", "pending");
  try {
    const [dashboardResponse, emulatorsResponse, monitorResponse] = await Promise.all([
      fetch("/api/dashboard", { cache: "no-store" }),
      fetch("/api/emulators", { cache: "no-store" }),
      fetch("/api/monitor-config", { cache: "no-store" }),
    ]);
    const payload = await dashboardResponse.json().catch(() => ({}));
    const emulatorsPayload = await emulatorsResponse.json().catch(() => ({}));
    const monitorPayload = await monitorResponse.json().catch(() => ({}));

    if (!dashboardResponse.ok) {
      throw new Error(payload.detail || `HTTP ${dashboardResponse.status}`);
    }

    if (monitorResponse.ok) {
      currentMonitorConfig = monitorPayload.config || currentMonitorConfig;
      restoreBackupsDir = String(currentMonitorConfig?.ldplayer_backups_dir || "").trim();
    }

    const emulatorSummary = emulatorsPayload.summary || {};
    renderRestorePathPanel(emulatorSummary);

    botActive = Boolean(payload.botActive);
    botState = payload.botState || botState;
    gnbotsOnline = payload.gnbotsOnline !== false;
    setGnbotsStatus(gnbotsOnline, { writable: !botActive });
    dashboardAccounts = payload.accounts || [];
    availableBackups = emulatorsPayload.backups || [];
    const accountMeta = window.GnBotsRestore
      ? window.GnBotsRestore.buildAccountMetaByInstance(dashboardAccounts)
      : new Map();
    restoreRows = window.GnBotsRestore
      ? window.GnBotsRestore.mergeRestoreRowsFromEmulators(
          emulatorsPayload.instances || [],
          accountMeta,
        )
      : [];

    await Promise.all([
      loadEmulatorHealthForRows(restoreRows),
      loadEmulatorApkForRows(restoreRows, { force: forceApk }),
      loadApkUpdateSelection(),
    ]);

    applyRestoreLockState();
    renderRestoreSummary(restoreRows);
    renderRestoreInstanceList(restoreRows);
    void refreshRemoteApkStatusQuiet();

    const hasActiveRestore = restoreRows.some((row) => row.restoreBusy);
    void resumeActiveRestorePolling(restoreRows);
    let hasActiveApkJob = Boolean(
      updateAllApksBusy || updateSelectedApksBusy || forceUpdateSelectedApksBusy || updateApkBusyIndex != null,
    );
    if (!hasActiveApkJob && window.GnBotsRestore) {
      try {
        const activeApk = await window.GnBotsRestore.findActiveApkUpdateJob();
        hasActiveApkJob = Boolean(activeApk?.id);
      } catch {
        hasActiveApkJob = false;
      }
    }
    void resumeActiveApkUpdatePolling();

    if (restoreLocked()) {
      setRestorePageStatus("Restore is disabled while the bot is running. Stop the bot to continue.", "warn");
    } else if (!restoreRows.length) {
      setRestorePageStatus("No backups are mapped to LDPlayer instances.", "warn");
    } else if (!hasActiveRestore && !hasActiveApkJob) {
      const troubled = restoreRows.filter((row) => row.troubled).length;
      const ldIssues = Object.values(emulatorHealthByIndex).filter(
        (health) => health && !health.error && Number(health.issueCount) > 0,
      ).length;
      const apkUpdates = Object.values(emulatorApkByIndex).filter((apk) => apkNeedsInstallOrUpdate(apk)).length;
      const bootingApks = Object.values(emulatorApkByIndex).filter((apk) => apk?.checkState === "booting").length;
      let message =
        troubled > 0
          ? `${troubled} instance${troubled === 1 ? "" : "s"} recommended for restore.`
          : "Select an instance to restore from backup.";
      if (emulatorHealthLoadError) {
        message = `${message} LD settings: ${emulatorHealthLoadError}`;
      } else if (ldIssues > 0) {
        message = `${message} ${ldIssues} instance${ldIssues === 1 ? "" : "s"} have LD setting mismatches.`;
      }
      if (emulatorApkLoadError) {
        message = `${message} APK: ${emulatorApkLoadError}`;
      } else if (bootingApks > 0) {
        message = `${message} ${bootingApks} emulator${bootingApks === 1 ? "" : "s"} still booting — APK check will refresh automatically.`;
      } else if (apkUpdates > 0) {
        message = `${message} ${apkUpdates} instance${apkUpdates === 1 ? "" : "s"} need APK updates.`;
      }
      setRestorePageStatus(
        message,
        troubled || ldIssues || apkUpdates || emulatorHealthLoadError || emulatorApkLoadError ? "warn" : "ok",
      );
    }
    els.lastUpdated.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    restoreRows = [];
    if (els.restoreInstanceList) {
      els.restoreInstanceList.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load restore options.")}</p>`;
    }
    setRestorePageStatus("");
  }
}

async function saveBackupAssignment(index, backupFile) {
  if (restoreLocked()) {
    setRestorePageStatus("Stop the bot before changing backup assignments.", "warn");
    return;
  }

  backupAssignmentBusyIndex = index;
  applyRestoreLockState();
  renderRestoreInstanceList(restoreRows);
  setRestorePageStatus(
    backupFile ? `Saving backup assignment for instance ${index}…` : `Resetting instance ${index} to auto-match…`,
    "pending",
  );

  try {
    const response = await fetch(`/api/emulators/${index}/backup-assignment`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backupFile: backupFile || null }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail ?? body.message ?? `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    const row = restoreRows.find((entry) => entry.index === index);
    const inst = body.instance || {};
    if (row && window.GnBotsRestore) {
      window.GnBotsRestore.applyEmulatorInstanceFields?.(row, inst);
    }
    setRestorePageStatus(
      backupFile ? `Instance ${index} will use ${backupFile}.` : `Instance ${index} set to auto-match.`,
      "ok",
    );
    await loadRestoreTab();
  } catch (error) {
    setRestorePageStatus(error.message || "Could not save backup assignment.", "error");
    await loadRestoreTab();
  } finally {
    backupAssignmentBusyIndex = null;
    applyRestoreLockState();
  }
}

async function runRestoreForIndex(index) {
  if (restoreLocked()) {
    setRestorePageStatus("Stop the bot before restoring emulators.", "warn");
    return;
  }

  const row = restoreRows.find((entry) => entry.index === index);
  if (!row || !window.GnBotsRestore) return;
  let confirmMessage = window.GnBotsRestore.restoreConfirmMessageForRow(row, { botActive });
  if (elevationLocked("restore-health-settings")) {
    confirmMessage +=
      "\n\nWarning: Sentinel is not elevated — post-restore health settings may not be applied.";
  }
  if (!window.confirm(confirmMessage)) return;

  restoreBusy = true;
  activeRestorePollToken += 1;
  applyRestoreLockState();
  renderRestoreInstanceList(restoreRows);
  setRestorePageStatus(`Starting restore for ${row.ldName}…`, "pending", 5);

  try {
    const job = await window.GnBotsRestore.startInstanceRestore(index, {
      onStatus: (jobStatus) => {
        updateRestoreJobProgress(index, jobStatus);
      },
    });
    const warnings = job.warnings || [];
    if (warnings.length) {
      setRestorePageStatus(
        `Restore finished for ${row.ldName} with ${warnings.length} warning(s): ${warnings[0]}`,
        "warn",
        100,
      );
    } else {
      setRestorePageStatus(`Restore completed for ${row.ldName}.`, "ok", 100);
    }
    delete restoreProgressByIndex[index];
    await loadRestoreTab({ forceApk: true });
  } catch (error) {
    setRestorePageStatus(error.message || "Restore failed.", "error");
    delete restoreProgressByIndex[index];
    await loadRestoreTab({ forceApk: true });
  } finally {
    restoreBusy = false;
    applyRestoreLockState();
  }
}

async function fixSettingsForIndex(index) {
  if (fixSettingsLocked()) {
    if (restoreLocked()) {
      setRestorePageStatus("Stop the bot before fixing emulator settings.", "warn");
    } else {
      setRestorePageStatus(
        capability("fix-ldplayer-settings")?.reason ||
          "Fix settings requires Sentinel running as Administrator.",
        "warn",
      );
    }
    return;
  }

  const row = restoreRows.find((entry) => entry.index === index);
  if (!row) return;

  const accountName = (row.accounts || [])[0] || "";
  const label = row.ldName || `instance ${index}`;
  if (
    !window.confirm(
      [
        `Apply GnBots health settings to ${label} (#${index})?`,
        accountName ? `Account: ${accountName}` : "",
        "",
        "The emulator will be stopped briefly while settings are applied.",
      ]
        .filter(Boolean)
        .join("\n"),
    )
  ) {
    return;
  }

  fixSettingsBusyIndex = index;
  applyRestoreLockState();
  renderRestoreInstanceList(restoreRows);
  setRestorePageStatus(`Fixing LDPlayer settings for ${label}…`, "pending");

  try {
    const query = accountName ? `?target_name=${encodeURIComponent(accountName)}` : "";
    const response = await fetch(`/api/emulators/${index}/fix-settings${query}`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : "Could not fix LDPlayer settings.");
    }
    if (payload.health) {
      emulatorHealthByIndex[Number(index)] = payload.health;
    }
    await refreshEmulatorApkRows([index]);
    const remaining = Number(payload.health?.issueCount) || 0;
    const hasWarnings = Array.isArray(payload.warnings) && payload.warnings.length > 0;
    setRestorePageStatus(
      payload.message || (remaining ? `Fixed with ${remaining} issue(s) remaining.` : "Settings fixed."),
      remaining || hasWarnings ? "warn" : "ok",
    );
  } catch (error) {
    setRestorePageStatus(error.message || "Failed to fix LDPlayer settings.", "error");
  } finally {
    fixSettingsBusyIndex = null;
    applyRestoreLockState();
    renderRestoreSummary(restoreRows);
    renderRestoreInstanceList(restoreRows);
  }
}

function indexesWithLdSettingIssues() {
  return Object.entries(emulatorHealthByIndex)
    .filter(([, health]) => health && !health.error && Number(health.issueCount) > 0)
    .map(([index]) => Number(index))
    .filter((index) => !Number.isNaN(index))
    .sort((a, b) => a - b);
}

async function restoreAllTroubled() {
  if (restoreLocked()) {
    setRestorePageStatus("Stop the bot before restoring emulators.", "warn");
    return;
  }

  const indexes = restoreRows
    .filter((row) => row.troubled && row.backupAvailable)
    .map((row) => row.index)
    .sort((a, b) => a - b);
  if (!indexes.length) {
    setRestorePageStatus("No recommended restore instances with backups.", "ok");
    return;
  }

  if (
    !window.confirm(
      [
        `Queue restore for ${indexes.length} troubled instance${indexes.length === 1 ? "" : "s"}?`,
        `Instances: ${indexes.map((index) => `#${index}`).join(", ")}`,
        "",
        "Restores run one instance at a time (serialized). Leave emulators alone during resource-pack download.",
      ].join("\n"),
    )
  ) {
    return;
  }

  restoreAllBusy = true;
  applyRestoreLockState();
  renderRestoreSummary(restoreRows);
  renderRestoreInstanceList(restoreRows);
  setRestorePageStatus(`Queueing restore for ${indexes.length} instance(s)…`, "pending");

  try {
    const response = await fetch(
      `/api/emulators/restore-all?indexes=${encodeURIComponent(indexes.join(","))}`,
      { method: "POST" },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : "Could not queue restore jobs.");
    }
    setRestorePageStatus(payload.message || `Queued ${payload.queued || 0} restore job(s).`, "ok");
    await loadRestoreTab();
  } catch (error) {
    setRestorePageStatus(error.message || "Failed to queue restore jobs.", "error");
  } finally {
    restoreAllBusy = false;
    applyRestoreLockState();
    renderRestoreSummary(restoreRows);
    renderRestoreInstanceList(restoreRows);
  }
}

async function fixAllSettings() {
  if (fixSettingsLocked()) {
    if (restoreLocked()) {
      setRestorePageStatus("Stop the bot before fixing emulator settings.", "warn");
    } else {
      setRestorePageStatus(
        capability("fix-ldplayer-settings")?.reason ||
          "Fix settings requires Sentinel running as Administrator.",
        "warn",
      );
    }
    return;
  }

  const indexes = indexesWithLdSettingIssues();
  if (!indexes.length) {
    setRestorePageStatus("No LDPlayer setting issues to fix.", "ok");
    return;
  }

  if (
    !window.confirm(
      [
        `Apply GnBots health settings to ${indexes.length} LDPlayer instance${indexes.length === 1 ? "" : "s"}?`,
        `Instances: ${indexes.map((index) => `#${index}`).join(", ")}`,
        "",
        "Each emulator will be stopped briefly while settings are applied.",
      ].join("\n"),
    )
  ) {
    return;
  }

  fixAllSettingsBusy = true;
  applyRestoreLockState();
  renderRestoreSummary(restoreRows);
  renderRestoreInstanceList(restoreRows);
  setRestorePageStatus(`Fixing LDPlayer settings on ${indexes.length} instance(s)…`, "pending");

  try {
    const response = await fetch(
      `/api/emulators/fix-settings?indexes=${encodeURIComponent(indexes.join(","))}`,
      { method: "POST" },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : "Could not fix LDPlayer settings.");
    }
    for (const result of payload.results || []) {
      if (result?.health && result.index != null) {
        emulatorHealthByIndex[Number(result.index)] = result.health;
      }
    }
    renderRestoreSummary(restoreRows);
    renderRestoreInstanceList(restoreRows);
    const remaining = Number(payload.remainingIssues) || 0;
    const failed = Number(payload.failed) || 0;
    const hasWarnings = Array.isArray(payload.warnings) && payload.warnings.length > 0;
    setRestorePageStatus(
      payload.message || (failed ? `Fixed with ${failed} failure(s).` : "All settings fixed."),
      remaining || failed || hasWarnings ? "warn" : "ok",
    );
  } catch (error) {
    setRestorePageStatus(error.message || "Failed to fix LDPlayer settings.", "error");
  } finally {
    fixAllSettingsBusy = false;
    applyRestoreLockState();
    renderRestoreSummary(restoreRows);
    renderRestoreInstanceList(restoreRows);
  }
}

function indexesWithApkUpdates() {
  return Object.entries(emulatorApkByIndex)
    .filter(([, apk]) => apkNeedsInstallOrUpdate(apk))
    .map(([index]) => Number(index))
    .filter((index) => !Number.isNaN(index))
    .sort((a, b) => a - b);
}

function applyApkJobResultToUi(job) {
  for (const result of job?.results || []) {
    if (result?.apk && result.index != null) {
      emulatorApkByIndex[Number(result.index)] = result.apk;
    }
  }
  if (job?.localVersion || job?.cacheVersion) {
    remoteApkStatus = {
      ...(remoteApkStatus || {}),
      localVersion: job.localVersion || job.cacheVersion,
      apkReady: true,
    };
  }
}

function markApkUpdateBusyFromJob(job) {
  const indexes = Array.isArray(job?.indexes) ? job.indexes.map(Number) : [];
  const current = job?.currentIndex != null ? Number(job.currentIndex) : null;
  updateAllApksBusy = true;
  updateSelectedApksBusy = true;
  forceUpdateSelectedApksBusy = Boolean(job?.force);
  updateApkBusyIndex = current != null && !Number.isNaN(current) ? current : indexes[0] ?? null;
  applyRestoreLockState();
  renderRestoreSummary(restoreRows);
  renderRestoreInstanceList(restoreRows);
  renderApkAccountSelection();
}

function clearApkUpdateBusyFlags() {
  updateApkBusyIndex = null;
  updateAllApksBusy = false;
  updateSelectedApksBusy = false;
  forceUpdateSelectedApksBusy = false;
  applyRestoreLockState();
  renderRestoreSummary(restoreRows);
  renderRestoreInstanceList(restoreRows);
  renderApkAccountSelection();
}

function updateApkJobProgress(job) {
  const formatted = window.GnBotsRestore
    ? window.GnBotsRestore.formatApkUpdateJobStatus(job)
    : { progress: Number(job?.progress) || 10, message: job?.message || "Updating APKs…" };
  if (job?.currentIndex != null) {
    updateApkBusyIndex = Number(job.currentIndex);
  }
  setRestorePageStatus(formatted.message, "pending", formatted.progress);
  renderRestoreSummary(restoreRows);
  renderRestoreInstanceList(restoreRows);
}

async function followApkUpdateJob(job, { busyMode = "all" } = {}) {
  if (!job?.id || !window.GnBotsRestore) {
    throw new Error("APK update started but no job id was returned.");
  }
  const pollToken = ++activeApkUpdatePollToken;
  if (busyMode === "single" && Array.isArray(job.indexes) && job.indexes.length === 1) {
    updateApkBusyIndex = Number(job.indexes[0]);
  } else if (busyMode === "force") {
    forceUpdateSelectedApksBusy = true;
    updateSelectedApksBusy = true;
  } else if (busyMode === "selected") {
    updateSelectedApksBusy = true;
  } else {
    updateAllApksBusy = true;
  }
  markApkUpdateBusyFromJob(job);
  updateApkJobProgress(job);

  try {
    const finished = await window.GnBotsRestore.pollApkUpdateJob(job.id, {
      onStatus: (liveJob) => {
        if (pollToken !== activeApkUpdatePollToken) return;
        updateApkJobProgress(liveJob);
      },
    });
    if (pollToken !== activeApkUpdatePollToken) return finished;
    applyApkJobResultToUi(finished);
    await loadApkUpdateSelection();
    await loadEmulatorApkForRows(restoreRows, { force: true });
    const failed = Number(finished.failed) || 0;
    setRestorePageStatus(
      finished.message || (failed ? `Updated with ${failed} failure(s).` : "APK update complete."),
      failed ? "warn" : "ok",
      100,
    );
    return finished;
  } finally {
    if (pollToken === activeApkUpdatePollToken) {
      clearApkUpdateBusyFlags();
    }
  }
}

async function resumeActiveApkUpdatePolling() {
  if (!window.GnBotsRestore) return;
  const active = await window.GnBotsRestore.findActiveApkUpdateJob();
  let jobId = active?.id || null;
  if (!jobId) {
    try {
      jobId = sessionStorage.getItem("sentinelApkUpdateJobId");
    } catch {
      jobId = null;
    }
  }
  if (!jobId) return;

  const pollToken = ++activeApkUpdatePollToken;
  markApkUpdateBusyFromJob(active || { id: jobId, indexes: [], status: "updating", progress: 20 });
  setRestorePageStatus("Resuming APK update in progress…", "pending", Number(active?.progress) || 20);

  try {
    await window.GnBotsRestore.resumeApkUpdateJobPolling({
      jobId,
      onStatus: (job) => {
        if (pollToken !== activeApkUpdatePollToken) return;
        updateApkJobProgress(job);
      },
      onComplete: async (job) => {
        if (pollToken !== activeApkUpdatePollToken) return;
        applyApkJobResultToUi(job);
        await loadApkUpdateSelection();
        await loadEmulatorApkForRows(restoreRows, { force: true });
        const failed = Number(job.failed) || 0;
        setRestorePageStatus(
          job.message || (failed ? `Updated with ${failed} failure(s).` : "APK update complete."),
          failed ? "warn" : "ok",
          100,
        );
      },
      onError: async (error) => {
        if (pollToken !== activeApkUpdatePollToken) return;
        setRestorePageStatus(error.message || "APK update failed.", "error");
      },
    });
  } catch {
    // onError already surfaced the message
  } finally {
    if (pollToken === activeApkUpdatePollToken) {
      clearApkUpdateBusyFlags();
    }
  }
}

async function updateApkForIndex(index) {
  if (restoreLocked()) {
    setRestorePageStatus("Stop the bot before updating emulator APKs.", "warn");
    return;
  }

  const row = restoreRows.find((entry) => entry.index === index);
  const label = row?.ldName || `instance ${index}`;
  const apk = emulatorApkByIndex[index];
  const latest = apk?.latestVersion || row?.apkVersion || "latest";
  if (
    !window.confirm(
      [
        `Update Whiteout Survival on ${label} (#${index})?`,
        `Latest cached version: ${latest}`,
        "",
        "The emulator will be started if needed. This can take several minutes.",
        "You can refresh this page — the update keeps running in the background.",
      ].join("\n"),
    )
  ) {
    return;
  }

  setRestorePageStatus(`Queuing Whiteout Survival update on ${label}…`, "pending", 5);

  try {
    const response = await fetch(`/api/emulators/${index}/update-apk`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : "Could not update Whiteout APK.");
    }
    const job = payload.job || payload;
    await followApkUpdateJob(job, { busyMode: "single" });
  } catch (error) {
    clearApkUpdateBusyFlags();
    setRestorePageStatus(error.message || "Failed to update Whiteout APK.", "error");
  }
}

async function refreshRemoteApkStatusQuiet() {
  try {
    const response = await fetch("/api/emulators/apk/check", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (response.ok) {
      remoteApkStatus = payload;
      renderRestoreSummary(restoreRows);
    }
  } catch {
    // ignore background remote APK check failures
  }
}

async function queueSelectedApkUpdate({ skipConfirm = false, force = false } = {}) {
  if (restoreLocked()) {
    setRestorePageStatus("Stop the bot before updating emulator APKs.", "warn");
    return false;
  }

  const indexes = selectedInstanceIndexes();
  if (!indexes.length) {
    setRestorePageStatus("Select at least one emulator instance to update.", "warn");
    return false;
  }

  const outdatedIndexes = indexesWithApkUpdatesForSelectedInstances();
  const targetIndexes = force ? indexes : outdatedIndexes.length ? outdatedIndexes : indexes;

  if (
    !skipConfirm &&
    !window.confirm(
      [
        force
          ? `Force reinstall Whiteout Survival on ${indexes.length} selected instance${indexes.length === 1 ? "" : "s"}?`
          : `Update Whiteout Survival on ${indexes.length} selected emulator instance${indexes.length === 1 ? "" : "s"}?`,
        `Instances: ${targetIndexes.map((index) => `#${index}`).join(", ")}`,
        "",
        force
          ? "This bypasses version checks and reinstalls from the APK cache."
          : outdatedIndexes.length
            ? `Only instances needing an update will be touched (${outdatedIndexes.length}).`
            : "All selected instances will be checked and updated if needed.",
        "Each instance update applies to every account on that emulator.",
        "Each emulator will be started if needed. This can take several minutes per instance.",
        "You can refresh this page — progress continues in the background.",
      ].join("\n"),
    )
  ) {
    return false;
  }

  setRestorePageStatus(
    `Queuing Whiteout Survival ${force ? "force " : ""}update on ${targetIndexes.length} instance(s)…`,
    "pending",
    5,
  );

  const query = force
    ? `/api/emulators/update-apk?scope=selected&indexes=${encodeURIComponent(indexes.join(","))}&force=1&only_outdated=0&check_game_update=0`
    : `/api/emulators/update-apk?scope=selected&indexes=${encodeURIComponent(indexes.join(","))}&only_outdated=1&check_game_update=1`;

  try {
    const response = await fetch(query, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      throw new Error(
        typeof detail === "string"
          ? detail
          : force
            ? "Could not force update selected instance APKs."
            : "Could not update selected instance APKs.",
      );
    }
    await followApkUpdateJob(payload.job || payload, { busyMode: force ? "force" : "selected" });
    return true;
  } catch (error) {
    clearApkUpdateBusyFlags();
    setRestorePageStatus(
      error.message || (force ? "Failed to force update selected instance APKs." : "Failed to update selected instance APKs."),
      "error",
    );
    return false;
  }
}

async function checkRemoteApk({ sync = false } = {}) {
  checkRemoteApkBusy = true;
  renderRestoreSummary(restoreRows);
  setRestorePageStatus(sync ? "Downloading latest Whiteout APK…" : "Checking remote Whiteout APK…", "pending");
  try {
    const query = sync ? "?sync=1" : "";
    const response = await fetch(`/api/emulators/apk/check${query}`, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : "Could not check remote APK.");
    }
    remoteApkStatus = payload;
    if (sync) {
      await loadEmulatorApkForRows(restoreRows, { force: true });
    }
    renderRestoreSummary(restoreRows);
    renderRestoreInstanceList(restoreRows);
    if (sync && payload.downloaded) {
      const versionLabel = payload.localVersion || payload.remoteVersion || "";
      // Cache sync ≠ emulator install. Push to selected instances when possible.
      if (restoreLocked()) {
        setRestorePageStatus(
          `Downloaded ${versionLabel} into the APK cache only. Stop the bot, then Update selected instances to install on emulators.`.trim(),
          "warn",
        );
      } else if (!selectedInstanceIndexes().length) {
        setRestorePageStatus(
          `Downloaded ${versionLabel} into the APK cache only. Select emulators and click Update selected instances to install.`.trim(),
          "warn",
        );
      } else {
        checkRemoteApkBusy = false;
        setRestorePageStatus(
          `Downloaded ${versionLabel} into cache. Installing on selected emulators…`.trim(),
          "pending",
        );
        await queueSelectedApkUpdate({ skipConfirm: true, force: false });
        return;
      }
    } else if (payload.localAheadOfRemote) {
      setRestorePageStatus(
        `Local split APKs are ${payload.localVersion || "newer"}; game.zip is still ${payload.remoteVersion || "older"}. Use Update selected instances — do not download the zip.`,
        "ok",
      );
    } else if (payload.updateAvailable) {
      setRestorePageStatus("A newer Whiteout game.zip is available on the GnBots server.", "warn");
    } else {
      const thirdPartyError = payload.thirdParty?.error;
      setRestorePageStatus(
        thirdPartyError
          ? `Local APK cache is ${payload.localVersion || "ready"}; third-party check failed: ${thirdPartyError}`
          : payload.localVersion
            ? `Local APK cache is ${payload.localVersion}${payload.remoteVersion ? `; remote is ${payload.remoteVersion}` : ""}. Download updates the cache only — use Update selected instances to install on emulators.`
            : "Local Whiteout APK cache matches the remote source.",
        thirdPartyError ? "warn" : "ok",
      );
    }
  } catch (error) {
    setRestorePageStatus(error.message || "Failed to check remote APK.", "error");
  } finally {
    checkRemoteApkBusy = false;
    renderRestoreSummary(restoreRows);
  }
}

async function updateSelectedInstanceApks() {
  await queueSelectedApkUpdate({ skipConfirm: false, force: false });
}

async function forceUpdateSelectedApks() {
  await queueSelectedApkUpdate({ skipConfirm: false, force: true });
}

async function updateAllApks() {
  if (restoreLocked()) {
    setRestorePageStatus("Stop the bot before updating emulator APKs.", "warn");
    return;
  }

  const indexes = indexesWithApkUpdates();
  if (!indexes.length) {
    setRestorePageStatus("No Whiteout APK updates needed.", "ok");
    return;
  }

  if (
    !window.confirm(
      [
        `Update Whiteout Survival on ${indexes.length} emulator instance${indexes.length === 1 ? "" : "s"}?`,
        `Instances: ${indexes.map((index) => `#${index}`).join(", ")}`,
        "",
        "Each emulator will be started if needed. This can take several minutes per instance.",
        "You can refresh this page — progress continues in the background.",
      ].join("\n"),
    )
  ) {
    return;
  }

  setRestorePageStatus(`Queuing Whiteout Survival update on ${indexes.length} instance(s)…`, "pending", 5);

  try {
    const response = await fetch(
      `/api/emulators/update-apk?indexes=${encodeURIComponent(indexes.join(","))}`,
      { method: "POST" },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail || payload.message || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : "Could not update emulator APKs.");
    }
    await followApkUpdateJob(payload.job || payload, { busyMode: "all" });
  } catch (error) {
    clearApkUpdateBusyFlags();
    setRestorePageStatus(error.message || "Failed to update emulator APKs.", "error");
  }
}

function setActiveSettingsTab(tabId) {
  if (tabId !== "restore") {
    clearEmulatorApkPoll();
  }
  if (tabId !== "provision") {
    clearProvisionPoll();
  }
  if (!SETTINGS_ACTIVITY_TABS.has(tabId)) {
    clearSettingsActivityPoll();
  }
  activeSettingsTab = tabId;
  els.settingsTabs?.forEach((button) => {
    const active = button.dataset.tab === tabId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  els.tabBot?.classList.toggle("hidden", tabId !== "bot");
  els.tabAccounts?.classList.toggle("hidden", tabId !== "accounts");
  els.tabNames?.classList.toggle("hidden", tabId !== "names");
  els.tabBulk?.classList.toggle("hidden", tabId !== "bulk");
  els.tabProvision?.classList.toggle("hidden", tabId !== "provision");
  els.tabRestore?.classList.toggle("hidden", tabId !== "restore");
  els.tabAutomation?.classList.toggle("hidden", tabId !== "automation");
  els.tabMonitor?.classList.toggle("hidden", tabId !== "monitor");
  if (els.settingsSubtitle) {
    if (tabId === "accounts") {
      els.settingsSubtitle.innerHTML =
        "Per-account Action Editor settings, templates, and schedule rules from the active profile";
    } else if (tabId === "names") {
      els.settingsSubtitle.innerHTML =
        "Bulk edit switch account names for every profile account at once";
    } else if (tabId === "bulk") {
      els.settingsSubtitle.innerHTML =
        "Change one action setting across selected profile accounts";
    } else if (tabId === "provision") {
      els.settingsSubtitle.innerHTML =
        "Create a new LDPlayer instance, install Whiteout Survival, and add a GnBots account";
    } else if (tabId === "restore") {
      els.settingsSubtitle.innerHTML = "Restore LDPlayer backups and reinstall Whiteout Survival";
    } else if (tabId === "automation") {
      els.settingsSubtitle.innerHTML =
        "Background automation, common-issue reports, and fix suggestions";
    } else if (tabId === "monitor") {
      els.settingsSubtitle.innerHTML = "Sentinel and watcher options from <code>monitor/config.json</code>";
    } else {
      els.settingsSubtitle.innerHTML =
        'Remote configuration via the GnBots <code>/settings</code> API';
    }
  }
  if (tabId === "accounts" && !profileAccounts.length) {
    loadProfileAccounts();
  }
  if (tabId === "names") {
    loadAccountNamesTab();
  }
  if (tabId === "bulk") {
    loadBulkActionsTab();
  }
  if (tabId === "provision") {
    loadProvisionTab();
  }
  if (tabId === "restore") {
    loadRestoreTab();
  }
  if (tabId === "automation") {
    loadAutomationTab();
  }
  if (tabId === "monitor" && !monitorGroups.length) {
    loadMonitorConfig();
  }
  if (tabId === "monitor") {
    loadUpdateStatus();
  }
  scheduleSettingsActivityPoll();
}

function renderAccountSelectOptions() {
  if (!els.accountSelect) return;
  if (!profileAccounts.length) {
    els.accountSelect.innerHTML = `<option value="">No accounts in profile</option>`;
    els.accountSelect.disabled = true;
    return;
  }

  const options = profileAccounts
    .map((account) => {
      const suffix = account.active ? "" : " · disabled";
      return `<option value="${escapeHtml(account.id)}">${escapeHtml(account.name)} (${account.instanceId})${suffix}</option>`;
    })
    .join("");
  els.accountSelect.innerHTML = options;
  els.accountSelect.disabled = false;

  const stillValid = profileAccounts.some((account) => account.id === selectedAccountId);
  if (!stillValid) {
    selectedAccountId = profileAccounts[0]?.id || "";
  }
  els.accountSelect.value = selectedAccountId;
}

function accountActionsLocked() {
  return !accountActionsWritable;
}

function updateAccountLockedBanner() {
  const banner = els.accountLockedBanner;
  if (!banner) return;
  if (!accountActionsLocked()) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.textContent =
    "Account actions are read-only while bot sessions are running. Stop the bot from the dashboard, edit here, then restart GnBots.";
  banner.classList.remove("hidden");
}

function applyAccountLockState() {
  updateAccountLockedBanner();
  if (els.accountActionsList) {
    els.accountActionsList.classList.toggle("locked", accountActionsLocked());
  }
  renderAccountTemplateOptions();
  if (currentAccountAdvanced) {
    renderAccountAdvancedPanel(currentAccountAdvanced);
  }
}

function updateAccountSettingsMeta(profileName = "") {
  if (!els.accountSettingsMeta) return;
  if (!selectedAccountId) {
    els.accountSettingsMeta.textContent = "—";
    return;
  }
  const account = profileAccounts.find((item) => item.id === selectedAccountId);
  if (!account) {
    els.accountSettingsMeta.textContent = "—";
    return;
  }
  const enabled = account.active ? "enabled in profile" : "disabled in profile";
  const health = account.healthCheckPassed ? "health check passed" : "health check not passed";
  els.accountSettingsMeta.textContent = `${profileName || profileInUse || "Profile"} · instance ${account.instanceId} · ${enabled} · ${health}`;
}

function renderScheduleMeta(schedule = {}) {
  const parts = [];
  if (schedule.lastUsedRelative) {
    parts.push(`Last used: ${schedule.lastUsedRelative}`);
  } else if (schedule.last) {
    parts.push(`Last used: ${schedule.last}`);
  }
  if (schedule.rulesCount) {
    parts.push(`${schedule.rulesCount} schedule rule${schedule.rulesCount === 1 ? "" : "s"}`);
  }
  const flags = [];
  if (schedule.daily) flags.push("daily");
  if (schedule.hourly) flags.push("hourly");
  if (schedule.weekly) flags.push("weekly");
  if (schedule.active) flags.push("timer active");
  if (flags.length) {
    parts.push(flags.join(", "));
  }
  return parts.join(" · ");
}

function renderActionLastUsed(schedule = {}) {
  if (schedule.lastUsedRelative) {
    return `Last used: ${schedule.lastUsedRelative}`;
  }
  if (schedule.last) {
    return `Last used: ${schedule.last}`;
  }
  return "Last used: never";
}

function showAccountDetailPanels(show) {
  const display = show ? "" : "hidden";
  for (const node of [
    els.accountTemplatesPanel,
    els.accountAdvancedPanel,
    els.accountActionsPanel,
  ]) {
    if (node) node.classList.toggle("hidden", !show);
  }
}

function renderAccountAdvancedPanel(advanced = null) {
  if (!els.accountAdvancedBody) return;
  currentAccountAdvanced = advanced && typeof advanced === "object" ? advanced : null;
  if (!selectedAccountId || !currentAccountAdvanced) {
    els.accountAdvancedBody.innerHTML = `<p class="settings-loading">Select an account to view advanced settings.</p>`;
    return;
  }

  const locked = accountActionsLocked() || accountSettingsBusy;
  const sessionOptions = Array.isArray(currentAccountAdvanced.sessionOptions)
    ? currentAccountAdvanced.sessionOptions
    : [{ value: -1, label: "Any" }];
  const sessionId = Number(currentAccountAdvanced.sessionId ?? -1);
  const sessionHtml = sessionOptions
    .map((option) => {
      const value = Number(option.value);
      const selected = value === sessionId ? " selected" : "";
      return `<option value="${value}"${selected}>${escapeHtml(option.label || String(value))}</option>`;
    })
    .join("");
  const shuffleChecked = currentAccountAdvanced.shuffle ? "checked" : "";
  const customValue = escapeHtml(currentAccountAdvanced.custom || "");
  const lastRun = currentAccountAdvanced.lastRun
    ? `<p class="account-advanced-meta">Account last run: ${escapeHtml(currentAccountAdvanced.lastRun)}</p>`
    : "";

  els.accountAdvancedBody.innerHTML = `
    <div class="account-advanced-grid">
      <label class="account-action-field" for="account-session-select">
        <span class="account-action-field-label">Assigned session</span>
        <span class="account-action-field-control">
          <select id="account-session-select" class="setting-select" ${locked ? "disabled" : ""}>${sessionHtml}</select>
        </span>
      </label>
      <label class="account-action-field account-action-field-boolean" for="account-shuffle-toggle">
        <span class="account-action-field-label">Shuffle</span>
        <span class="account-action-field-control">
          <input id="account-shuffle-toggle" type="checkbox" ${shuffleChecked} ${locked ? "disabled" : ""}>
        </span>
      </label>
      <label class="account-action-field account-advanced-custom" for="account-custom-input">
        <span class="account-action-field-label">Custom</span>
        <span class="account-action-field-control">
          <input id="account-custom-input" class="setting-input" type="text" value="${customValue}" ${locked ? "disabled" : ""}>
        </span>
      </label>
    </div>
    ${lastRun}
    <div class="account-advanced-footer">
      <button class="btn btn-small" id="account-advanced-save" type="button" ${locked ? "disabled" : ""}>
        ${accountSettingsBusy ? "Saving…" : "Save advanced settings"}
      </button>
    </div>
  `;
}

function renderAccountTemplateOptions() {
  if (!els.accountTemplateSelect) return;
  const locked = accountActionsLocked() || accountSettingsBusy;
  const current = els.accountTemplateSelect.value;
  const options = profileTemplates.map((item) => item.title).filter(Boolean);
  if (!options.length) {
    els.accountTemplateSelect.innerHTML = `<option value="">No templates found</option>`;
    els.accountTemplateSelect.disabled = true;
    if (els.accountTemplateDescription) els.accountTemplateDescription.value = "";
    if (els.accountTemplateApply) els.accountTemplateApply.disabled = true;
    if (els.accountTemplateCreate) els.accountTemplateCreate.disabled = locked || !selectedAccountId;
    if (els.accountTemplateRemove) els.accountTemplateRemove.disabled = true;
    return;
  }

  const selected = options.includes(current) ? current : options[0];
  els.accountTemplateSelect.innerHTML = options
    .map((title) => {
      const isSelected = title === selected ? " selected" : "";
      return `<option value="${escapeHtml(title)}"${isSelected}>${escapeHtml(title)}</option>`;
    })
    .join("");
  els.accountTemplateSelect.disabled = locked;
  updateAccountTemplateDescription(selected);
  if (els.accountTemplateApply) els.accountTemplateApply.disabled = locked || !selectedAccountId;
  if (els.accountTemplateCreate) els.accountTemplateCreate.disabled = locked || !selectedAccountId;
  if (els.accountTemplateRemove) els.accountTemplateRemove.disabled = locked;
}

function updateAccountTemplateDescription(title = "") {
  if (!els.accountTemplateDescription) return;
  const match = profileTemplates.find((item) => item.title === title);
  els.accountTemplateDescription.value = match?.description || "";
}

async function loadProfileTemplates() {
  try {
    const response = await fetch("/api/profile/templates?appId=whitebot");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || "Could not load templates.");
    }
    profileTemplates = Array.isArray(body.templates) ? body.templates : [];
  } catch {
    profileTemplates = [];
  }
  renderAccountTemplateOptions();
}

async function saveAccountAdvancedSettings() {
  if (accountActionsLocked() || accountSettingsBusy || !selectedAccountId) return;

  const sessionSelect = document.getElementById("account-session-select");
  const shuffleToggle = document.getElementById("account-shuffle-toggle");
  const customInput = document.getElementById("account-custom-input");
  const payload = {
    sessionId: sessionSelect ? Number(sessionSelect.value) : undefined,
    shuffle: shuffleToggle ? shuffleToggle.checked : undefined,
    custom: customInput ? customInput.value : undefined,
  };

  accountSettingsBusy = true;
  renderAccountAdvancedPanel(currentAccountAdvanced);
  renderAccountTemplateOptions();
  setAccountPageStatus("Saving advanced settings…", "pending");

  try {
    const response = await fetch(
      `/api/profile/accounts/${encodeURIComponent(selectedAccountId)}/settings`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.message || "Could not save account settings.");
    }
    const account = body.account || {};
    currentAccountAdvanced = account.advanced || currentAccountAdvanced;
    renderAccountAdvancedPanel(currentAccountAdvanced);
    renderAccountActions(account.actions || currentAccountActions);
    setAccountPageStatus(body.message || "Advanced settings saved.", "ok");
  } catch (error) {
    setAccountPageStatus(error.message || "Failed to save advanced settings.", "error");
  } finally {
    accountSettingsBusy = false;
    renderAccountAdvancedPanel(currentAccountAdvanced);
    renderAccountTemplateOptions();
    applyAccountLockState();
  }
}

async function applyAccountTemplate() {
  if (accountActionsLocked() || accountSettingsBusy || !selectedAccountId || !els.accountTemplateSelect) return;
  const template = els.accountTemplateSelect.value.trim();
  if (!template) return;
  if (!window.confirm(`Apply template "${template}" to this account? This replaces the account's actions.`)) {
    return;
  }

  accountSettingsBusy = true;
  renderAccountTemplateOptions();
  setAccountPageStatus(`Applying template "${template}"…`, "pending");

  try {
    const response = await fetch(
      `/api/profile/accounts/${encodeURIComponent(selectedAccountId)}/apply-template`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template, appId: "whitebot" }),
      },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.message || "Could not apply template.");
    }
    const account = body.account || {};
    currentAccountAdvanced = account.advanced || currentAccountAdvanced;
    renderAccountAdvancedPanel(currentAccountAdvanced);
    renderAccountActions(account.actions || []);
    setAccountPageStatus(body.message || "Template applied.", "ok");
  } catch (error) {
    setAccountPageStatus(error.message || "Failed to apply template.", "error");
  } finally {
    accountSettingsBusy = false;
    renderAccountTemplateOptions();
    applyAccountLockState();
  }
}

async function createAccountTemplate() {
  if (accountActionsLocked() || accountSettingsBusy || !selectedAccountId) return;
  const title = window.prompt("Template name (letters, numbers, spaces, dots, dashes):");
  if (!title || !title.trim()) return;
  const description = window.prompt("Template description (optional):") || "";

  accountSettingsBusy = true;
  renderAccountTemplateOptions();
  setAccountPageStatus("Creating template…", "pending");

  try {
    const response = await fetch("/api/profile/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title.trim(),
        description,
        accountId: selectedAccountId,
        appId: "whitebot",
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.message || "Could not create template.");
    }
    await loadProfileTemplates();
    if (els.accountTemplateSelect) {
      els.accountTemplateSelect.value = title.trim();
      updateAccountTemplateDescription(title.trim());
    }
    setAccountPageStatus(body.message || "Template created.", "ok");
  } catch (error) {
    setAccountPageStatus(error.message || "Failed to create template.", "error");
  } finally {
    accountSettingsBusy = false;
    renderAccountTemplateOptions();
    applyAccountLockState();
  }
}

async function removeAccountTemplate() {
  if (accountActionsLocked() || accountSettingsBusy || !els.accountTemplateSelect) return;
  const template = els.accountTemplateSelect.value.trim();
  if (!template) return;
  if (!window.confirm(`Remove template "${template}"? This cannot be undone.`)) {
    return;
  }

  accountSettingsBusy = true;
  renderAccountTemplateOptions();
  setAccountPageStatus(`Removing template "${template}"…`, "pending");

  try {
    const response = await fetch(
      `/api/profile/templates/${encodeURIComponent(template)}?appId=whitebot`,
      { method: "DELETE" },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.message || "Could not remove template.");
    }
    await loadProfileTemplates();
    setAccountPageStatus(body.message || "Template removed.", "ok");
  } catch (error) {
    setAccountPageStatus(error.message || "Failed to remove template.", "error");
  } finally {
    accountSettingsBusy = false;
    renderAccountTemplateOptions();
    applyAccountLockState();
  }
}

const SCHEDULE_DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const SCHEDULE_RULE_KIND_LABELS = {
  skip: "Skip",
  wait_after: "Wait After",
  close_instance_wait: "Close Instance And Wait After",
  only_run_on: "Only Run On",
  unknown: "Custom rule",
};

const SCHEDULE_RULE_KIND_OPTIONS = [
  "skip",
  "wait_after",
  "close_instance_wait",
  "only_run_on",
];

function scheduleRuleItems(action) {
  const schedule = action.schedule || {};
  if (Array.isArray(schedule.ruleItems) && schedule.ruleItems.length) {
    return schedule.ruleItems.map((item, index) => ({ ...item, index }));
  }
  const labels = Array.isArray(schedule.rules) ? schedule.rules : [];
  return labels.map((label, index) => ({
    index,
    kind: "unknown",
    kindLabel: SCHEDULE_RULE_KIND_LABELS.unknown,
    label: String(label || ""),
    raw: null,
  }));
}

function renderScheduleDurationFields(actionId, rule, ruleIndex, disabled) {
  const duration = Number(rule.duration ?? 1);
  const unit = rule.durationUnit === "minutes" ? "minutes" : "hours";
  return `
    <label class="account-schedule-field">
      <span>Duration</span>
      <input
        class="setting-input account-schedule-duration"
        type="number"
        min="0.1"
        step="0.1"
        data-action-id="${escapeHtml(actionId)}"
        data-rule-index="${ruleIndex}"
        value="${escapeHtml(String(duration))}"
        ${disabled ? "disabled" : ""}
      >
    </label>
    <label class="account-schedule-field">
      <span>Unit</span>
      <select
        class="setting-select account-schedule-unit"
        data-action-id="${escapeHtml(actionId)}"
        data-rule-index="${ruleIndex}"
        ${disabled ? "disabled" : ""}
      >
        <option value="hours"${unit === "hours" ? " selected" : ""}>Hours</option>
        <option value="minutes"${unit === "minutes" ? " selected" : ""}>Minutes</option>
      </select>
    </label>
  `;
}

function renderScheduleOnlyRunOnFields(actionId, rule, ruleIndex, disabled) {
  const selected = new Set(Array.isArray(rule.days) ? rule.days.map((day) => String(day).toLowerCase()) : []);
  const dayChecks = SCHEDULE_DAY_KEYS.map((day) => {
    const checked = selected.has(day) ? "checked" : "";
    return `
      <label class="account-schedule-day">
        <input
          type="checkbox"
          class="account-schedule-day-input"
          data-action-id="${escapeHtml(actionId)}"
          data-rule-index="${ruleIndex}"
          data-day="${day}"
          ${checked}
          ${disabled ? "disabled" : ""}
        >
        <span>${escapeHtml(day)}</span>
      </label>
    `;
  }).join("");
  const startTime = escapeHtml(rule.startTime || "00:00");
  const endTime = escapeHtml(rule.endTime || "00:00");
  return `
    <div class="account-schedule-days">${dayChecks}</div>
    <label class="account-schedule-field">
      <span>Start</span>
      <input
        class="setting-input account-schedule-start"
        type="time"
        data-action-id="${escapeHtml(actionId)}"
        data-rule-index="${ruleIndex}"
        value="${startTime}"
        ${disabled ? "disabled" : ""}
      >
    </label>
    <label class="account-schedule-field">
      <span>End</span>
      <input
        class="setting-input account-schedule-end"
        type="time"
        data-action-id="${escapeHtml(actionId)}"
        data-rule-index="${ruleIndex}"
        value="${endTime}"
        ${disabled ? "disabled" : ""}
      >
    </label>
  `;
}

function renderScheduleRuleRow(action, rule, ruleIndex, disabled) {
  const actionId = String(action.id);
  const kind = rule.kind || "unknown";
  const fields =
    kind === "only_run_on"
      ? renderScheduleOnlyRunOnFields(actionId, rule, ruleIndex, disabled)
      : kind === "unknown"
        ? `<p class="account-schedule-unknown">This rule uses a custom format. Remove it and add a new rule to edit here.</p>`
        : renderScheduleDurationFields(actionId, rule, ruleIndex, disabled);

  return `
    <article class="account-schedule-rule" data-action-id="${escapeHtml(actionId)}" data-rule-index="${ruleIndex}">
      <div class="account-schedule-rule-head">
        <div>
          <strong>${escapeHtml(rule.kindLabel || SCHEDULE_RULE_KIND_LABELS[kind] || "Rule")}</strong>
          <p class="account-schedule-rule-label">${escapeHtml(rule.label || "")}</p>
        </div>
        <button
          type="button"
          class="btn btn-small account-schedule-delete"
          data-action-id="${escapeHtml(actionId)}"
          data-rule-index="${ruleIndex}"
          title="Remove rule"
          ${disabled ? "disabled" : ""}
        >Remove</button>
      </div>
      <div class="account-schedule-rule-fields">${fields}</div>
    </article>
  `;
}

function renderScheduleRulesBlock(action) {
  const actionId = String(action.id);
  const disabled = accountActionsLocked() || accountActionBusyIds.has(actionId);
  const rules = scheduleRuleItems(action);
  const schedule = action.schedule || {};
  const lastUsed = renderActionLastUsed(schedule);
  const ruleRows = rules
    .map((rule, index) => renderScheduleRuleRow(action, rule, index, disabled))
    .join("");
  const kindOptions = SCHEDULE_RULE_KIND_OPTIONS.map((kind) => {
    const label = SCHEDULE_RULE_KIND_LABELS[kind];
    return `<option value="${kind}">${escapeHtml(label)}</option>`;
  }).join("");

  return `
    <section class="account-action-schedule" data-schedule-editor="${escapeHtml(actionId)}">
      <div class="account-action-schedule-head">
        <h4 class="account-action-schedule-title">Rules</h4>
        <span class="account-action-last-used">${escapeHtml(lastUsed)}</span>
      </div>
      <div class="account-schedule-rules" data-schedule-rules="${escapeHtml(actionId)}">
        ${ruleRows || `<p class="account-schedule-empty">No rules configured for this action.</p>`}
      </div>
      <div class="account-schedule-add-row">
        <select
          class="setting-select account-schedule-kind"
          data-action-id="${escapeHtml(actionId)}"
          ${disabled ? "disabled" : ""}
        >${kindOptions}</select>
        <button
          type="button"
          class="btn btn-small account-schedule-add"
          data-action-id="${escapeHtml(actionId)}"
          ${disabled ? "disabled" : ""}
        >Add</button>
      </div>
      <div class="account-schedule-footer">
        <button
          type="button"
          class="btn btn-small account-schedule-save"
          data-save-schedule-id="${escapeHtml(actionId)}"
          ${disabled ? "disabled" : ""}
        >Save rules</button>
        <button
          type="button"
          class="btn btn-small account-schedule-reset"
          data-reset-schedule-id="${escapeHtml(actionId)}"
          ${disabled ? "disabled" : ""}
        >Reset timers</button>
      </div>
    </section>
  `;
}

function defaultScheduleRule(kind) {
  if (kind === "only_run_on") {
    return {
      kind,
      kindLabel: SCHEDULE_RULE_KIND_LABELS.only_run_on,
      label: "Only run on mon, tue, wed, thu, fri, sat, sun between 12:00 and 18:00",
      days: [...SCHEDULE_DAY_KEYS],
      startTime: "12:00",
      endTime: "18:00",
    };
  }
  return {
    kind,
    kindLabel: SCHEDULE_RULE_KIND_LABELS[kind] || kind,
    label: kind === "skip" ? "Skip for 1 hour" : "Wait 1 hour after",
    duration: 1,
    durationUnit: "hours",
  };
}

function addScheduleRuleToAction(actionId, kind) {
  const action = currentAccountActions.find((item) => String(item.id) === String(actionId));
  if (!action) return;
  const schedule = action.schedule || {};
  const items = scheduleRuleItems(action);
  const next = defaultScheduleRule(kind);
  next.index = items.length;
  schedule.ruleItems = [...items, next];
  schedule.rulesCount = schedule.ruleItems.length;
  action.schedule = schedule;
  renderAccountActions(currentAccountActions);
}

function removeScheduleRuleFromAction(actionId, ruleIndex) {
  const action = currentAccountActions.find((item) => String(item.id) === String(actionId));
  if (!action) return;
  const schedule = action.schedule || {};
  const items = scheduleRuleItems(action).filter((_, index) => index !== Number(ruleIndex));
  schedule.ruleItems = items.map((item, index) => ({ ...item, index }));
  schedule.rulesCount = schedule.ruleItems.length;
  schedule.rules = items.map((item) => item.label).filter(Boolean);
  action.schedule = schedule;
  renderAccountActions(currentAccountActions);
}

function collectScheduleRulesFromDom(actionId) {
  const action = currentAccountActions.find((item) => String(item.id) === String(actionId));
  if (!action) return [];
  const items = scheduleRuleItems(action);
  return items.map((rule, ruleIndex) => {
    if (rule.kind === "unknown" && rule.raw) {
      return { kind: "unknown", raw: rule.raw };
    }
    if (rule.kind === "only_run_on") {
      const days = [];
      document
        .querySelectorAll(
          `.account-schedule-day-input[data-action-id="${CSS.escape(String(actionId))}"][data-rule-index="${ruleIndex}"]:checked`,
        )
        .forEach((input) => {
          const day = input.getAttribute("data-day");
          if (day) days.push(day);
        });
      const startInput = document.querySelector(
        `.account-schedule-start[data-action-id="${CSS.escape(String(actionId))}"][data-rule-index="${ruleIndex}"]`,
      );
      const endInput = document.querySelector(
        `.account-schedule-end[data-action-id="${CSS.escape(String(actionId))}"][data-rule-index="${ruleIndex}"]`,
      );
      return {
        kind: "only_run_on",
        days,
        startTime: startInput?.value || rule.startTime || "00:00",
        endTime: endInput?.value || rule.endTime || "00:00",
      };
    }
    const durationInput = document.querySelector(
      `.account-schedule-duration[data-action-id="${CSS.escape(String(actionId))}"][data-rule-index="${ruleIndex}"]`,
    );
    const unitInput = document.querySelector(
      `.account-schedule-unit[data-action-id="${CSS.escape(String(actionId))}"][data-rule-index="${ruleIndex}"]`,
    );
    return {
      kind: rule.kind,
      duration: Number(durationInput?.value || rule.duration || 1),
      durationUnit: unitInput?.value || rule.durationUnit || "hours",
    };
  });
}

async function saveAccountScheduleRules(actionId, options = {}) {
  if (accountActionsLocked() || accountActionBusyIds.has(String(actionId))) return;

  const payload = {
    scheduleRules: collectScheduleRulesFromDom(actionId),
  };
  if (options.resetTimers) {
    payload.resetScheduleTimers = true;
  }

  accountActionBusyIds.add(String(actionId));
  renderAccountActions(currentAccountActions);
  setAccountPageStatus(options.resetTimers ? "Resetting timers…" : "Saving rules…", "pending");

  try {
    const response = await fetch(
      `/api/profile/accounts/${encodeURIComponent(selectedAccountId)}/actions/${encodeURIComponent(actionId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail || body.message || response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    const updated = body.action;
    if (updated) {
      const index = currentAccountActions.findIndex((item) => String(item.id) === String(actionId));
      if (index >= 0) {
        currentAccountActions[index] = updated;
      }
    }
    setAccountPageStatus(
      body.message || (options.resetTimers ? "Timers reset." : "Rules saved."),
      "ok",
    );
  } catch (error) {
    setAccountPageStatus(error.message || "Failed to save schedule rules.", "error");
  } finally {
    accountActionBusyIds.delete(String(actionId));
    renderAccountActions(currentAccountActions);
  }
}

function switchNamesLocked() {
  return !switchNamesWritable || switchNamesBusy;
}

function formatApiError(body, fallback) {
  if (!body || typeof body !== "object") return fallback;
  const detail = body.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item) => (item && typeof item.msg === "string" ? item.msg : String(item)))
      .filter(Boolean)
      .join("; ");
  }
  if (typeof body.message === "string" && body.message.trim()) return body.message;
  return fallback;
}

function setNamesPageStatus(message, tone = "") {
  if (!els.namesPageStatus) return;
  els.namesPageStatus.textContent = message || "";
  els.namesPageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function updateNamesLockedBanner() {
  const banner = els.namesLockedBanner;
  if (!banner) return;
  if (switchNamesWritable) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.textContent =
    "Switch account names are read-only while bot sessions are running. Stop the bot from the dashboard, then edit here.";
  banner.classList.remove("hidden");
}

function applySwitchNamesLockState() {
  updateNamesLockedBanner();
  if (els.accountNamesList) {
    els.accountNamesList.classList.toggle("locked", switchNamesLocked());
  }
  if (els.accountNamesSaveAll) {
    els.accountNamesSaveAll.disabled = switchNamesLocked() || !switchNameRows.length;
  }
}

function switchNameHistoryOptions(currentValue = "", history = null) {
  const names = [];
  const seen = new Set();
  const source = Array.isArray(history) ? history : currentSwitchNameHistory;
  for (const name of [currentValue, ...source]) {
    const text = String(name || "").trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    names.push(text);
  }
  return names.slice(0, 10);
}

function uniqueSwitchNameHistory(history) {
  const names = [];
  const seen = new Set();
  for (const name of history || []) {
    const text = String(name || "").trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    names.push(text);
  }
  return names;
}

function renderRecentHistoryChips(accountId, value, history, locked) {
  const items = uniqueSwitchNameHistory(history);
  if (!items.length) {
    return `<span class="account-switch-name-empty">No recent names saved yet.</span>`;
  }
  return items
    .map((name) => {
      const isCurrent = name.toLowerCase() === String(value || "").trim().toLowerCase();
      return `
        <span class="account-names-recent-item${isCurrent ? " is-current" : ""}">
          <button
            type="button"
            class="btn btn-small account-switch-name-pick account-names-chip${isCurrent ? " current" : ""}"
            data-account-id="${escapeHtml(accountId)}"
            data-switch-name="${escapeHtml(name)}"
            ${locked ? "disabled" : ""}
            title="${isCurrent ? "Current switch name" : "Use this name"}"
          >${escapeHtml(name)}</button>
          <button
            type="button"
            class="account-names-history-remove"
            data-account-id="${escapeHtml(accountId)}"
            data-switch-name="${escapeHtml(name)}"
            aria-label="Remove ${escapeHtml(name)} from recent names"
            title="Remove from recent names"
          >×</button>
        </span>
      `;
    })
    .join("");
}

function setSwitchNameInputValue(accountId, value) {
  const input = document.querySelector(
    `.account-names-input[data-account-id="${CSS.escape(String(accountId))}"]`,
  );
  if (input) {
    input.value = value;
    input.focus();
  }
}

function renderAccountNameRow(row) {
  const locked = switchNamesLocked();
  const accountId = String(row.accountId);
  const value = row.switchAccountName == null ? "" : String(row.switchAccountName);
  const options = switchNameHistoryOptions(value, row.switchNameHistory || []);
  const listId = `account-names-history-${accountId}`;
  const datalist = options.map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
  const selectOptions = options
    .filter((name) => name.toLowerCase() !== value.trim().toLowerCase())
    .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
    .join("");
  const chips = renderRecentHistoryChips(accountId, value, row.switchNameHistory || [], locked);
  const statusLabel = row.active ? "enabled" : "disabled";

  return `
    <article class="account-names-row" data-account-id="${escapeHtml(accountId)}">
      <div class="account-names-row-meta">
        <div class="account-names-row-title">
          <strong>${escapeHtml(row.accountName || accountId)}</strong>
          <span class="account-names-row-sub">instance ${escapeHtml(String(row.instanceId))} · ${statusLabel}</span>
        </div>
      </div>
      <div class="account-names-row-edit">
        <label class="account-names-field" for="account-names-input-${escapeHtml(accountId)}">
          <span class="account-names-field-label">Switch account name</span>
          <input
            id="account-names-input-${escapeHtml(accountId)}"
            class="setting-input account-names-input"
            type="text"
            list="${listId}"
            data-account-id="${escapeHtml(accountId)}"
            value="${escapeHtml(value)}"
            autocomplete="off"
            spellcheck="false"
            ${locked ? "disabled" : ""}
          >
          <datalist id="${listId}">${datalist}</datalist>
        </label>
        <label class="account-names-field" for="account-names-select-${escapeHtml(accountId)}">
          <span class="account-names-field-label">Recent</span>
          <select
            id="account-names-select-${escapeHtml(accountId)}"
            class="setting-select account-names-recent-select"
            data-account-id="${escapeHtml(accountId)}"
            ${locked ? "disabled" : ""}
          >
            <option value="">Pick a recent name…</option>
            ${selectOptions}
          </select>
        </label>
      </div>
      <div class="account-names-chips">
        <span class="account-names-chips-label">Recent names</span>
        <div class="account-names-chips-list">${chips}</div>
      </div>
    </article>
  `;
}

function renderAccountNamesList() {
  if (!els.accountNamesList) return;
  if (!switchNameRows.length) {
    els.accountNamesList.innerHTML = `<p class="settings-loading">No account switch actions found in this profile.</p>`;
    applySwitchNamesLockState();
    return;
  }
  els.accountNamesList.innerHTML = switchNameRows.map((row) => renderAccountNameRow(row)).join("");
  applySwitchNamesLockState();
}

function collectSwitchNameUpdates() {
  return switchNameRows.map((row) => {
    const accountId = String(row.accountId);
    const input = document.querySelector(
      `.account-names-input[data-account-id="${CSS.escape(accountId)}"]`,
    );
    return {
      accountId,
      switchAccountName: input ? input.value.trim() : String(row.switchAccountName || "").trim(),
    };
  });
}

async function loadAccountNamesTab() {
  if (!els.accountNamesList) return;
  switchNamesBusy = true;
  applySwitchNamesLockState();
  setNamesPageStatus("Loading account names…", "pending");
  els.accountNamesList.innerHTML = `<p class="settings-loading">Loading account names…</p>`;
  try {
    const response = await fetch("/api/profile/switch-names");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || "Could not load switch account names.");
    }
    switchNameRows = Array.isArray(body.accounts) ? body.accounts : [];
    switchNamesWritable = body.writable !== false;
    profileEditLocked = body.writable === false;
    applySwitchNamesLockState();
    if (els.accountNamesMeta) {
      const profile = body.profile || profileInUse || "Profile";
      els.accountNamesMeta.textContent = `${profile} · ${switchNameRows.length} account${switchNameRows.length === 1 ? "" : "s"} with Account Switch`;
    }
    renderAccountNamesList();
    setNamesPageStatus(
      switchNamesLocked()
        ? "Switch account names are read-only while bot sessions are running."
        : `Loaded ${switchNameRows.length} switch account name${switchNameRows.length === 1 ? "" : "s"}. Edit any row, then Save all names.`,
      switchNamesLocked() ? "warn" : "ok",
    );
  } catch (error) {
    switchNameRows = [];
    els.accountNamesList.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load account names.")}</p>`;
    setNamesPageStatus("");
  } finally {
    switchNamesBusy = false;
    applySwitchNamesLockState();
    scheduleSettingsActivityPoll();
  }
}

async function removeSwitchNameHistory(accountId, name) {
  const cleanAccountId = String(accountId || "").trim();
  const cleanName = String(name || "").trim();
  if (!cleanAccountId || !cleanName) return;

  setNamesPageStatus(`Removing ${cleanName} from recent names…`, "pending");
  try {
    const response = await fetch(
      `/api/profile/switch-names/${encodeURIComponent(cleanAccountId)}/history?name=${encodeURIComponent(cleanName)}`,
      { method: "DELETE" },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || "Could not remove recent name.");
    }

    const row = switchNameRows.find((item) => String(item.accountId) === cleanAccountId);
    if (row) {
      row.switchNameHistory = Array.isArray(body.switchNameHistory) ? body.switchNameHistory : [];
    }
    renderAccountNamesList();
    setNamesPageStatus(`Removed ${cleanName} from recent names.`, "ok");
  } catch (error) {
    setNamesPageStatus(error.message || "Failed to remove recent name.", "error");
  }
}

async function saveAllSwitchNames() {
  if (switchNamesLocked() || !switchNameRows.length) return;

  const updates = collectSwitchNameUpdates();
  switchNamesBusy = true;
  applySwitchNamesLockState();
  setNamesPageStatus("Saving all switch account names…", "pending");

  try {
    const response = await fetch("/api/profile/switch-names", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(formatApiError(body, "Could not save switch account names."));
    }
    switchNameRows = Array.isArray(body.accounts) ? body.accounts : switchNameRows;
    renderAccountNamesList();
    setNamesPageStatus(body.message || "All switch account names saved.", "ok");
    els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    setNamesPageStatus(error.message || "Failed to save switch account names.", "error");
  } finally {
    switchNamesBusy = false;
    applySwitchNamesLockState();
  }
}

function bulkActionsSessionLocked() {
  return !bulkFieldsWritable;
}

function bulkActionsLocked() {
  return bulkActionsSessionLocked() || bulkFieldsBusy;
}

function setBulkPageStatus(message, tone = "") {
  if (!els.bulkPageStatus) return;
  els.bulkPageStatus.textContent = message || "";
  els.bulkPageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function updateBulkLockedBanner() {
  const banner = els.bulkLockedBanner;
  if (!banner) return;
  if (!bulkActionsSessionLocked()) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.textContent =
    "Bulk action settings are read-only while bot sessions are running. Stop the bot from the dashboard, then edit here.";
  banner.classList.remove("hidden");
}

function applyBulkActionsLockState() {
  updateBulkLockedBanner();
  if (els.bulkActionsList) {
    els.bulkActionsList.classList.toggle("locked", bulkActionsSessionLocked());
  }
  const locked = bulkActionsLocked();
  if (els.bulkActionSelect) els.bulkActionSelect.disabled = locked || bulkFieldsBusy;
  if (els.bulkFieldSelect) {
    els.bulkFieldSelect.disabled = locked || bulkFieldsBusy || !bulkSelectedScriptSuffix;
  }
  if (els.bulkApplySelectedBtn) {
    els.bulkApplySelectedBtn.disabled = locked || !bulkSelectedAccountIds.size || !bulkFieldMeta;
  }
  if (els.bulkSaveSelectedBtn) {
    els.bulkSaveSelectedBtn.disabled = locked || !bulkSelectedAccountIds.size || !bulkFieldRows.length;
  }
  if (els.bulkSelectAllBtn) els.bulkSelectAllBtn.disabled = locked || !bulkFieldRows.length;
  if (els.bulkSelectNoneBtn) els.bulkSelectNoneBtn.disabled = locked || !bulkFieldRows.length;
}

function bulkActionBySuffix(suffix) {
  return bulkActionCatalog.find((item) => String(item.scriptSuffix) === String(suffix)) || null;
}

function bulkFieldsForAction(suffix) {
  const action = bulkActionBySuffix(suffix);
  return Array.isArray(action?.fields) ? action.fields : [];
}

function bulkFieldIsSchedule(field) {
  const type = String(field?.type || "");
  return type === "schedule_rules" || type === "schedule_rule" || type === "schedule_reset";
}

function bulkScheduleRulesFromValue(value) {
  return Array.isArray(value) ? value.map((rule) => ({ ...rule })) : [];
}

function bulkScheduleRuleFromValue(value, field) {
  if (value && typeof value === "object") return { ...value };
  if (field?.type === "schedule_rule") {
    return { kind: "wait_after", duration: 1, durationUnit: "hours" };
  }
  return { kind: "wait_after", duration: 1, durationUnit: "hours" };
}

function summarizeBulkScheduleValue(field, value) {
  if (!field) return "—";
  if (field.type === "schedule_reset") {
    return value ? "Reset timers" : "No change";
  }
  if (field.type === "schedule_rule") {
    const rule = bulkScheduleRuleFromValue(value, field);
    if (rule.kind === "only_run_on") {
      const days = Array.isArray(rule.days) ? rule.days.join(", ") : "";
      return `Only run on ${days} ${rule.startTime || "00:00"}–${rule.endTime || "00:00"}`;
    }
    if (rule.kind === "unknown") return "Custom rule";
    const amount = rule.duration ?? 1;
    const unit = rule.durationUnit === "minutes" ? "minute(s)" : "hour(s)";
    const label = SCHEDULE_RULE_KIND_LABELS[rule.kind] || rule.kind;
    return `${label}: ${amount} ${unit}`;
  }
  if (field.type === "schedule_rules") {
    const rules = bulkScheduleRulesFromValue(value);
    if (!rules.length) return "No rules";
    return rules
      .map((rule) => summarizeBulkScheduleValue({ type: "schedule_rule" }, rule))
      .join("; ");
  }
  return "—";
}

function renderBulkScheduleDurationFields(scope, rule, ruleIndex, disabled) {
  const duration = Number(rule.duration ?? 1);
  const unit = rule.durationUnit === "minutes" ? "minutes" : "hours";
  return `
    <label class="account-schedule-field">
      <span>Duration</span>
      <input
        class="setting-input bulk-schedule-duration"
        type="number"
        min="0.1"
        step="0.1"
        data-bulk-schedule-scope="${escapeHtml(scope)}"
        data-rule-index="${ruleIndex}"
        value="${escapeHtml(String(duration))}"
        ${disabled ? "disabled" : ""}
      >
    </label>
    <label class="account-schedule-field">
      <span>Unit</span>
      <select
        class="setting-select bulk-schedule-unit"
        data-bulk-schedule-scope="${escapeHtml(scope)}"
        data-rule-index="${ruleIndex}"
        ${disabled ? "disabled" : ""}
      >
        <option value="hours"${unit === "hours" ? " selected" : ""}>Hours</option>
        <option value="minutes"${unit === "minutes" ? " selected" : ""}>Minutes</option>
      </select>
    </label>
  `;
}

function renderBulkScheduleOnlyRunOnFields(scope, rule, ruleIndex, disabled) {
  const selected = new Set(Array.isArray(rule.days) ? rule.days.map((day) => String(day).toLowerCase()) : []);
  const dayChecks = SCHEDULE_DAY_KEYS.map((day) => {
    const checked = selected.has(day) ? "checked" : "";
    return `
      <label class="account-schedule-day">
        <input
          type="checkbox"
          class="bulk-schedule-day-input"
          data-bulk-schedule-scope="${escapeHtml(scope)}"
          data-rule-index="${ruleIndex}"
          data-day="${day}"
          ${checked}
          ${disabled ? "disabled" : ""}
        >
        <span>${escapeHtml(day)}</span>
      </label>
    `;
  }).join("");
  return `
    <div class="account-schedule-days">${dayChecks}</div>
    <label class="account-schedule-field">
      <span>Start</span>
      <input
        class="setting-input bulk-schedule-start"
        type="time"
        data-bulk-schedule-scope="${escapeHtml(scope)}"
        data-rule-index="${ruleIndex}"
        value="${escapeHtml(rule.startTime || "00:00")}"
        ${disabled ? "disabled" : ""}
      >
    </label>
    <label class="account-schedule-field">
      <span>End</span>
      <input
        class="setting-input bulk-schedule-end"
        type="time"
        data-bulk-schedule-scope="${escapeHtml(scope)}"
        data-rule-index="${ruleIndex}"
        value="${escapeHtml(rule.endTime || "00:00")}"
        ${disabled ? "disabled" : ""}
      >
    </label>
  `;
}

function renderBulkScheduleRuleRow(scope, rule, ruleIndex, disabled) {
  const kind = rule.kind || "wait_after";
  const fields =
    kind === "only_run_on"
      ? renderBulkScheduleOnlyRunOnFields(scope, rule, ruleIndex, disabled)
      : kind === "unknown"
        ? `<p class="account-schedule-unknown">Custom rule format — edit in Account Settings.</p>`
        : renderBulkScheduleDurationFields(scope, rule, ruleIndex, disabled);
  return `
    <article class="account-schedule-rule bulk-schedule-rule" data-bulk-schedule-scope="${escapeHtml(scope)}" data-rule-index="${ruleIndex}" data-rule-kind="${escapeHtml(kind)}">
      <div class="account-schedule-rule-head">
        <div>
          <strong>${escapeHtml(SCHEDULE_RULE_KIND_LABELS[kind] || kind)}</strong>
        </div>
        <button
          type="button"
          class="btn btn-small bulk-schedule-delete"
          data-bulk-schedule-scope="${escapeHtml(scope)}"
          data-rule-index="${ruleIndex}"
          ${disabled ? "disabled" : ""}
        >Remove</button>
      </div>
      <div class="account-schedule-rule-fields">${fields}</div>
    </article>
  `;
}

function renderBulkScheduleRulesEditor(scope, rules, disabled) {
  const items = bulkScheduleRulesFromValue(rules);
  const ruleRows = items.map((rule, index) => renderBulkScheduleRuleRow(scope, rule, index, disabled)).join("");
  const kindOptions = SCHEDULE_RULE_KIND_OPTIONS.map((kind) => {
    const label = SCHEDULE_RULE_KIND_LABELS[kind];
    return `<option value="${kind}">${escapeHtml(label)}</option>`;
  }).join("");
  return `
    <div class="bulk-schedule-editor" data-bulk-schedule-scope="${escapeHtml(scope)}">
      <div class="account-schedule-rules">${ruleRows || `<p class="account-schedule-empty">No rules configured.</p>`}</div>
      <div class="account-schedule-add-row">
        <select class="setting-select bulk-schedule-kind" data-bulk-schedule-scope="${escapeHtml(scope)}" ${disabled ? "disabled" : ""}>${kindOptions}</select>
        <button type="button" class="btn btn-small bulk-schedule-add" data-bulk-schedule-scope="${escapeHtml(scope)}" ${disabled ? "disabled" : ""}>Add rule</button>
      </div>
    </div>
  `;
}

function renderBulkScheduleSingleRuleEditor(scope, rule, disabled) {
  return `
    <div class="bulk-schedule-editor bulk-schedule-editor-single" data-bulk-schedule-scope="${escapeHtml(scope)}">
      ${renderBulkScheduleRuleRow(scope, bulkScheduleRuleFromValue(rule), 0, disabled)}
    </div>
  `;
}

function collectBulkScheduleRulesFromDom(scope) {
  const container = document.querySelector(`[data-bulk-schedule-scope="${CSS.escape(scope)}"]`);
  if (!container) return [];
  const rules = [];
  container.querySelectorAll(".bulk-schedule-rule").forEach((row) => {
    const ruleIndex = Number(row.getAttribute("data-rule-index") || 0);
    const kind = row.getAttribute("data-rule-kind") || "wait_after";
    if (kind === "only_run_on") {
      const days = [];
      container
        .querySelectorAll(
          `.bulk-schedule-day-input[data-bulk-schedule-scope="${CSS.escape(scope)}"][data-rule-index="${ruleIndex}"]:checked`,
        )
        .forEach((input) => {
          const day = input.getAttribute("data-day");
          if (day) days.push(day);
        });
      const startInput = container.querySelector(
        `.bulk-schedule-start[data-bulk-schedule-scope="${CSS.escape(scope)}"][data-rule-index="${ruleIndex}"]`,
      );
      const endInput = container.querySelector(
        `.bulk-schedule-end[data-bulk-schedule-scope="${CSS.escape(scope)}"][data-rule-index="${ruleIndex}"]`,
      );
      rules.push({
        kind: "only_run_on",
        days,
        startTime: startInput?.value || "00:00",
        endTime: endInput?.value || "00:00",
      });
      return;
    }
    if (kind === "unknown") {
      return;
    }
    const durationInput = container.querySelector(
      `.bulk-schedule-duration[data-bulk-schedule-scope="${CSS.escape(scope)}"][data-rule-index="${ruleIndex}"]`,
    );
    const unitInput = container.querySelector(
      `.bulk-schedule-unit[data-bulk-schedule-scope="${CSS.escape(scope)}"][data-rule-index="${ruleIndex}"]`,
    );
    rules.push({
      kind,
      duration: Number(durationInput?.value || 1),
      durationUnit: unitInput?.value || "hours",
    });
  });
  return rules;
}

function collectBulkScheduleSingleRuleFromDom(scope) {
  const rules = collectBulkScheduleRulesFromDom(scope);
  return rules[0] || { kind: "wait_after", duration: 1, durationUnit: "hours" };
}

function formatBulkFieldValue(field, value) {
  if (value == null) return "";
  if (bulkFieldIsSchedule(field)) return summarizeBulkScheduleValue(field, value);
  if (field?.type === "boolean") return value ? "true" : "false";
  return String(value);
}

function renderBulkFieldInput(field, value, { inputId = "bulk-apply-value", disabled = false, dataAccountId = "" } = {}) {
  if (!field) return "";
  const scope = dataAccountId ? `bulk-row-${dataAccountId}` : "bulk-apply";

  if (field.type === "schedule_rules") {
    return renderBulkScheduleRulesEditor(scope, value, disabled);
  }
  if (field.type === "schedule_rule") {
    return renderBulkScheduleSingleRuleEditor(scope, value, disabled);
  }
  if (field.type === "schedule_reset") {
    const checked = parseStoredBoolean(value);
    return `<label class="bulk-schedule-reset"><input type="checkbox" class="bulk-field-input bulk-field-checkbox" data-bulk-field-input="1" data-bulk-account-id="${escapeHtml(dataAccountId)}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}> Reset timers</label>`;
  }

  const accountAttr = dataAccountId ? ` data-bulk-account-id="${escapeHtml(dataAccountId)}"` : "";
  const common = `id="${inputId}" class="setting-input bulk-field-input" data-bulk-field-input="1"${accountAttr}`;

  if (field.type === "boolean") {
    const checked = parseStoredBoolean(value);
    return `<input type="checkbox" ${common.replace('class="setting-input bulk-field-input"', 'class="bulk-field-input bulk-field-checkbox"')} ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}>`;
  }

  if (field.type === "select") {
    const current = formatBulkFieldValue(field, value);
    const options = (field.options || [])
      .map((option) => {
        const text = String(option);
        const selected = text === current ? " selected" : "";
        return `<option value="${escapeHtml(text)}"${selected}>${escapeHtml(text)}</option>`;
      })
      .join("");
    return `<select class="setting-select bulk-field-input" data-bulk-field-input="1"${accountAttr} ${disabled ? "disabled" : ""}>${options}</select>`;
  }

  const inputType = field.type === "number" ? "number" : "text";
  return `<input ${common} type="${inputType}" value="${escapeHtml(formatBulkFieldValue(field, value))}" ${disabled ? "disabled" : ""}>`;
}

function readBulkFieldInput(input, field, scope = "") {
  if (!field) return "";
  if (field.type === "schedule_rules") {
    return collectBulkScheduleRulesFromDom(scope || input?.closest("[data-bulk-schedule-scope]")?.getAttribute("data-bulk-schedule-scope") || "bulk-apply");
  }
  if (field.type === "schedule_rule") {
    return collectBulkScheduleSingleRuleFromDom(scope || input?.closest("[data-bulk-schedule-scope]")?.getAttribute("data-bulk-schedule-scope") || "bulk-apply");
  }
  if (!input) return "";
  if (field.type === "boolean" || field.type === "schedule_reset") {
    return input.checked;
  }
  if (input.tagName === "SELECT") {
    return input.value;
  }
  if (field.type === "number") {
    const text = input.value.trim();
    if (!text) return "";
    const number = Number(text);
    return Number.isFinite(number) ? number : text;
  }
  return input.value;
}

function renderBulkApplyControl() {
  if (!els.bulkApplyControl) return;
  if (!bulkFieldMeta) {
    els.bulkApplyControl.innerHTML = "";
    return;
  }
  if (bulkFieldMeta.type === "schedule_rules") {
    const seed = bulkScheduleRulesFromValue(bulkFieldMeta.value);
    els.bulkApplyControl.innerHTML = renderBulkScheduleRulesEditor(
      "bulk-apply",
      seed.length ? seed : [{ kind: "wait_after", duration: 1, durationUnit: "hours" }],
      bulkActionsSessionLocked(),
    );
    return;
  }
  if (bulkFieldMeta.type === "schedule_rule") {
    els.bulkApplyControl.innerHTML = renderBulkScheduleSingleRuleEditor(
      "bulk-apply",
      bulkScheduleRuleFromValue(bulkFieldMeta.value, bulkFieldMeta),
      bulkActionsSessionLocked(),
    );
    return;
  }
  if (bulkFieldMeta.type === "schedule_reset") {
    els.bulkApplyControl.innerHTML = renderBulkFieldInput(bulkFieldMeta, false, { disabled: bulkActionsSessionLocked() });
    return;
  }
  els.bulkApplyControl.innerHTML = renderBulkFieldInput(bulkFieldMeta, bulkFieldMeta.value, { disabled: bulkActionsSessionLocked() });
}

function renderBulkActionSelectOptions() {
  if (!els.bulkActionSelect) return;
  const options = [
    `<option value="">Select an action…</option>`,
    ...bulkActionCatalog.map(
      (action) =>
        `<option value="${escapeHtml(action.scriptSuffix)}"${action.scriptSuffix === bulkSelectedScriptSuffix ? " selected" : ""}>${escapeHtml(action.title || action.scriptSuffix)}</option>`,
    ),
  ];
  els.bulkActionSelect.innerHTML = options.join("");
  els.bulkActionSelect.disabled = bulkActionsLocked() || !bulkActionCatalog.length;
}

function renderBulkFieldSelectOptions() {
  if (!els.bulkFieldSelect) return;
  const fields = bulkFieldsForAction(bulkSelectedScriptSuffix);
  const options = [
    `<option value="">Select a setting…</option>`,
    ...fields.map(
      (field) =>
        `<option value="${escapeHtml(field.key)}"${field.key === bulkSelectedFieldKey ? " selected" : ""}>${escapeHtml(field.label || field.key)}</option>`,
    ),
  ];
  els.bulkFieldSelect.innerHTML = options.join("");
  els.bulkFieldSelect.disabled = bulkActionsLocked() || !bulkSelectedScriptSuffix || !fields.length;
}

function renderBulkActionFieldRow(row) {
  const accountId = String(row.accountId);
  const checked = bulkSelectedAccountIds.has(accountId);
  // Session lock only — never treat in-flight loading (busy) as "bot sessions running".
  const locked = bulkActionsSessionLocked();
  const inputId = `bulk-field-${accountId}`;
  const statusLabel = row.active ? "active" : "inactive";
  const scope = `bulk-row-${accountId}`;
  const editBlock = bulkFieldIsSchedule(bulkFieldMeta)
    ? `
      <div class="bulk-actions-row-edit bulk-actions-row-edit-schedule">
        <span class="bulk-actions-field-label">New value</span>
        <p class="bulk-schedule-summary">${escapeHtml(summarizeBulkScheduleValue(bulkFieldMeta, row.value))}</p>
        <details class="bulk-schedule-row-details">
          <summary>Edit this account</summary>
          ${renderBulkFieldInput(bulkFieldMeta, row.value, {
            disabled: locked,
            dataAccountId: accountId,
          })}
        </details>
      </div>`
    : `<label class="bulk-actions-row-edit" for="${escapeHtml(inputId)}">
        <span class="bulk-actions-field-label">New value</span>
        ${renderBulkFieldInput(bulkFieldMeta, row.value, {
          inputId,
          disabled: locked,
          dataAccountId: accountId,
        })}
      </label>`;
  return `
    <article class="bulk-actions-row" data-account-id="${escapeHtml(accountId)}">
      <label class="bulk-actions-select">
        <input
          type="checkbox"
          class="bulk-account-select"
          data-account-id="${escapeHtml(accountId)}"
          ${checked ? "checked" : ""}
          ${locked ? "disabled" : ""}
        >
        <span class="bulk-actions-select-label">Include</span>
      </label>
      <div class="bulk-actions-row-meta">
        <div class="bulk-actions-row-title">
          <strong>${escapeHtml(row.accountName || accountId)}</strong>
          <span class="bulk-actions-row-sub">instance ${escapeHtml(String(row.instanceId))} · ${statusLabel}</span>
        </div>
        <div class="bulk-actions-row-current">
          <span class="bulk-actions-current-label">Current</span>
          <span class="bulk-actions-current-value">${escapeHtml(row.display || "—")}</span>
        </div>
      </div>
      ${editBlock}
    </article>
  `;
}

function renderBulkActionFieldList() {
  if (!els.bulkActionsList) return;
  if (!bulkSelectedScriptSuffix || !bulkSelectedFieldKey) {
    els.bulkActionsList.innerHTML = `<p class="settings-loading">Choose an action and setting to edit.</p>`;
    els.bulkActionsBulkRow?.classList.add("hidden");
    els.bulkActionsSelectionRow?.classList.add("hidden");
    return;
  }
  if (!bulkFieldRows.length) {
    els.bulkActionsList.innerHTML = `<p class="settings-loading">No accounts have this action/setting.</p>`;
    els.bulkActionsBulkRow?.classList.remove("hidden");
    els.bulkActionsSelectionRow?.classList.remove("hidden");
    renderBulkApplyControl();
    applyBulkActionsLockState();
    return;
  }

  els.bulkActionsBulkRow?.classList.remove("hidden");
  els.bulkActionsSelectionRow?.classList.remove("hidden");
  renderBulkApplyControl();
  els.bulkActionsList.innerHTML = bulkFieldRows.map((row) => renderBulkActionFieldRow(row)).join("");
  applyBulkActionsLockState();
}

function collectBulkFieldUpdates(onlySelected = true) {
  const updates = [];
  for (const row of bulkFieldRows) {
    const accountId = String(row.accountId);
    if (onlySelected && !bulkSelectedAccountIds.has(accountId)) continue;
    if (bulkFieldIsSchedule(bulkFieldMeta)) {
      const scope = `bulk-row-${accountId}`;
      let value;
      if (bulkFieldMeta.type === "schedule_rules") {
        value = collectBulkScheduleRulesFromDom(scope);
      } else if (bulkFieldMeta.type === "schedule_rule") {
        value = collectBulkScheduleSingleRuleFromDom(scope);
      } else {
        const checkbox = document.querySelector(
          `[data-bulk-field-input][data-bulk-account-id="${CSS.escape(accountId)}"]`,
        );
        value = checkbox ? checkbox.checked : Boolean(row.value);
      }
      updates.push({ accountId, value });
      continue;
    }
    const input = document.querySelector(
      `[data-bulk-field-input][data-bulk-account-id="${CSS.escape(accountId)}"]`,
    );
    if (!input) continue;
    updates.push({
      accountId,
      value: readBulkFieldInput(input, bulkFieldMeta),
    });
  }
  return updates;
}

async function loadBulkActionCatalog() {
  bulkFieldsBusy = true;
  applyBulkActionsLockState();
  setBulkPageStatus("Loading actions…", "pending");
  try {
    const response = await fetch("/api/profile/action-fields", { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(formatApiError(body, "Could not load action catalog."));
    }
    bulkActionCatalog = Array.isArray(body.actions) ? body.actions : [];
    bulkFieldsWritable = body.writable !== false;
    const profile = body.profile ? String(body.profile) : "";
    if (els.bulkActionsMeta) {
      els.bulkActionsMeta.textContent = profile
        ? `${profile} · ${bulkActionCatalog.length} action type${bulkActionCatalog.length === 1 ? "" : "s"}`
        : "—";
    }
    renderBulkActionSelectOptions();
    renderBulkFieldSelectOptions();
    renderBulkActionFieldList();
    setBulkPageStatus(
      bulkActionsSessionLocked()
        ? "Bulk action settings are read-only while bot sessions are running."
        : "Choose an action and setting, then edit selected accounts.",
      bulkActionsSessionLocked() ? "warn" : "ok",
    );
  } catch (error) {
    bulkActionCatalog = [];
    if (els.bulkActionsList) {
      els.bulkActionsList.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load bulk actions.")}</p>`;
    }
    setBulkPageStatus("");
  } finally {
    bulkFieldsBusy = false;
    applyBulkActionsLockState();
  }
}

async function loadBulkActionFieldRows() {
  if (!bulkSelectedScriptSuffix || !bulkSelectedFieldKey) {
    bulkFieldRows = [];
    bulkFieldMeta = null;
    renderBulkActionFieldList();
    return;
  }

  bulkFieldsBusy = true;
  applyBulkActionsLockState();
  setBulkPageStatus("Loading account values…", "pending");
  try {
    const query = new URLSearchParams({
      scriptSuffix: bulkSelectedScriptSuffix,
      fieldKey: bulkSelectedFieldKey,
    });
    const response = await fetch(`/api/profile/action-fields?${query.toString()}`, { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(formatApiError(body, "Could not load action field values."));
    }
    bulkFieldsWritable = body.writable !== false;
    bulkFieldMeta = body.field || null;
    bulkFieldRows = Array.isArray(body.accounts) ? body.accounts : [];
    bulkSelectedAccountIds = new Set(bulkFieldRows.map((row) => String(row.accountId)));
    if (bulkFieldMeta && bulkFieldRows.length && bulkFieldIsSchedule(bulkFieldMeta)) {
      bulkFieldMeta = { ...bulkFieldMeta, value: bulkFieldRows[0].value };
    }
    // Clear busy before render/status so rows are not permanently disabled as "sessions running".
    bulkFieldsBusy = false;
    renderBulkActionFieldList();
    const fieldLabel = bulkFieldMeta?.label || bulkSelectedFieldKey;
    const action = bulkActionBySuffix(bulkSelectedScriptSuffix);
    setBulkPageStatus(
      bulkActionsSessionLocked()
        ? "Bulk action settings are read-only while bot sessions are running."
        : `${action?.title || bulkSelectedScriptSuffix} · ${fieldLabel} · ${bulkFieldRows.length} account${bulkFieldRows.length === 1 ? "" : "s"}`,
      bulkActionsSessionLocked() ? "warn" : "ok",
    );
  } catch (error) {
    bulkFieldRows = [];
    bulkFieldMeta = null;
    if (els.bulkActionsList) {
      els.bulkActionsList.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load values.")}</p>`;
    }
    setBulkPageStatus(error.message || "Failed to load values.", "error");
  } finally {
    bulkFieldsBusy = false;
    applyBulkActionsLockState();
  }
}

async function loadBulkActionsTab() {
  bulkSelectedScriptSuffix = els.bulkActionSelect?.value || bulkSelectedScriptSuffix || "";
  bulkSelectedFieldKey = els.bulkFieldSelect?.value || bulkSelectedFieldKey || "";
  await loadBulkActionCatalog();
  if (bulkSelectedScriptSuffix && bulkSelectedFieldKey) {
    await loadBulkActionFieldRows();
  }
}

function applyBulkValueToSelected() {
  if (!bulkFieldMeta || !els.bulkApplyControl) return;
  let value;
  if (bulkFieldMeta.type === "schedule_rules") {
    value = collectBulkScheduleRulesFromDom("bulk-apply");
  } else if (bulkFieldMeta.type === "schedule_rule") {
    value = collectBulkScheduleSingleRuleFromDom("bulk-apply");
  } else if (bulkFieldMeta.type === "schedule_reset") {
    const checkbox = els.bulkApplyControl.querySelector("[data-bulk-field-input]");
    value = checkbox ? checkbox.checked : true;
  } else {
    const source = els.bulkApplyControl.querySelector("[data-bulk-field-input]");
    if (!source) return;
    value = readBulkFieldInput(source, bulkFieldMeta);
  }
  for (const accountId of bulkSelectedAccountIds) {
    const row = bulkFieldRows.find((item) => String(item.accountId) === String(accountId));
    if (row) row.value = value;
  }
  renderBulkActionFieldList();
  setBulkPageStatus("Applied value to selected rows. Review and Save selected.", "ok");
}

function bulkScheduleRerender(scope, rules) {
  const container = document.querySelector(`[data-bulk-schedule-scope="${CSS.escape(scope)}"]`);
  if (!container) return;
  const rulesHost = container.querySelector(".account-schedule-rules");
  if (!rulesHost) return;
  const disabled = bulkActionsSessionLocked();
  rulesHost.innerHTML = rules.length
    ? rules.map((rule, index) => renderBulkScheduleRuleRow(scope, rule, index, disabled)).join("")
    : `<p class="account-schedule-empty">No rules configured.</p>`;
}

function bulkScheduleAddRule(scope) {
  const container = document.querySelector(`[data-bulk-schedule-scope="${CSS.escape(scope)}"]`);
  if (!container) return;
  const kindSelect = container.querySelector(".bulk-schedule-kind");
  const kind = kindSelect?.value || "wait_after";
  const rules = collectBulkScheduleRulesFromDom(scope);
  const next =
    kind === "only_run_on"
      ? { kind, days: [...SCHEDULE_DAY_KEYS], startTime: "12:00", endTime: "18:00" }
      : { kind, duration: 1, durationUnit: "hours" };
  rules.push(next);
  bulkScheduleRerender(scope, rules);
}

function bulkScheduleDeleteRule(scope, ruleIndex) {
  const rules = collectBulkScheduleRulesFromDom(scope).filter((_, index) => index !== Number(ruleIndex));
  bulkScheduleRerender(scope, rules);
}

async function saveBulkActionFields() {
  if (bulkActionsLocked() || !bulkSelectedScriptSuffix || !bulkSelectedFieldKey) return;
  const updates = collectBulkFieldUpdates(true);
  if (!updates.length) {
    setBulkPageStatus("Select at least one account to update.", "warn");
    return;
  }

  bulkFieldsBusy = true;
  applyBulkActionsLockState();
  setBulkPageStatus(`Saving ${updates.length} account${updates.length === 1 ? "" : "s"}…`, "pending");

  try {
    const response = await fetch("/api/profile/action-fields/bulk", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scriptSuffix: bulkSelectedScriptSuffix,
        fieldKey: bulkSelectedFieldKey,
        updates,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(formatApiError(body, "Could not save bulk action settings."));
    }
    bulkFieldMeta = body.field || bulkFieldMeta;
    bulkFieldRows = Array.isArray(body.accounts) ? body.accounts : bulkFieldRows;
    renderBulkActionFieldList();
    setBulkPageStatus(body.message || "Bulk action settings saved.", "ok");
    els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    setBulkPageStatus(error.message || "Failed to save bulk action settings.", "error");
  } finally {
    bulkFieldsBusy = false;
    applyBulkActionsLockState();
  }
}

function renderSwitchAccountNameField(action, field) {
  const actionId = String(action.id);
  const disabled = accountActionsLocked() || accountActionBusyIds.has(actionId);
  const fieldId = `account-action-${actionId}-switchAccountName`;
  const listId = `account-switch-name-history-${actionId}`;
  const value = field.value == null ? "" : String(field.value);
  const options = switchNameHistoryOptions(value);
  const datalist = options
    .map((name) => `<option value="${escapeHtml(name)}"></option>`)
    .join("");
  const recent = options.filter((name) => name.toLowerCase() !== value.trim().toLowerCase());
  const chips = recent.length
    ? recent
        .map(
          (name) => `
            <button
              type="button"
              class="btn btn-small account-switch-name-pick"
              data-action-id="${escapeHtml(actionId)}"
              data-switch-name="${escapeHtml(name)}"
              ${disabled ? "disabled" : ""}
            >${escapeHtml(name)}</button>
          `,
        )
        .join("")
  : `<span class="account-switch-name-empty">Recent names appear here after you save a new one.</span>`;

  return `
    <div class="account-action-field account-switch-name-field">
      <label class="account-switch-name-label" for="${fieldId}">
        <span class="account-action-field-label">${escapeHtml(field.label || "Switch account name")}</span>
        <span class="account-action-field-control account-switch-name-control">
          <input
            id="${fieldId}"
            class="setting-input account-switch-name-input"
            type="text"
            list="${listId}"
            data-action-id="${escapeHtml(actionId)}"
            data-field-key="switchAccountName"
            data-field-type="text"
            value="${escapeHtml(value)}"
            autocomplete="off"
            spellcheck="false"
            ${disabled ? "disabled" : ""}
          >
          <datalist id="${listId}">${datalist}</datalist>
        </span>
      </label>
      <div class="account-switch-name-recent">
        <span class="account-switch-name-recent-label">Recent</span>
        <div class="account-switch-name-chips">${chips}</div>
      </div>
    </div>
  `;
}

function renderAccountActionField(action, field) {
  const actionId = String(action.id);
  const disabled = accountActionsLocked() || accountActionBusyIds.has(actionId);
  const fieldId = `account-action-${actionId}-${field.key.replaceAll(".", "-")}`;
  const label = escapeHtml(field.label || field.key);
  const fieldKey = escapeHtml(field.key);

  if (field.key === "switchAccountName") {
    return renderSwitchAccountNameField(action, field);
  }

  if (field.type === "boolean") {
    const checked = Boolean(field.value);
    return `
      <label class="account-action-field account-action-field-boolean" for="${fieldId}">
        <span class="account-action-field-label">${label}</span>
        <span class="account-action-field-control">
          <input
            id="${fieldId}"
            type="checkbox"
            data-action-id="${actionId}"
            data-field-key="${fieldKey}"
            data-field-type="boolean"
            ${checked ? "checked" : ""}
            ${disabled ? "disabled" : ""}
          >
        </span>
      </label>
    `;
  }

  if (field.type === "select") {
    const current = field.value == null ? "" : String(field.value);
    const options = (field.options || []).map((option) => {
      const value = String(option);
      const selected = value === current ? " selected" : "";
      return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(value)}</option>`;
    }).join("");
    return `
      <label class="account-action-field" for="${fieldId}">
        <span class="account-action-field-label">${label}</span>
        <span class="account-action-field-control">
          <select
            id="${fieldId}"
            class="setting-select"
            data-action-id="${actionId}"
            data-field-key="${fieldKey}"
            data-field-type="select"
            ${disabled ? "disabled" : ""}
          >${options}</select>
        </span>
      </label>
    `;
  }

  const inputType = field.type === "number" ? "number" : "text";
  const value = field.value == null ? "" : String(field.value);
  return `
    <label class="account-action-field" for="${fieldId}">
      <span class="account-action-field-label">${label}</span>
      <span class="account-action-field-control">
        <input
          id="${fieldId}"
          class="setting-input"
          type="${inputType}"
          data-action-id="${actionId}"
          data-field-key="${fieldKey}"
          data-field-type="${escapeHtml(field.type || "text")}"
          value="${escapeHtml(value)}"
          ${disabled ? "disabled" : ""}
        >
      </span>
    </label>
  `;
}

function readAccountActionFieldValue(input) {
  const fieldType = input.getAttribute("data-field-type") || "text";
  if (fieldType === "boolean") {
    return input.checked;
  }
  if (fieldType === "number") {
    const text = input.value.trim();
    if (!text) return "";
    const number = Number(text);
    return Number.isFinite(number) ? number : text;
  }
  return input.value;
}

function collectAccountActionPayload(actionId) {
  const fields = {};
  document
    .querySelectorAll(`[data-action-id="${CSS.escape(String(actionId))}"][data-field-key]`)
    .forEach((input) => {
      const key = input.getAttribute("data-field-key");
      if (!key) return;
      fields[key] = readAccountActionFieldValue(input);
    });
  const activeToggle = document.querySelector(
    `input[type="checkbox"][data-action-active="${CSS.escape(String(actionId))}"]`,
  );
  return {
    isActive: activeToggle ? activeToggle.checked : undefined,
    fields,
  };
}

async function saveAccountAction(actionId) {
  if (accountActionsLocked() || accountActionBusyIds.has(String(actionId))) return;

  const payload = collectAccountActionPayload(actionId);
  accountActionBusyIds.add(String(actionId));
  renderAccountActions(currentAccountActions);
  setAccountPageStatus("Saving action…", "pending");

  try {
    const response = await fetch(
      `/api/profile/accounts/${encodeURIComponent(selectedAccountId)}/actions/${encodeURIComponent(actionId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail || body.message || response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    const updated = body.action;
    if (updated) {
      currentAccountActions = currentAccountActions.map((action) =>
        String(action.id) === String(actionId) ? updated : action,
      );
    }
    if (Array.isArray(body.switchNameHistory)) {
      currentSwitchNameHistory = body.switchNameHistory;
    }
    renderAccountActions(currentAccountActions);
    setAccountPageStatus(body.message || "Action saved.", body.requiresRestart ? "warn" : "ok");
    els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    setAccountPageStatus(error.message || "Failed to save action.", "error");
    renderAccountActions(currentAccountActions);
  } finally {
    accountActionBusyIds.delete(String(actionId));
    renderAccountActions(currentAccountActions);
  }
}

function renderAccountActions(actions = []) {
  if (!els.accountActionsList) return;
  currentAccountActions = Array.isArray(actions) ? actions : [];
  if (!currentAccountActions.length) {
    els.accountActionsList.innerHTML = `<p class="settings-loading">No actions configured for this account.</p>`;
    return;
  }

  const locked = accountActionsLocked();
  const html = currentAccountActions
    .map((action) => {
      const actionId = String(action.id);
      const busy = accountActionBusyIds.has(actionId);
      const disabled = locked || busy;
      const badgeClass = action.isActive ? "on" : "off";
      const badgeLabel = action.isActive ? "On" : "Off";
      const scheduleMeta = renderScheduleMeta(action.schedule);
      const scheduleRules = renderScheduleRulesBlock(action);
      const lastUsed = renderActionLastUsed(action.schedule);
      const hasSchedule = Number(action.schedule?.rulesCount || 0) > 0;
      const fields = Array.isArray(action.fields) ? action.fields : [];
      const fieldRows = fields
        .map((field) => renderAccountActionField(action, field))
        .join("");
      const fieldsBlock = fieldRows
        ? `<div class="account-action-fields">${fieldRows}</div>`
        : `<p class="account-action-empty">No configurable fields for this action.</p>`;

      return `
        <article class="account-action-card${locked ? " is-disabled" : ""}" data-action-id="${escapeHtml(actionId)}">
          <header class="account-action-head">
            <label class="account-action-active-toggle account-action-toggle-main">
              <input
                type="checkbox"
                data-action-active="${escapeHtml(actionId)}"
                ${action.isActive ? "checked" : ""}
                ${disabled ? "disabled" : ""}
              >
              <span class="account-action-badge ${badgeClass}">${badgeLabel}</span>
            </label>
            <div class="account-action-title-wrap">
              <h3 class="account-action-title">${escapeHtml(action.title || action.scriptId || "Action")}</h3>
              ${hasSchedule ? `<span class="account-action-schedule-icon" title="Has schedule rules">⏱</span>` : ""}
            </div>
            <span class="account-action-last-used">${escapeHtml(lastUsed)}</span>
            ${scheduleMeta ? `<span class="account-action-meta">${escapeHtml(scheduleMeta)}</span>` : ""}
          </header>
          ${scheduleRules}
          ${fieldsBlock}
          <footer class="account-action-footer">
            <button
              type="button"
              class="btn btn-small account-action-save"
              data-save-action-id="${escapeHtml(actionId)}"
              ${disabled ? "disabled" : ""}
            >${busy ? "Saving…" : "Save action"}</button>
          </footer>
        </article>
      `;
    })
    .join("");

  els.accountActionsList.innerHTML = html;
  applyAccountLockState();
}

async function loadProfileAccounts() {
  if (!els.accountSelect) return;
  setAccountPageStatus("Loading accounts…", "pending");
  els.accountSelect.disabled = true;
  showAccountDetailPanels(false);
  try {
    const response = await fetch("/api/profile/accounts");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || "Could not load profile accounts.");
    }
    profileAccounts = Array.isArray(body.accounts) ? body.accounts : [];
    accountActionsWritable = body.writable !== false;
    profileEditLocked = body.writable === false;
    botActive = Boolean(body.botActive);
    applyAccountLockState();
    renderAccountSelectOptions();
    updateAccountSettingsMeta(body.profile || "");
    await loadProfileTemplates();
    if (selectedAccountId) {
      await loadAccountActions(selectedAccountId, body.profile || "");
    } else {
      renderAccountActions([]);
      currentAccountAdvanced = null;
      renderAccountAdvancedPanel(null);
      if (els.accountActionsList) {
        els.accountActionsList.innerHTML = `<p class="settings-loading">No accounts found in this profile.</p>`;
      }
      setAccountPageStatus("No accounts found.", "warn");
    }
  } catch (error) {
    profileAccounts = [];
    if (els.accountSelect) {
      els.accountSelect.innerHTML = `<option value="">Failed to load accounts</option>`;
      els.accountSelect.disabled = true;
    }
    if (els.accountActionsList) {
      els.accountActionsList.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load accounts.")}</p>`;
    }
    setAccountPageStatus("");
  }
  scheduleSettingsActivityPoll();
}

async function loadAccountActions(accountId, profileName = "") {
  if (!accountId || accountActionsBusy) return;
  accountActionsBusy = true;
  setAccountPageStatus("Loading actions…", "pending");
  if (els.accountActionsList) {
    els.accountActionsList.innerHTML = `<p class="settings-loading">Loading actions…</p>`;
  }
  try {
    const response = await fetch(`/api/profile/accounts/${encodeURIComponent(accountId)}/actions`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || "Could not load account actions.");
    }
    const account = body.account || {};
    accountActionsWritable = body.writable !== false && body.readOnly !== true;
    applyAccountLockState();
    showAccountDetailPanels(true);
    currentAccountAdvanced = account.advanced || null;
    currentSwitchNameHistory = Array.isArray(account.switchNameHistory)
      ? account.switchNameHistory
      : [];
    renderAccountAdvancedPanel(currentAccountAdvanced);
    renderAccountActions(account.actions || []);
    updateAccountSettingsMeta(profileName || body.profile || "");
    const count = (account.actions || []).length;
    const activeCount = (account.actions || []).filter((item) => item.isActive).length;
    const scheduledCount = (account.actions || []).filter(
      (item) => Number(item.schedule?.rulesCount || item.schedule?.rules?.length || 0) > 0,
    ).length;
    const scheduleNote =
      scheduledCount > 0
        ? ` · ${scheduledCount} action${scheduledCount === 1 ? "" : "s"} with schedule rules`
        : "";
    const modeLabel = accountActionsLocked() ? "read-only" : "editable";
    setAccountPageStatus(
      `${account.name || "Account"}: ${activeCount} of ${count} actions enabled (${modeLabel})${scheduleNote}.`,
      accountActionsLocked() ? "warn" : "ok",
    );
  } catch (error) {
    if (els.accountActionsList) {
      els.accountActionsList.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load actions.")}</p>`;
    }
    setAccountPageStatus("");
  } finally {
    accountActionsBusy = false;
  }
}

function setPageStatus(message, tone = "") {
  if (!els.pageStatus) return;
  els.pageStatus.textContent = message || "";
  els.pageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function setGnbotsStatus(online, options = {}) {
  gnbotsOnline = online;
  if (!els.gnbotsStatus) return;
  if (online && options.writable === false) {
    els.gnbotsStatus.textContent = "GnBots running · API busy";
    els.gnbotsStatus.className = "status-pill warn";
    return;
  }
  els.gnbotsStatus.textContent = online ? "GnBots online" : "GnBots offline";
  els.gnbotsStatus.className = `status-pill ${online ? "online" : "offline"}`;
}

function schemaKeys() {
  const keys = new Set();
  for (const group of SETTINGS_GROUPS) {
    for (const field of group.fields) {
      keys.add(field.key);
    }
  }
  return keys;
}

function renderField(groupId, field) {
  const value = currentSettings[field.key];
  const disabled = settingsLocked() || field.readOnly || busyKeys.has(field.key);
  const fieldId = `setting-${groupId}-${field.key}`;

  if (field.type === "boolean") {
    const checked = parseStoredBoolean(value);
    return `
      <label class="setting-field setting-field-boolean" for="${fieldId}">
        <span class="setting-label">
          <span class="setting-name">${field.label}</span>
          <code class="setting-key">${field.key}</code>
          ${field.hint ? `<span class="setting-hint">${field.hint}</span>` : ""}
        </span>
        <span class="setting-control">
          <input id="${fieldId}" type="checkbox" data-key="${field.key}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}>
          <button class="btn btn-small setting-save" type="button" data-key="${field.key}" ${disabled ? "disabled" : ""}>Save</button>
        </span>
      </label>
    `;
  }

  if (field.type === "profile") {
    const current = formatValue(value);
    const options = [...new Set([...profileNames, current].filter(Boolean))].sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" }),
    );
    const optionHtml = options
      .map((name) => {
        const selected = name === current ? " selected" : "";
        return `<option value="${escapeHtml(name)}"${selected}>${escapeHtml(name)}</option>`;
      })
      .join("");
    return `
      <div class="setting-field">
        <label class="setting-label" for="${fieldId}">
          <span class="setting-name">${field.label}</span>
          <code class="setting-key">${field.key}</code>
          ${field.hint ? `<span class="setting-hint">${field.hint}</span>` : ""}
        </label>
        <div class="setting-control">
          <select id="${fieldId}" class="setting-select" data-key="${field.key}" ${disabled ? "disabled" : ""}>
            ${optionHtml || `<option value="">No profiles found</option>`}
          </select>
          <button class="btn btn-small setting-save" type="button" data-key="${field.key}" ${disabled ? "disabled" : ""}>Save</button>
        </div>
      </div>
    `;
  }

  if (field.type === "select") {
    const current = formatValue(value);
    const options = (field.options || []).map((name) => {
      const selected = String(name) === current ? " selected" : "";
      return `<option value="${escapeHtml(name)}"${selected}>${escapeHtml(name)}</option>`;
    }).join("");
    return `
      <div class="setting-field">
        <label class="setting-label" for="${fieldId}">
          <span class="setting-name">${field.label}</span>
          <code class="setting-key">${field.key}</code>
          ${field.hint ? `<span class="setting-hint">${field.hint}</span>` : ""}
        </label>
        <div class="setting-control">
          <select id="${fieldId}" class="setting-select" data-key="${field.key}" ${disabled ? "disabled" : ""}>${options}</select>
          <button class="btn btn-small setting-save" type="button" data-key="${field.key}" ${disabled ? "disabled" : ""}>Save</button>
        </div>
      </div>
    `;
  }

  const inputType = field.type === "number" ? "number" : "text";
  const attrs = [
    `id="${fieldId}"`,
    `class="setting-input"`,
    `type="${inputType}"`,
    `data-key="${field.key}"`,
    `value="${escapeHtml(formatValue(value))}"`,
    disabled ? "disabled" : "",
    field.placeholder ? `placeholder="${escapeHtml(field.placeholder)}"` : "",
    field.min !== undefined ? `min="${field.min}"` : "",
    field.max !== undefined ? `max="${field.max}"` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return `
    <div class="setting-field">
      <label class="setting-label" for="${fieldId}">
        <span class="setting-name">${field.label}</span>
        <code class="setting-key">${field.key}</code>
        ${field.hint ? `<span class="setting-hint">${field.hint}</span>` : ""}
        ${field.readOnly ? `<span class="setting-hint">Read-only in the monitor UI.</span>` : ""}
      </label>
      <div class="setting-control">
        <input ${attrs}>
        <button class="btn btn-small setting-save" type="button" data-key="${field.key}" ${disabled ? "disabled" : ""}>Save</button>
      </div>
    </div>
  `;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderEmulatorStatusBanner() {
  const uid = formatValue(currentSettings.LastSelectedEmulatorUID).toLowerCase();
  const label = formatValue(currentSettings.Emulator);
  const activeName = EMULATOR_UID_LABELS[uid] || (uid ? uid : "Not set");
  const expectedLabel = EMULATOR_LABEL_FOR_UID[uid] || "";
  const mismatch = Boolean(expectedLabel && label && label !== expectedLabel);

  return `
    <div class="setting-profile-status${mismatch ? " mismatch" : ""}">
      <div class="setting-profile-status-main">
        <span class="setting-profile-status-label">Active emulator</span>
        <span class="setting-profile-status-value">${escapeHtml(activeName)}</span>
      </div>
      ${
        mismatch
          ? `<p class="setting-hint">Emulator label is <strong>${escapeHtml(label)}</strong> but UID <code>${escapeHtml(uid)}</code> expects <strong>${escapeHtml(expectedLabel)}</strong>. Save the corrected label and restart GnBots.</p>`
          : `<p class="setting-hint">UID <code>${escapeHtml(uid || "—")}</code> matches label <strong>${escapeHtml(label || "—")}</strong>.</p>`
      }
    </div>
  `;
}

function renderProfileInUseBanner() {
  const inUse = profileInUse || currentSettings.SelectedProfile || "—";
  const saved = configuredProfile || currentSettings.SelectedProfile || "";
  const live = runtimeProfile || "";
  const mismatch = Boolean(live && saved && live !== saved);

  return `
    <div class="setting-profile-status${mismatch ? " mismatch" : ""}">
      <div class="setting-profile-status-main">
        <span class="setting-profile-status-label">Profile in use</span>
        <span class="setting-profile-status-value">${escapeHtml(inUse)}</span>
      </div>
      ${
        mismatch
          ? `<p class="setting-hint">Saved selection is <span class="setting-profile-status-value">${escapeHtml(saved)}</span>. Restart GnBots to switch the active profile.</p>`
          : `<p class="setting-hint">Matches the active profile after restart. Change below, save, then restart GnBots.</p>`
      }
    </div>
  `;
}

function renderGroups() {
  if (!els.settingsGroups) return;

  const html = SETTINGS_GROUPS.map((group) => {
    const fields = group.fields
      .map((field) => renderField(group.id, field))
      .join("");
    const profileBanner = group.id === "run" ? renderProfileInUseBanner() : "";
    const emulatorBanner = group.id === "emulator" ? renderEmulatorStatusBanner() : "";
    return `
      <section class="panel settings-group" data-group="${group.id}">
        <div class="panel-head">
          <div>
            <h2>${group.title}</h2>
            <p class="settings-group-desc">${group.description}</p>
          </div>
        </div>
        <div class="settings-fields">${profileBanner}${emulatorBanner}${fields}</div>
      </section>
    `;
  }).join("");

  els.settingsGroups.innerHTML = html;
  bindFieldActions();
}

function renderRawSettings() {
  if (!els.settingsRaw) return;
  const visible = Object.fromEntries(
    Object.entries(currentSettings).filter(([key]) => !HIDDEN_KEYS.has(key.toLowerCase())),
  );
  const known = schemaKeys();
  const extra = Object.keys(visible)
    .filter((key) => !known.has(key))
    .sort();
  const payload = { ...visible };
  if (extra.length) {
    payload._extraKeys = extra;
  }
  els.settingsRaw.textContent = JSON.stringify(payload, null, 2);
}

function fieldMeta(key) {
  for (const group of SETTINGS_GROUPS) {
    const field = group.fields.find((item) => item.key === key);
    if (field) return field;
  }
  return null;
}

function readFieldValue(key) {
  const meta = fieldMeta(key);
  const checkbox = document.querySelector(`input[type="checkbox"][data-key="${key}"]`);
  if (checkbox) {
    return checkbox.checked ? "true" : "false";
  }
  const select = document.querySelector(`select.setting-select[data-key="${key}"]`);
  if (select) {
    return select.value.trim();
  }
  const input = document.querySelector(`input.setting-input[data-key="${key}"]`);
  if (!input) return "";
  const raw = input.value.trim();
  if (meta?.type === "number" && raw !== "") {
    const num = Number(raw);
    if (Number.isNaN(num)) {
      throw new Error(`${meta.label} must be a number.`);
    }
    if (meta.min !== undefined && num < meta.min) {
      throw new Error(`${meta.label} must be at least ${meta.min}.`);
    }
    if (meta.max !== undefined && num > meta.max) {
      throw new Error(`${meta.label} must be at most ${meta.max}.`);
    }
    return String(num);
  }
  return raw;
}

async function saveSetting(key) {
  const meta = fieldMeta(key);
  if (!meta || meta.readOnly) return;

  let value;
  try {
    value = readFieldValue(key);
  } catch (error) {
    setPageStatus(error.message || "Invalid value.", "error");
    return;
  }

  busyKeys.add(key);
  renderGroups();
  setPageStatus(`Saving ${key}…`, "pending");

  try {
    const response = await fetch(
      `/api/settings/${encodeURIComponent(key)}/update?value=${encodeURIComponent(value)}`,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail || body.error || response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (body.data === "Error") {
      throw new Error(`GnBots rejected the update to ${key}.`);
    }

    if (body.value !== undefined) {
      currentSettings[key] = body.value;
    } else if (meta.type === "boolean") {
      currentSettings[key] = value === "true";
    } else if (meta.type === "number") {
      currentSettings[key] = Number(value);
    } else {
      currentSettings[key] = value;
    }

    setPageStatus(
      body.message || `Saved ${key}. Restart GnBots to apply.`,
      "warn",
    );
    renderRawSettings();
    if (key === "SelectedProfile") {
      await loadSettings();
      return;
    }
  } catch (error) {
    setPageStatus(error.message || `Failed to save ${key}.`, "error");
  } finally {
    busyKeys.delete(key);
    if (key !== "SelectedProfile") {
      renderGroups();
    }
    els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }
}

function bindFieldActions() {
  document.querySelectorAll(".setting-save").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-key");
      if (key) saveSetting(key);
    });
  });

  document.querySelectorAll(".setting-input").forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        const key = input.getAttribute("data-key");
        if (key) saveSetting(key);
      }
    });
  });
}

async function loadProfiles(settingsBody = null) {
  const apply = (names) => {
    if (Array.isArray(names) && names.length) {
      profileNames = names;
      return true;
    }
    return false;
  };

  const sources = [
    async () => {
      const response = await fetch("/api/profiles", { cache: "no-store" });
      if (!response.ok) return null;
      const body = await response.json().catch(() => ({}));
      return body.profiles;
    },
    async () => settingsBody?.profiles ?? null,
    async () => window.GNBOTS_PROFILES ?? null,
    async () => {
      const response = await fetch("/static/profiles.json", { cache: "no-store" });
      if (!response.ok) return null;
      const body = await response.json().catch(() => ({}));
      return body.profiles;
    },
  ];

  for (const source of sources) {
    try {
      if (await apply(await source())) {
        return;
      }
    } catch {
      // try next source
    }
  }
}

async function restartGnBots() {
  if (restartBusy) return;
  if (
    !window.confirm(
      "Restart GnBots? This stops the bot, closes GnBots.exe, waits a few seconds, then launches it again.",
    )
  ) {
    return;
  }

  restartBusy = true;
  if (els.restartGnBotsBtn) {
    els.restartGnBotsBtn.disabled = true;
  }
  setPageStatus("Restarting GnBots…", "pending");

  try {
    const response = await fetch("/api/host/gnbots/restart", { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.message || `HTTP ${response.status}`);
    }
    setPageStatus(body.message || "GnBots restarted.", "ok");
    await loadSettings();
  } catch (error) {
    setPageStatus(error.message || "Failed to restart GnBots.", "error");
  } finally {
    restartBusy = false;
    if (els.restartGnBotsBtn) {
      els.restartGnBotsBtn.disabled = false;
    }
  }
}

async function loadSettings() {
  if (activeSettingsTab === "monitor") {
    await loadMonitorConfig();
    return;
  }
  if (activeSettingsTab === "restore") {
    await loadRestoreTab();
    return;
  }
  if (activeSettingsTab === "provision") {
    await loadProvisionTab();
    return;
  }
  setPageStatus("Loading settings…", "pending");
  try {
    const settingsRes = await fetch("/api/settings");
    const body = await settingsRes.json().catch(() => ({}));
    if (!settingsRes.ok) {
      throw new Error(
        typeof body.detail === "string" ? body.detail : "Could not load settings from GnBots.",
      );
    }

    await loadProfiles(body);

    profileInUse = body.profileInUse || "";
    configuredProfile = body.configuredProfile || "";
    runtimeProfile = body.runtimeProfile || "";
    botActive = Boolean(body.botActive);
    botState = body.botState || "";
    currentSettings = body.settings || {};
    settingsWritable = body.writable !== false;
    profileEditLocked = body.writable === false;
    setGnbotsStatus(body.gnbotsOnline !== false, { writable: settingsWritable });
    applySettingsLockState();
    if (activeSettingsTab === "restore") {
      applyRestoreLockState();
    }
    renderGroups();
    renderRawSettings();

    if (body.warning) {
      if (body.gnbotsOnline === false && body.writable !== false) {
        setPageStatus(
          "GnBots is offline — showing saved config. You can edit now; restart GnBots after saving.",
          "ok",
        );
      } else {
        setPageStatus(body.warning, "warn");
      }
    } else if (settingsLocked()) {
      setPageStatus("Settings are read-only while bot sessions are running. Stop the bot to edit.", "warn");
    } else if (body.gnbotsOnline !== false) {
      const source = body.source ? ` (${body.source})` : "";
      setPageStatus(`Settings loaded${source}. Stop the bot before editing; restart GnBots after saving.`, "ok");
    } else {
      setPageStatus("GnBots is offline — you can edit settings before the next launch.", "ok");
    }
    els.lastUpdated.textContent = `Loaded ${new Date().toLocaleTimeString()}`;

    if (activeSettingsTab === "accounts") {
      applyAccountLockState();
      await loadProfileAccounts();
    }
    if (activeSettingsTab === "names") {
      await loadAccountNamesTab();
    }
    if (activeSettingsTab === "bulk") {
      await loadBulkActionsTab();
    }
    scheduleSettingsActivityPoll();
  } catch (error) {
    setGnbotsStatus(false);
    if (els.settingsGroups) {
      els.settingsGroups.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load settings.")}</p>`;
    }
    setPageStatus("");
  }
}

els.refreshBtn?.addEventListener("click", () => {
  if (activeSettingsTab === "accounts") {
    loadProfileAccounts();
    return;
  }
  if (activeSettingsTab === "names") {
    loadAccountNamesTab();
    return;
  }
  if (activeSettingsTab === "bulk") {
    loadBulkActionsTab();
    return;
  }
  if (activeSettingsTab === "provision") {
    loadProvisionTab();
    return;
  }
  if (activeSettingsTab === "restore") {
    loadRestoreTab({ forceApk: true });
    return;
  }
  if (activeSettingsTab === "monitor") {
    loadMonitorConfig();
    return;
  }
  loadSettings();
});

els.restartGnBotsBtn?.addEventListener("click", () => restartGnBots());

els.provisionForm?.addEventListener("submit", (event) => startProvisionAccount(event));

els.settingsTabs?.forEach((button) => {
  button.addEventListener("click", () => {
    const tabId = button.dataset.tab;
    if (!tabId || tabId === activeSettingsTab) return;
    setActiveSettingsTab(tabId);
    if (tabId === "accounts") {
      loadProfileAccounts();
    } else if (tabId === "names") {
      loadAccountNamesTab();
    } else if (tabId === "provision") {
      loadProvisionTab();
    } else if (tabId === "restore") {
      loadRestoreTab();
    } else if (tabId === "monitor") {
      loadMonitorConfig();
    }
  });
});

els.accountSelect?.addEventListener("change", (event) => {
  selectedAccountId = event.target.value;
  if (selectedAccountId) {
    loadAccountActions(selectedAccountId);
  }
});

els.accountActionsList?.addEventListener("click", (event) => {
  const saveButton = event.target.closest("[data-save-action-id]");
  if (saveButton && !saveButton.disabled) {
    const actionId = saveButton.getAttribute("data-save-action-id");
    if (actionId) {
      void saveAccountAction(actionId);
    }
    return;
  }

  const saveScheduleButton = event.target.closest("[data-save-schedule-id]");
  if (saveScheduleButton && !saveScheduleButton.disabled) {
    const actionId = saveScheduleButton.getAttribute("data-save-schedule-id");
    if (actionId) {
      void saveAccountScheduleRules(actionId);
    }
    return;
  }

  const resetScheduleButton = event.target.closest("[data-reset-schedule-id]");
  if (resetScheduleButton && !resetScheduleButton.disabled) {
    const actionId = resetScheduleButton.getAttribute("data-reset-schedule-id");
    if (actionId) {
      void saveAccountScheduleRules(actionId, { resetTimers: true });
    }
    return;
  }

  const addScheduleButton = event.target.closest(".account-schedule-add");
  if (addScheduleButton && !addScheduleButton.disabled) {
    const actionId = addScheduleButton.getAttribute("data-action-id");
    const kindSelect = document.querySelector(
      `.account-schedule-kind[data-action-id="${CSS.escape(String(actionId || ""))}"]`,
    );
    const kind = kindSelect?.value || "wait_after";
    if (actionId) {
      addScheduleRuleToAction(actionId, kind);
    }
    return;
  }

  const deleteScheduleButton = event.target.closest(".account-schedule-delete");
  if (deleteScheduleButton && !deleteScheduleButton.disabled) {
    const actionId = deleteScheduleButton.getAttribute("data-action-id");
    const ruleIndex = deleteScheduleButton.getAttribute("data-rule-index");
    if (actionId && ruleIndex != null) {
      removeScheduleRuleFromAction(actionId, ruleIndex);
    }
    return;
  }

  const switchNameButton = event.target.closest(".account-switch-name-pick");
  if (switchNameButton && !switchNameButton.disabled) {
    const actionId = switchNameButton.getAttribute("data-action-id");
    const switchName = switchNameButton.getAttribute("data-switch-name");
    if (!actionId || !switchName) return;
    const input = document.querySelector(
      `.account-switch-name-input[data-action-id="${CSS.escape(String(actionId))}"]`,
    );
    if (input) {
      input.value = switchName;
      input.focus();
    }
  }
});

els.accountAdvancedBody?.addEventListener("click", (event) => {
  if (event.target.closest("#account-advanced-save")) {
    void saveAccountAdvancedSettings();
  }
});

els.accountTemplateSelect?.addEventListener("change", (event) => {
  updateAccountTemplateDescription(event.target.value);
});

els.accountTemplateApply?.addEventListener("click", () => {
  void applyAccountTemplate();
});

els.accountTemplateCreate?.addEventListener("click", () => {
  void createAccountTemplate();
});

els.accountTemplateRemove?.addEventListener("click", () => {
  void removeAccountTemplate();
});

els.accountNamesSaveAll?.addEventListener("click", () => {
  void saveAllSwitchNames();
});

els.accountNamesList?.addEventListener("click", (event) => {
  const removeBtn = event.target.closest(".account-names-history-remove");
  if (removeBtn) {
    event.preventDefault();
    event.stopPropagation();
    const accountId = removeBtn.getAttribute("data-account-id");
    const switchName = removeBtn.getAttribute("data-switch-name");
    if (accountId && switchName) {
      void removeSwitchNameHistory(accountId, switchName);
    }
    return;
  }

  const chip = event.target.closest(".account-names-chip");
  if (!chip || chip.disabled) return;
  const accountId = chip.getAttribute("data-account-id");
  const switchName = chip.getAttribute("data-switch-name");
  if (accountId && switchName) {
    setSwitchNameInputValue(accountId, switchName);
  }
});

els.accountNamesList?.addEventListener("change", (event) => {
  const select = event.target.closest(".account-names-recent-select");
  if (!select || select.disabled || !select.value) return;
  const accountId = select.getAttribute("data-account-id");
  if (accountId) {
    setSwitchNameInputValue(accountId, select.value);
    select.value = "";
  }
});

els.bulkActionSelect?.addEventListener("change", (event) => {
  bulkSelectedScriptSuffix = event.target.value || "";
  bulkSelectedFieldKey = "";
  bulkFieldRows = [];
  bulkFieldMeta = null;
  bulkSelectedAccountIds = new Set();
  renderBulkFieldSelectOptions();
  renderBulkActionFieldList();
});

els.bulkFieldSelect?.addEventListener("change", (event) => {
  bulkSelectedFieldKey = event.target.value || "";
  if (!bulkSelectedFieldKey) {
    bulkFieldRows = [];
    bulkFieldMeta = null;
    bulkSelectedAccountIds = new Set();
    renderBulkActionFieldList();
    return;
  }
  void loadBulkActionFieldRows();
});

els.bulkApplySelectedBtn?.addEventListener("click", () => {
  applyBulkValueToSelected();
});

els.bulkSelectAllBtn?.addEventListener("click", () => {
  bulkSelectedAccountIds = new Set(bulkFieldRows.map((row) => String(row.accountId)));
  renderBulkActionFieldList();
});

els.bulkSelectNoneBtn?.addEventListener("click", () => {
  bulkSelectedAccountIds = new Set();
  renderBulkActionFieldList();
});

els.bulkSaveSelectedBtn?.addEventListener("click", () => {
  void saveBulkActionFields();
});

els.bulkActionsList?.addEventListener("change", (event) => {
  const checkbox = event.target.closest(".bulk-account-select");
  if (!checkbox) return;
  const accountId = checkbox.getAttribute("data-account-id");
  if (!accountId) return;
  if (checkbox.checked) {
    bulkSelectedAccountIds.add(accountId);
  } else {
    bulkSelectedAccountIds.delete(accountId);
  }
  applyBulkActionsLockState();
});

document.addEventListener("click", (event) => {
  const addBtn = event.target.closest(".bulk-schedule-add");
  if (addBtn && !addBtn.disabled) {
    const scope = addBtn.getAttribute("data-bulk-schedule-scope");
    if (scope) bulkScheduleAddRule(scope);
    return;
  }
  const deleteBtn = event.target.closest(".bulk-schedule-delete");
  if (deleteBtn && !deleteBtn.disabled) {
    const scope = deleteBtn.getAttribute("data-bulk-schedule-scope");
    const ruleIndex = deleteBtn.getAttribute("data-rule-index");
    if (scope != null && ruleIndex != null) bulkScheduleDeleteRule(scope, ruleIndex);
  }
});

els.toggleAdvancedBtn?.addEventListener("click", () => {
  const raw = els.settingsRaw;
  if (!raw) return;
  const show = raw.classList.contains("hidden");
  raw.classList.toggle("hidden", !show);
  els.toggleAdvancedBtn.textContent = show ? "Hide raw JSON" : "Show raw JSON";
  els.toggleAdvancedBtn.setAttribute("aria-expanded", show ? "true" : "false");
});

function formatLdHealthResolution(summary) {
  if (!summary || typeof summary !== "object") return "";
  const width = summary.ld_health_width;
  const height = summary.ld_health_height;
  const dpi = summary.ld_health_dpi;
  if (width == null || height == null || dpi == null) return "";
  return `${width}×${height} @ ${dpi} DPI`;
}

function ldHealthGroupHeaderHtml() {
  const effective = formatLdHealthResolution(ldHealthEffective);
  const defaults = formatLdHealthResolution(ldHealthDefaults);
  const usingDefaults = parseStoredBoolean(ldHealthEffective.ld_health_use_defaults);
  const effectiveLine = effective
    ? `<p class="ld-health-effective">Effective: <strong>${escapeHtml(effective)}</strong>${
        usingDefaults ? " (GnBots defaults)" : " (custom overrides)"
      }</p>`
    : "";
  const defaultsLine = defaults
    ? `<p class="setting-hint ld-health-defaults-hint">Built-in defaults: ${escapeHtml(defaults)}</p>`
    : "";
  return `
    <div class="ld-health-group-note">
      <p class="setting-hint">
        Applied by <strong>Fix settings</strong> on the Restore tab and by the post-restore health check
        when enabled. Requires Administrator elevation to commit LDPlayer config.
      </p>
      ${effectiveLine}
      ${defaultsLine}
      <button class="btn btn-small ld-health-reset-btn" type="button" id="ld-health-reset-btn">
        Reset to defaults
      </button>
    </div>
  `;
}

function monitorFieldMeta(key) {
  for (const group of monitorGroups) {
    const field = (group.fields || []).find((item) => item.key === key);
    if (field) return field;
  }
  return null;
}

function monitorFieldEffectiveNote(field) {
  if (field.key !== "ldplayer_path") return "";
  const override = String(currentMonitorConfig.ldplayer_path || "").trim();
  const resolved = String(monitorResolvedPaths.ldplayer_path || "").trim();
  if (override || !resolved) return "";
  return `<span class="setting-effective">Using GnBots <code>LDPath64</code>: <code>${escapeHtml(resolved)}</code></span>`;
}

function renderMonitorField(groupId, field) {
  const value = currentMonitorConfig[field.key];
  const disabled = field.readOnly || monitorBusyKeys.has(field.key) || monitorFieldAdminLocked(field);
  const adminNote = monitorFieldAdminLocked(field)
    ? `<span class="setting-hint requires-admin-hint">Requires Administrator elevation.</span>`
    : "";
  const fieldId = `monitor-setting-${groupId}-${field.key}`;
  const effectiveNote = monitorFieldEffectiveNote(field);

  if (field.type === "boolean") {
    const checked = parseStoredBoolean(value);
    return `
      <label class="setting-field setting-field-boolean" for="${fieldId}">
        <span class="setting-label">
          <span class="setting-name">${field.label}</span>
          <code class="setting-key">${field.key}</code>
          ${field.hint ? `<span class="setting-hint">${field.hint}</span>` : ""}
          ${adminNote}
          ${effectiveNote}
        </span>
        <span class="setting-control">
          <input id="${fieldId}" type="checkbox" data-monitor-key="${field.key}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}>
          <button class="btn btn-small monitor-setting-save" type="button" data-monitor-key="${field.key}" ${disabled ? "disabled" : ""}>Save</button>
        </span>
      </label>
    `;
  }

  if (field.type === "select") {
    const current = formatValue(value).toLowerCase();
    const options = (field.options || []).map((name) => {
      const selected = String(name).toLowerCase() === current ? " selected" : "";
      return `<option value="${escapeHtml(name)}"${selected}>${escapeHtml(name)}</option>`;
    }).join("");
    return `
      <div class="setting-field">
        <label class="setting-label" for="${fieldId}">
          <span class="setting-name">${field.label}</span>
          <code class="setting-key">${field.key}</code>
          ${field.hint ? `<span class="setting-hint">${field.hint}</span>` : ""}
          ${adminNote}
          ${effectiveNote}
        </label>
        <div class="setting-control">
          <select id="${fieldId}" class="setting-select" data-monitor-key="${field.key}" ${disabled ? "disabled" : ""}>${options}</select>
          <button class="btn btn-small monitor-setting-save" type="button" data-monitor-key="${field.key}" ${disabled ? "disabled" : ""}>Save</button>
        </div>
      </div>
    `;
  }

  const inputType = field.type === "number" ? "number" : "text";
  const attrs = [
    `id="${fieldId}"`,
    `class="setting-input"`,
    `type="${inputType}"`,
    `data-monitor-key="${field.key}"`,
    `value="${escapeHtml(formatValue(value))}"`,
    disabled ? "disabled" : "",
    field.placeholder ? `placeholder="${escapeHtml(field.placeholder)}"` : "",
    field.min !== undefined ? `min="${field.min}"` : "",
    field.max !== undefined ? `max="${field.max}"` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return `
    <div class="setting-field">
      <label class="setting-label" for="${fieldId}">
        <span class="setting-name">${field.label}</span>
        <code class="setting-key">${field.key}</code>
        ${field.hint ? `<span class="setting-hint">${field.hint}</span>` : ""}
        ${adminNote}
        ${effectiveNote}
      </label>
      <div class="setting-control">
        <input ${attrs}>
        <button class="btn btn-small monitor-setting-save" type="button" data-monitor-key="${field.key}" ${disabled ? "disabled" : ""}>Save</button>
      </div>
    </div>
  `;
}

function renderMonitorGroups() {
  if (!els.monitorSettingsGroups) return;
  if (!monitorGroups.length) {
    els.monitorSettingsGroups.innerHTML = `<p class="settings-loading">No monitor settings schema found.</p>`;
    return;
  }

  const html = monitorGroups
    .map((group) => {
      const fields = (group.fields || []).map((field) => renderMonitorField(group.id, field)).join("");
      const healthHeader = group.id === "emulator-health" ? ldHealthGroupHeaderHtml() : "";
      return `
        <section class="panel settings-group" data-group="${group.id}">
          <div class="panel-head">
            <div>
              <h2>${group.title}</h2>
              <p class="settings-group-desc">${group.description || ""}</p>
              ${healthHeader}
            </div>
          </div>
          <div class="settings-fields">${fields}</div>
        </section>
      `;
    })
    .join("");

  els.monitorSettingsGroups.innerHTML = html;
  bindMonitorFieldActions();
  document.getElementById("ld-health-reset-btn")?.addEventListener("click", () => {
    void resetLdHealthSettings();
  });
}

function renderMonitorRawSettings() {
  if (!els.monitorSettingsRaw) return;
  els.monitorSettingsRaw.textContent = JSON.stringify(currentMonitorConfig, null, 2);
}

function readMonitorFieldValue(key) {
  const meta = monitorFieldMeta(key);
  const checkbox = document.querySelector(`input[type="checkbox"][data-monitor-key="${key}"]`);
  if (checkbox) {
    return checkbox.checked ? "true" : "false";
  }
  const select = document.querySelector(`select.setting-select[data-monitor-key="${key}"]`);
  if (select) {
    return select.value.trim();
  }
  const input = document.querySelector(`input.setting-input[data-monitor-key="${key}"]`);
  if (!input) return "";
  const raw = input.value.trim();
  if (meta?.type === "number" && raw !== "") {
    const num = Number(raw);
    if (Number.isNaN(num)) {
      throw new Error(`${meta.label} must be a number.`);
    }
    if (meta.min !== undefined && num < meta.min) {
      throw new Error(`${meta.label} must be at least ${meta.min}.`);
    }
    if (meta.max !== undefined && num > meta.max) {
      throw new Error(`${meta.label} must be at most ${meta.max}.`);
    }
    return String(num);
  }
  return raw;
}

async function saveMonitorSetting(key) {
  const meta = monitorFieldMeta(key);
  if (!meta || meta.readOnly) return;

  let value;
  try {
    value = readMonitorFieldValue(key);
  } catch (error) {
    setMonitorPageStatus(error.message || "Invalid value.", "error");
    return;
  }

  monitorBusyKeys.add(key);
  renderMonitorGroups();
  setMonitorPageStatus(`Saving ${key}…`, "pending");

  try {
    const response = await fetch(
      `/api/monitor-config/${encodeURIComponent(key)}/update?value=${encodeURIComponent(value)}`,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail || body.error || response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    if (body.value !== undefined) {
      currentMonitorConfig[key] = body.value;
    } else if (meta.type === "boolean") {
      currentMonitorConfig[key] = value === "true";
    } else if (meta.type === "number") {
      currentMonitorConfig[key] = Number(value);
    } else {
      currentMonitorConfig[key] = value;
    }
    if (body.resolved && typeof body.resolved === "object") {
      monitorResolvedPaths = body.resolved;
    }
    if (body.ldHealthEffective && typeof body.ldHealthEffective === "object") {
      ldHealthEffective = body.ldHealthEffective;
    }
    if (body.config && typeof body.config === "object") {
      currentMonitorConfig = body.config;
    }

    setMonitorPageStatus(body.message || `Saved ${key}.`, body.message?.includes("Restart") ? "warn" : "ok");
    renderMonitorRawSettings();
  } catch (error) {
    setMonitorPageStatus(error.message || `Failed to save ${key}.`, "error");
  } finally {
    monitorBusyKeys.delete(key);
    renderMonitorGroups();
    els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }
}

function bindMonitorFieldActions() {
  document.querySelectorAll(".monitor-setting-save").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-monitor-key");
      if (key) saveMonitorSetting(key);
    });
  });

  document.querySelectorAll("input.setting-input[data-monitor-key]").forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        const key = input.getAttribute("data-monitor-key");
        if (key) saveMonitorSetting(key);
      }
    });
  });
}

async function resetLdHealthSettings() {
  if (monitorBusyKeys.size) return;
  monitorBusyKeys.add("ld_health_use_defaults");
  renderMonitorGroups();
  setMonitorPageStatus("Resetting LDPlayer health settings…", "pending");
  try {
    const response = await fetch(
      `/api/monitor-config/${encodeURIComponent("ld_health_use_defaults")}/update?value=${encodeURIComponent("true")}`,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail || body.error || response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (body.config && typeof body.config === "object") {
      currentMonitorConfig = body.config;
    } else if (ldHealthDefaults && typeof ldHealthDefaults === "object") {
      Object.assign(currentMonitorConfig, ldHealthDefaults);
    }
    if (body.ldHealthEffective && typeof body.ldHealthEffective === "object") {
      ldHealthEffective = body.ldHealthEffective;
    } else if (ldHealthDefaults && typeof ldHealthDefaults === "object") {
      ldHealthEffective = { ...ldHealthDefaults };
    }
    setMonitorPageStatus(body.message || "Reset LDPlayer health settings to defaults.", "ok");
    renderMonitorRawSettings();
  } catch (error) {
    setMonitorPageStatus(error.message || "Failed to reset LDPlayer health settings.", "error");
  } finally {
    monitorBusyKeys.delete("ld_health_use_defaults");
    renderMonitorGroups();
    els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }
}

async function loadMonitorConfig() {
  setMonitorPageStatus("Loading monitor settings…", "pending");
  try {
    const response = await fetch("/api/monitor-config");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || "Could not load monitor config.");
    }

    monitorGroups = Array.isArray(body.groups) ? body.groups : [];
    currentMonitorConfig = body.config || {};
    monitorResolvedPaths = body.resolved || {};
    ldHealthDefaults = body.ldHealthDefaults || {};
    ldHealthEffective = body.ldHealthEffective || {};
    if (body.capabilities) {
      monitorCapabilities = body.capabilities;
      updateRestoreElevationBanner();
    }
    if (els.monitorConfigPath) {
      els.monitorConfigPath.textContent = body.configPath ? `File: ${body.configPath}` : "";
    }

    renderMonitorGroups();
    renderMonitorRawSettings();
    setMonitorPageStatus("Sentinel settings loaded. Save each field individually.", "ok");
    els.lastUpdated.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    monitorGroups = [];
    if (els.monitorSettingsGroups) {
      els.monitorSettingsGroups.innerHTML = `<p class="settings-loading error">${escapeHtml(error.message || "Failed to load monitor settings.")}</p>`;
    }
    setMonitorPageStatus("");
  }
}

els.toggleMonitorRawBtn?.addEventListener("click", () => {
  const raw = els.monitorSettingsRaw;
  if (!raw) return;
  const show = raw.classList.contains("hidden");
  raw.classList.toggle("hidden", !show);
  els.toggleMonitorRawBtn.textContent = show ? "Hide raw JSON" : "Show raw JSON";
  els.toggleMonitorRawBtn.setAttribute("aria-expanded", show ? "true" : "false");
});

els.restoreBackupsSave?.addEventListener("click", () => {
  void saveRestoreBackupsDir();
});

els.restoreBackupsDir?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    void saveRestoreBackupsDir();
  }
});

els.restoreSummaryPanel?.addEventListener("click", async (event) => {
  const restoreAllButton = event.target.closest("#restore-all-btn, .btn-restore-all");
  if (restoreAllButton && restoreAllButton.id === "restore-all-btn" && !restoreAllButton.disabled) {
    await restoreAllTroubled();
    return;
  }

  const updateAllButton = event.target.closest("#update-all-apks-btn, .btn-update-all-apks");
  if (updateAllButton && updateAllButton.id === "update-all-apks-btn" && !updateAllButton.disabled) {
    await updateAllApks();
    return;
  }

  const updateSelectedButton = event.target.closest("#update-selected-apks-btn, .btn-update-selected-apks");
  if (updateSelectedButton && !updateSelectedButton.disabled) {
    await updateSelectedInstanceApks();
    return;
  }

  const forceUpdateSelectedButton = event.target.closest(
    "#force-update-selected-apks-btn, .btn-force-update-selected-apks",
  );
  if (forceUpdateSelectedButton && !forceUpdateSelectedButton.disabled) {
    await forceUpdateSelectedApks();
    return;
  }

  const checkRemoteButton = event.target.closest("#check-remote-apk-btn, .btn-check-remote-apk");
  if (checkRemoteButton && !checkRemoteButton.disabled) {
    await checkRemoteApk({ sync: false });
    return;
  }

  const syncRemoteButton = event.target.closest("#sync-remote-apk-btn, .btn-sync-remote-apk");
  if (syncRemoteButton && !syncRemoteButton.disabled) {
    await checkRemoteApk({ sync: true });
    return;
  }

  const fixAllButton = event.target.closest("#fix-all-settings-btn, .btn-fix-all-settings");
  if (fixAllButton && !fixAllButton.disabled) {
    await fixAllSettings();
  }
});

els.restoreApkAccountList?.addEventListener("change", (event) => {
  const checkbox = event.target.closest(".restore-apk-instance-checkbox");
  if (!checkbox || checkbox.disabled) return;
  const index = Number(checkbox.getAttribute("data-apk-instance-index"));
  if (Number.isNaN(index)) return;
  if (checkbox.checked) {
    apkUpdateSelectedIndexes.add(index);
  } else {
    apkUpdateSelectedIndexes.delete(index);
  }
  renderApkAccountSelection();
  renderRestoreSummary(restoreRows);
  scheduleApkSelectionSave();
});

els.apkSelectActiveBtn?.addEventListener("click", () => {
  const indexes = apkUpdateInstances
    .filter((group) => (group.accounts || []).some((account) => account.active))
    .map((group) => Number(group.index))
    .filter((index) => !Number.isNaN(index) && index >= 0);
  setApkUpdateSelection(indexes);
});

els.apkSelectAllBtn?.addEventListener("click", () => {
  setApkUpdateSelection(
    apkUpdateInstances
      .map((group) => Number(group.index))
      .filter((index) => !Number.isNaN(index) && index >= 0),
  );
});

els.apkSelectNoneBtn?.addEventListener("click", () => {
  setApkUpdateSelection([]);
});

els.restoreInstanceList?.addEventListener("change", async (event) => {
  const select = event.target.closest(".restore-backup-select");
  if (!select || select.disabled) return;
  const index = Number(select.dataset.backupIndex);
  if (Number.isNaN(index)) return;

  const row = restoreRows.find((entry) => entry.index === index);
  const nextValue = select.value.trim();
  const currentManual = row?.backupManualFile || "";
  if ((nextValue || "") === (currentManual || "")) return;

  await saveBackupAssignment(index, nextValue || null);
});

els.restoreInstanceList?.addEventListener("click", async (event) => {
  const updateButton = event.target.closest("[data-update-apk-index]");
  if (updateButton && !updateButton.disabled) {
    const index = Number(updateButton.dataset.updateApkIndex);
    if (!Number.isNaN(index)) {
      await updateApkForIndex(index);
    }
    return;
  }

  const fixButton = event.target.closest("[data-fix-settings-index]");
  if (fixButton && !fixButton.disabled) {
    const index = Number(fixButton.dataset.fixSettingsIndex);
    if (!Number.isNaN(index)) {
      await fixSettingsForIndex(index);
    }
    return;
  }

  const button = event.target.closest("[data-restore-index]");
  if (!button || button.disabled) return;
  const index = Number(button.dataset.restoreIndex);
  if (Number.isNaN(index)) return;
  await runRestoreForIndex(index);
});

els.restoreInstanceList?.addEventListener("toggle", async (event) => {
  const details = event.target;
  if (!(details instanceof HTMLDetailsElement) || !details.classList.contains("ld-health-details")) return;
  if (!details.open) return;

  const index = Number(details.dataset.healthIndex);
  if (Number.isNaN(index) || emulatorHealthByIndex[index]) return;

  const summary = details.querySelector("summary");
  const previousSummary = summary ? summary.outerHTML : "<summary>LDPlayer Settings</summary>";
  details.innerHTML = `${previousSummary}<p class="settings-loading">Loading LDPlayer settings…</p>`;
  details.open = true;

  try {
    const health = await loadEmulatorHealthForIndex(index);
    const replacement = document.createElement("div");
    replacement.innerHTML = renderLdHealthPanel(health, index);
    const next = replacement.firstElementChild;
    if (next) {
      next.open = true;
      next.dataset.healthLoaded = "1";
      details.replaceWith(next);
    }
  } catch (error) {
    details.innerHTML = `
      ${previousSummary.replace("LDPlayer Settings", "LDPlayer Settings (error)")}
      <p class="settings-loading error">${escapeHtml(error.message || "Could not load LDPlayer settings.")}</p>`;
    if (summary) summary.classList.add("warn");
    details.dataset.healthLoaded = "1";
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearEmulatorApkPoll();
    clearProvisionPoll();
    clearSettingsActivityPoll();
    return;
  }
  if (activeSettingsTab === "restore") {
    scheduleEmulatorApkSync();
  }
  if (activeSettingsTab === "provision" && activeProvisionJobId) {
    scheduleProvisionPoll(activeProvisionJobId);
  }
  scheduleSettingsActivityPoll();
});

const initialTabParam = new URLSearchParams(window.location.search).get("tab");

async function loadUpdateStatus(force = false) {
  const summary = document.getElementById("monitor-update-summary");
  const applyBtn = document.getElementById("monitor-apply-update-btn");
  if (!summary) return;
  summary.textContent = "Checking version…";
  try {
    const response = await fetch(`/api/update/status${force ? "?force=true" : ""}`);
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Update check failed.");
    const versionLabel = body.localVersion ? `v${body.localVersion}` : "";
    const local = [versionLabel, body.localCommitShort].filter(Boolean).join(" ") || "unknown";
    const remote = body.remoteCommitShort || "unknown";
    summary.textContent = body.updateAvailable
      ? `Update available: ${local} → ${remote}${body.remoteMessage ? ` — ${body.remoteMessage}` : ""}`
      : `Up to date (${local}) via ${body.updateMode || "release"}.`;
    if (applyBtn) applyBtn.disabled = !body.updateAvailable;
  } catch (error) {
    summary.textContent = error.message || "Could not check for updates.";
    if (applyBtn) applyBtn.disabled = true;
  }
}

function setAutomationPageStatus(message, tone = "") {
  if (!els.automationPageStatus) return;
  els.automationPageStatus.textContent = message || "";
  els.automationPageStatus.className = `settings-status controls-meta${tone ? ` ${tone}` : ""}`;
}

function renderAutomationToggles(status, config) {
  if (!els.automationToggles) return;
  const cfg = config || {};
  const fields = [
    {
      key: "issue_history_enabled",
      label: "Record issue history",
      checked: cfg.issue_history_enabled !== false,
    },
    {
      key: "stuck_screen_learning_enabled",
      label: "Learn stuck-screen patterns (same-screen timeouts)",
      checked: cfg.stuck_screen_learning_enabled !== false,
    },
    {
      key: "stuck_screen_auto_fix_enabled",
      label: "Auto-fix stuck screens (Back / restart / warn)",
      checked: Boolean(cfg.stuck_screen_auto_fix_enabled),
    },
    {
      key: "auto_stop_gnbots_on_trouble",
      label: "Auto-stop GnBots on problem emulators",
      checked: Boolean(cfg.auto_stop_gnbots_on_trouble),
    },
    {
      key: "auto_update_apks",
      label: "Auto-update APKs when newer (GnBots URL and/or third-party; bot must be stopped)",
      checked: Boolean(cfg.auto_update_apks),
    },
  ];
  const sourcePolicy = String(cfg.apk_source_policy || "auto").toLowerCase();
  els.automationToggles.innerHTML =
    fields
      .map(
        (field) => `
    <label class="automation-toggle-row">
      <input type="checkbox" data-automation-key="${field.key}" ${field.checked ? "checked" : ""}>
      <span>${escapeHtml(field.label)}</span>
    </label>`,
      )
      .join("") +
    `
    <label class="automation-toggle-row automation-select-row">
      <span>APK source policy</span>
      <select data-automation-key="apk_source_policy">
        <option value="auto" ${sourcePolicy === "auto" ? "selected" : ""}>Auto — newer of GnBots / third-party</option>
        <option value="third_party" ${sourcePolicy === "third_party" || sourcePolicy === "apk20" ? "selected" : ""}>Force third-party (APK20)</option>
        <option value="gnbots" ${sourcePolicy === "gnbots" ? "selected" : ""}>Force GnBots game.zip</option>
      </select>
    </label>`;

  if (els.automationMeta) {
    const state = status?.state || {};
    const lastTick = state.lastTickAt || "never";
    const lastError = state.lastError ? ` Last error: ${state.lastError}` : "";
    const stuck = status?.stuckRules || {};
    els.automationMeta.textContent =
      `Poll every ${status?.pollSeconds || 60}s · last tick ${lastTick} · ` +
      `stuck rules ${stuck.enabledRuleCount || 0}/${stuck.ruleCount || 0} enabled.${lastError}`;
  }
}

function remediationLabel(value) {
  const map = {
    press_back: "Press Back",
    restart_emulator: "Restart emulator",
    warn_user: "Warn user",
  };
  return map[value] || value || "Warn user";
}

function renderStuckRules(payload) {
  if (!els.automationStuckRulesBody) return;
  const rules = payload?.rules || [];
  if (!rules.length) {
    els.automationStuckRulesBody.innerHTML =
      `<p class="settings-group-desc">No stuck-screen rules yet. Enable learning and wait for same-screen timeouts, or click Learn from history.</p>`;
    return;
  }
  els.automationStuckRulesBody.innerHTML = `
    <p class="settings-group-desc">
      Learning ${payload?.learningEnabled === false ? "off" : "on"} ·
      Auto-fix ${payload?.autoFixEnabled ? "on" : "off"} ·
      ${rules.length} rule(s). Enable Auto-fix above to execute enabled rules.
    </p>
    <ul class="automation-stuck-list">
      ${rules
        .map((rule) => {
          const match = rule.match || {};
          const contains = match.actionContains || match.actionExact || "(any)";
          const rem = rule.remediation || "warn_user";
          return `
        <li class="automation-stuck-row" data-rule-id="${escapeHtml(rule.id)}">
          <label class="automation-toggle-row">
            <input type="checkbox" data-stuck-enabled ${rule.enabled ? "checked" : ""}>
            <span><strong>${escapeHtml(rule.label || rule.id)}</strong></span>
          </label>
          <div class="automation-stuck-meta">
            Match screen contains <code>${escapeHtml(contains)}</code>
            · hits ${Number(rule.hits) || 0}
            · fixes ${Number(rule.autoFixCount) || 0}
            · ${escapeHtml(rule.source || "rule")}
          </div>
          <label class="account-settings-label">
            Action
            <select class="setting-input" data-stuck-remediation style="width: auto; margin-left: 0.5rem;">
              <option value="press_back" ${rem === "press_back" ? "selected" : ""}>Press Back</option>
              <option value="restart_emulator" ${rem === "restart_emulator" ? "selected" : ""}>Restart emulator</option>
              <option value="warn_user" ${rem === "warn_user" ? "selected" : ""}>Warn user</option>
            </select>
          </label>
        </li>`;
        })
        .join("")}
    </ul>`;
}

function renderIssueReport(report) {
  if (!els.automationReportBody) return;
  const common = report?.commonIssues || [];
  const accounts = report?.topAccounts || [];
  const recent = report?.recent || [];
  if (!common.length && !recent.length) {
    els.automationReportBody.innerHTML =
      `<p class="settings-group-desc">No issues recorded in the last ${report?.days || 7} day(s) yet.</p>`;
    return;
  }
  els.automationReportBody.innerHTML = `
    <p class="settings-group-desc">${Number(report.totalEvents) || 0} event(s) in the last ${report.days} day(s).</p>
    <div class="automation-report-grid">
      <div>
        <h3 class="automation-subhead">Most common</h3>
        <ul class="automation-list">
          ${common
            .map(
              (row) =>
                `<li><strong>${escapeHtml(row.label || row.category)}</strong> <span>${Number(row.count) || 0}</span></li>`,
            )
            .join("") || "<li>None</li>"}
        </ul>
      </div>
      <div>
        <h3 class="automation-subhead">Top accounts</h3>
        <ul class="automation-list">
          ${accounts
            .map(
              (row) =>
                `<li><strong>${escapeHtml(row.account)}</strong> <span>${Number(row.count) || 0}</span></li>`,
            )
            .join("") || "<li>None</li>"}
        </ul>
      </div>
    </div>
    <h3 class="automation-subhead">Recent</h3>
    <ul class="automation-recent-list">
      ${recent
        .slice(0, 12)
        .map(
          (row) =>
            `<li><span class="automation-recent-at">${escapeHtml(String(row.at || "").slice(0, 19))}</span> ${escapeHtml(row.label || row.category || "")}${row.account ? ` · ${escapeHtml(row.account)}` : ""}</li>`,
        )
        .join("")}
    </ul>`;
}

function renderAssistantSuggestions(payload) {
  if (!els.automationAssistantBody) return;
  const items = payload?.items || [];
  const llmNote =
    payload?.llm?.enabled && payload?.llm?.result?.overview
      ? `<p class="settings-group-desc">${escapeHtml(payload.llm.result.overview)}</p>`
      : `<p class="settings-group-desc">${escapeHtml(payload?.message || "")}</p>`;
  if (!items.length) {
    els.automationAssistantBody.innerHTML = llmNote;
    return;
  }
  els.automationAssistantBody.innerHTML =
    llmNote +
    items
      .map(
        (item) => `
    <article class="automation-suggestion-card">
      <h3>${escapeHtml(item.title || item.label || item.category)} <span class="automation-count">${Number(item.count) || 0}</span></h3>
      <p>${escapeHtml(item.summary || "")}</p>
      <ol>
        ${(item.suggestions || []).map((tip) => `<li>${escapeHtml(tip)}</li>`).join("")}
      </ol>
    </article>`,
      )
      .join("");
}

async function saveAutomationToggle(key, enabled) {
  await saveAutomationConfigValue(key, enabled ? "true" : "false");
  currentMonitorConfig = { ...(currentMonitorConfig || {}), [key]: enabled };
}

async function saveAutomationConfigValue(key, value) {
  const response = await fetch(
    `/api/monitor-config/${encodeURIComponent(key)}/update?value=${encodeURIComponent(String(value))}`,
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail || body.error || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  currentMonitorConfig = { ...(currentMonitorConfig || {}), [key]: value };
  return body;
}

async function loadAutomationTab() {
  setAutomationPageStatus("Loading automation…", "pending");
  const days = Number(els.automationReportDays?.value || 7);
  try {
    const [statusRes, configRes, reportRes, suggestRes, stuckRes] = await Promise.all([
      fetch("/api/automation/status", { cache: "no-store" }),
      fetch("/api/monitor-config", { cache: "no-store" }),
      fetch(`/api/reports/issues?days=${days}`, { cache: "no-store" }),
      fetch(`/api/assistant/suggestions?days=${days}`, { cache: "no-store" }),
      fetch("/api/automation/stuck-rules", { cache: "no-store" }),
    ]);
    const status = await statusRes.json().catch(() => ({}));
    const configPayload = await configRes.json().catch(() => ({}));
    const report = await reportRes.json().catch(() => ({}));
    const suggestions = await suggestRes.json().catch(() => ({}));
    const stuck = await stuckRes.json().catch(() => ({}));
    if (!statusRes.ok) throw new Error(status.detail || `HTTP ${statusRes.status}`);
    if (configRes.ok) {
      currentMonitorConfig = configPayload.config || currentMonitorConfig;
    }
    renderAutomationToggles(status, currentMonitorConfig);
    if (stuckRes.ok) renderStuckRules(stuck);
    if (reportRes.ok) renderIssueReport(report);
    if (suggestRes.ok) renderAssistantSuggestions(suggestions);
    setAutomationPageStatus("Automation ready.", "ok");
  } catch (error) {
    setAutomationPageStatus(error.message || "Failed to load automation.", "error");
  }
}

els.automationRefreshBtn?.addEventListener("click", () => {
  loadAutomationTab();
});

els.automationRunTickBtn?.addEventListener("click", async () => {
  setAutomationPageStatus("Running automation check…", "pending");
  try {
    const response = await fetch("/api/automation/tick", { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    const count = Array.isArray(body.actions) ? body.actions.length : 0;
    setAutomationPageStatus(
      count ? `Automation tick finished (${count} action(s)).` : "Automation tick finished (no actions).",
      "ok",
    );
    await loadAutomationTab();
  } catch (error) {
    setAutomationPageStatus(error.message || "Automation tick failed.", "error");
  }
});

els.automationSuggestBtn?.addEventListener("click", async () => {
  const days = Number(els.automationReportDays?.value || 7);
  setAutomationPageStatus("Refreshing suggestions…", "pending");
  try {
    const response = await fetch(`/api/assistant/suggestions?days=${days}&llm=1`, { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    renderAssistantSuggestions(body);
    setAutomationPageStatus("Suggestions updated.", "ok");
  } catch (error) {
    setAutomationPageStatus(error.message || "Could not refresh suggestions.", "error");
  }
});

els.automationReportDays?.addEventListener("change", () => {
  loadAutomationTab();
});

els.automationToggles?.addEventListener("change", async (event) => {
  const select = event.target.closest("select[data-automation-key]");
  if (select) {
    const key = select.dataset.automationKey;
    const previous = currentMonitorConfig?.[key] || "auto";
    try {
      setAutomationPageStatus(`Saving ${key}…`, "pending");
      await saveAutomationConfigValue(key, select.value);
      setAutomationPageStatus(`Saved ${key}.`, "ok");
    } catch (error) {
      select.value = previous;
      setAutomationPageStatus(error.message || "Could not save automation setting.", "error");
    }
    return;
  }
  const input = event.target.closest("input[data-automation-key]");
  if (!input) return;
  const key = input.dataset.automationKey;
  try {
    setAutomationPageStatus(`Saving ${key}…`, "pending");
    await saveAutomationToggle(key, Boolean(input.checked));
    setAutomationPageStatus(`Saved ${key}.`, "ok");
  } catch (error) {
    input.checked = !input.checked;
    setAutomationPageStatus(error.message || "Could not save automation setting.", "error");
  }
});

els.automationStuckLearnBtn?.addEventListener("click", async () => {
  const days = Number(els.automationReportDays?.value || 7);
  setAutomationPageStatus("Learning stuck-screen patterns from history…", "pending");
  try {
    const response = await fetch(`/api/automation/stuck-rules/learn?days=${days}`, {
      method: "POST",
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    renderStuckRules({
      learningEnabled: currentMonitorConfig?.stuck_screen_learning_enabled !== false,
      autoFixEnabled: Boolean(currentMonitorConfig?.stuck_screen_auto_fix_enabled),
      rules: body.rules || [],
    });
    setAutomationPageStatus(
      `Learned ${Number(body.learned) || 0}, reinforced ${Number(body.reinforced) || 0}.`,
      "ok",
    );
  } catch (error) {
    setAutomationPageStatus(error.message || "Stuck-screen learning failed.", "error");
  }
});

els.automationStuckRulesBody?.addEventListener("change", async (event) => {
  const row = event.target.closest("[data-rule-id]");
  if (!row) return;
  const ruleId = row.dataset.ruleId;
  const enabledInput = row.querySelector("input[data-stuck-enabled]");
  const remSelect = row.querySelector("select[data-stuck-remediation]");
  const payload = {};
  if (event.target === enabledInput) payload.enabled = Boolean(enabledInput.checked);
  if (event.target === remSelect) payload.remediation = remSelect.value;
  if (!Object.keys(payload).length) return;
  try {
    setAutomationPageStatus(`Saving rule ${ruleId}…`, "pending");
    const response = await fetch(`/api/automation/stuck-rules/${encodeURIComponent(ruleId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    setAutomationPageStatus("Stuck-screen rule saved.", "ok");
  } catch (error) {
    setAutomationPageStatus(error.message || "Could not save stuck-screen rule.", "error");
    await loadAutomationTab();
  }
});

document.getElementById("monitor-check-updates-btn")?.addEventListener("click", () => {
  loadUpdateStatus(true);
});

document.getElementById("monitor-apply-update-btn")?.addEventListener("click", async () => {
  const applyBtn = document.getElementById("monitor-apply-update-btn");
  const summary = document.getElementById("monitor-update-summary");
  if (!applyBtn || applyBtn.disabled) return;
  const confirmed = window.confirm(
    "Apply update and restart the monitor stack?\n\n" +
      "A desktop progress window will appear. This Settings page may disconnect while the monitor restarts.",
  );
  if (!confirmed) return;
  applyBtn.disabled = true;
  summary.textContent = "Starting update…";
  try {
    const response = await fetch("/api/update/apply", { method: "POST" });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Update failed to start.");
    summary.textContent =
      body.message ||
      "Update running — watch the Sentinel update window. This page may stop responding until restart.";
    pollUpdateRestart(summary, applyBtn);
  } catch (error) {
    summary.textContent = error.message || "Update failed.";
    applyBtn.disabled = false;
  }
});

async function pollUpdateRestart(summary, applyBtn) {
  let sawDisconnect = false;
  for (let attempt = 0; attempt < 90; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    try {
      const response = await fetch("/api/update/status?force=true", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (sawDisconnect) {
        summary.textContent = "Monitor is back. Refreshing update status…";
        await loadUpdateStatus(true);
        return;
      }
      summary.textContent =
        "Update running — watch the Sentinel update window. Waiting for monitor restart…";
    } catch (_error) {
      sawDisconnect = true;
      summary.textContent = "Monitor restarting… watch the Sentinel update window.";
    }
  }
  summary.textContent =
    "Still waiting for the monitor. If the update window closed, refresh this page.";
  if (applyBtn) applyBtn.disabled = false;
}

const initialTabHash = window.location.hash.replace("#", "");
const initialTab = [initialTabParam, initialTabHash].find(
  (value) =>
    value &&
    ["bot", "accounts", "names", "bulk", "provision", "restore", "automation", "monitor"].includes(value),
);
if (initialTab) {
  setActiveSettingsTab(initialTab);
} else {
  loadSettings();
}

