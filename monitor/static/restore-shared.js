/** Shared LDPlayer restore helpers for dashboard + settings. */

const RESTORE_STATUS_PROGRESS = {
  queued: 5,
  stopping: 10,
  restoring: 25,
  "prelaunch-settings": 38,
  renaming: 40,
  "health-check": 50,
  "syncing-apk": 58,
  booting: 65,
  "installing-apk": 72,
  "resource-pack": 85,
  finalizing: 95,
  completed: 100,
  failed: 0,
};

function progressForRestoreStatus(status) {
  return RESTORE_STATUS_PROGRESS[String(status || "")] ?? 15;
}

function formatRestoreJobStatus(job) {
  const progress = Number.isFinite(job?.progress)
    ? Number(job.progress)
    : progressForRestoreStatus(job?.status);
  const message = job?.message || `Restore in progress (${job?.status || "working"})…`;
  return { progress, message };
}

function escapeRestoreHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function buildAccountMetaByInstance(accounts) {
  const byInstance = new Map();
  for (const account of accounts || []) {
    const restore = account.emulatorRestore || {};
    const index = restore.instanceIndex;
    if (index == null || index < 0) continue;

    if (!byInstance.has(index)) {
      byInstance.set(index, {
        accounts: [],
        troubled: false,
        troubleReasons: [],
        apkVersion: restore.apkVersion || null,
      });
    }

    const meta = byInstance.get(index);
    meta.accounts.push(account.name);
    if (restore.troubled) {
      meta.troubled = true;
      for (const reason of restore.troubleReasons || []) {
        if (!meta.troubleReasons.includes(reason)) meta.troubleReasons.push(reason);
      }
    }
    if (restore.apkVersion) meta.apkVersion = restore.apkVersion;
  }
  return byInstance;
}

function applyEmulatorInstanceFields(row, inst) {
  row.ldName = inst.name || row.ldName || `Instance ${row.index}`;
  row.missing = Boolean(inst.missing);
  row.backupAvailable = Boolean(inst.backupAvailable);
  row.backupFile = inst.backupFile || null;
  row.backupPath = inst.backupPath || null;
  row.backupSizeMb = inst.backupSizeMb ?? null;
  row.backupMatchSource = inst.backupMatchSource || "none";
  row.backupAutoFile = inst.backupAutoFile || null;
  row.backupManualFile = inst.backupManualFile || null;
  row.restoreBusy = Boolean(inst.restoreBusy);
  if (inst.restoreJobId) row.restoreJobId = inst.restoreJobId;
}

function mergeRestoreRowsFromEmulators(emulatorInstances, accountMetaByIndex) {
  const metaMap = accountMetaByIndex instanceof Map ? accountMetaByIndex : buildAccountMetaByInstance(accountMetaByIndex);
  const rows = [];

  for (const inst of emulatorInstances || []) {
    if (!inst || inst.index == null || inst.index < 0) continue;
    const index = Number(inst.index);
    const meta = metaMap.get(index) || {};
    const troubleReasons = [...(meta.troubleReasons || [])];
    if (inst.missing && !troubleReasons.includes("LDPlayer instance missing")) {
      troubleReasons.push("LDPlayer instance missing");
    }

    const row = {
      index,
      ldName: inst.name || `Instance ${index}`,
      missing: Boolean(inst.missing),
      accounts: [...(meta.accounts || [])],
      troubled: Boolean(meta.troubled || inst.missing),
      troubleReasons,
      apkVersion: meta.apkVersion || null,
      restoreBusy: Boolean(inst.restoreBusy),
      restoreJobId: inst.restoreJobId || null,
      backupAvailable: false,
      backupFile: null,
      backupPath: null,
      backupSizeMb: null,
      backupMatchSource: "none",
      backupAutoFile: null,
      backupManualFile: null,
    };
    applyEmulatorInstanceFields(row, inst);
    rows.push(row);
  }

  return rows.sort((a, b) => a.index - b.index);
}

function buildRestoreInstanceRows(accounts) {
  const byInstance = new Map();
  for (const account of accounts || []) {
    const restore = account.emulatorRestore || {};
    const index = restore.instanceIndex;
    if (index == null || index < 0) continue;

    if (!byInstance.has(index)) {
      byInstance.set(index, {
        index,
        ldName: restore.ldName || `Instance ${index}`,
        missing: Boolean(restore.ldMissing),
        backupAvailable: Boolean(restore.available),
        backupFile: restore.backupFile,
        backupSizeMb: restore.backupSizeMb,
        backupMatchSource: restore.backupMatchSource || "none",
        backupAutoFile: restore.backupAutoFile || null,
        backupManualFile: restore.backupManualFile || null,
        apkVersion: restore.apkVersion,
        troubled: Boolean(restore.ldMissing),
        troubleReasons: restore.ldMissing ? ["LDPlayer instance missing"] : [],
        accounts: [],
        restoreBusy: Boolean(restore.restoreBusy),
        restoreJobId: restore.restoreJobId || null,
      });
    }

    const row = byInstance.get(index);
    row.accounts.push(account.name);
    if (restore.troubled) {
      row.troubled = true;
      for (const reason of restore.troubleReasons || []) {
        if (!row.troubleReasons.includes(reason)) row.troubleReasons.push(reason);
      }
    }
    row.missing = row.missing || Boolean(restore.ldMissing);
    row.backupAvailable = row.backupAvailable || Boolean(restore.available);
    row.restoreBusy = row.restoreBusy || Boolean(restore.restoreBusy);
    if (restore.restoreJobId) row.restoreJobId = restore.restoreJobId;
  }

  return [...byInstance.values()].sort((a, b) => a.index - b.index);
}

function troubledRestoreRows(accounts) {
  return buildRestoreInstanceRows(accounts).filter((row) => row.troubled);
}

function restoreConfirmMessageForRow(row, { botActive = false } = {}) {
  const backup = row.backupFile || "backup";
  const size = row.backupSizeMb ? ` (~${row.backupSizeMb} MB)` : "";
  const reasons = (row.troubleReasons || []).join("; ");
  const accounts = (row.accounts || []).join(", ");
  return [
    row.missing
      ? `Recreate missing LDPlayer slot ${row.index} (${row.ldName}) and restore from ${backup}${size}?`
      : `Restore ${row.ldName} (instance ${row.index}) from ${backup}${size}?`,
    accounts ? `Accounts on this instance: ${accounts}` : "",
    "",
    row.missing
      ? "Creates the LDPlayer instance if needed, then replaces it with the backup."
      : "This replaces the current emulator data with the backup.",
    "Renames the instance to the canonical LDPlayer name and applies GnBots emulator health settings.",
    row.apkVersion
      ? `Then installs Whiteout Survival ${row.apkVersion} from the GnBots APK cache.`
      : "Then installs the latest Whiteout Survival APK from the GnBots cache.",
    botActive ? "Stop the bot before restoring." : "",
    reasons ? `Reason: ${reasons}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

async function pollRestoreJob(jobId, options = {}) {
  const onStatus = typeof options.onStatus === "function" ? options.onStatus : () => {};
  const deadline = Date.now() + (options.timeoutMs || 2 * 60 * 60 * 1000);
  while (Date.now() < deadline) {
    const response = await fetch(`/api/emulators/restore/jobs/${jobId}`, { cache: "no-store" });
    if (!response.ok) break;
    const payload = await response.json();
    const job = payload.job || {};
    const status = String(job.status || "");
    onStatus(job);
    if (status === "completed") return job;
    if (status === "failed") {
      throw new Error(job.message || "Emulator restore failed.");
    }
    await new Promise((resolve) => setTimeout(resolve, options.pollMs || 3000));
  }
  throw new Error("Timed out waiting for emulator restore to finish.");
}

async function findActiveRestoreJob() {
  try {
    const response = await fetch("/api/emulators/restore/jobs", { cache: "no-store" });
    if (!response.ok) return null;
    const payload = await response.json();
    const jobs = payload.jobs || [];
    return (
      jobs.find((job) => {
        const status = String(job.status || "");
        return status && status !== "completed" && status !== "failed";
      }) || null
    );
  } catch {
    return null;
  }
}

async function resumeRestoreJobPolling(options = {}) {
  const onStatus = typeof options.onStatus === "function" ? options.onStatus : () => {};
  const onComplete = typeof options.onComplete === "function" ? options.onComplete : () => {};
  const onError = typeof options.onError === "function" ? options.onError : () => {};

  let jobId = options.jobId || null;
  if (!jobId) {
    const active = await findActiveRestoreJob();
    jobId = active?.id || null;
  }
  if (!jobId) return null;

  try {
    const job = await pollRestoreJob(jobId, { ...options, onStatus });
    await onComplete(job);
    return job;
  } catch (error) {
    await onError(error);
    throw error;
  }
}

async function startInstanceRestore(index, options = {}) {
  const onStatus = typeof options.onStatus === "function" ? options.onStatus : () => {};
  onStatus({ message: "Starting emulator restore…", status: "starting" });

  const response = await fetch(`/api/emulators/${index}/restore`, {
    method: "POST",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail ?? payload.message ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  const jobId = payload.job?.id;
  if (!jobId) {
    throw new Error("Restore started but no job id was returned.");
  }

  return pollRestoreJob(jobId, { ...options, onStatus });
}

window.GnBotsRestore = {
  escapeRestoreHtml,
  buildAccountMetaByInstance,
  applyEmulatorInstanceFields,
  buildRestoreInstanceRows,
  mergeRestoreRowsFromEmulators,
  troubledRestoreRows,
  restoreConfirmMessageForRow,
  progressForRestoreStatus,
  formatRestoreJobStatus,
  pollRestoreJob,
  findActiveRestoreJob,
  resumeRestoreJobPolling,
  startInstanceRestore,
};
