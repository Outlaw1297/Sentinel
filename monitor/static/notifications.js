const STORAGE_KEY = "gnbotsNotificationsEnabled";
const INSTALL_BANNER_KEY = "gnbotsInstallBannerDismissed";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}

function supportsNotifications() {
  return "serviceWorker" in navigator && "Notification" in window && "PushManager" in window;
}

function notificationsEnabledLocally() {
  return localStorage.getItem(STORAGE_KEY) === "true";
}

function setNotificationsEnabledLocally(enabled) {
  localStorage.setItem(STORAGE_KEY, enabled ? "true" : "false");
}

function updateBellButton(button, state = {}) {
  if (!button) return;
  const enabled = Boolean(state.enabled);
  const subscribed = Boolean(state.subscribed);
  button.classList.toggle("active", enabled && subscribed);
  button.classList.toggle("warn", enabled && !subscribed && Notification.permission === "denied");
  if (!enabled) {
    button.title = "Notifications unavailable on this server";
  } else if (subscribed) {
    button.title = "Notifications on — tap to turn off";
  } else if (Notification.permission === "denied") {
    button.title = "Notifications blocked in browser settings";
  } else {
    button.title = "Enable notifications";
  }
}

async function fetchPushStatus() {
  const response = await fetch("/api/push/status");
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return body;
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return null;
  }
  return navigator.serviceWorker.register("/service-worker.js", { scope: "/" });
}

async function getActivePushSubscription() {
  if (!supportsNotifications()) {
    return null;
  }
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

async function isCurrentlySubscribed() {
  const subscription = await getActivePushSubscription();
  return Boolean(subscription);
}

async function syncBellFromSubscription(button, serverStatus = {}) {
  const subscribed = (await isCurrentlySubscribed()) && Notification.permission === "granted";
  if (subscribed) {
    setNotificationsEnabledLocally(true);
  } else {
    setNotificationsEnabledLocally(false);
  }
  updateBellButton(button, {
    enabled: serverStatus.enabled !== false,
    subscribed,
  });
  return subscribed;
}

async function reconcilePushSubscription() {
  const subscription = await getActivePushSubscription();
  if (!subscription && notificationsEnabledLocally()) {
    setNotificationsEnabledLocally(false);
  }
}

async function subscribeToPush() {
  const status = await fetchPushStatus();
  if (!status.enabled || !status.publicKey) {
    throw new Error("Push notifications are not enabled on the server.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notification permission was not granted.");
  }

  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(status.publicKey),
    });
  }

  const response = await fetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription.toJSON()),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Subscribe failed (${response.status})`);
  }

  setNotificationsEnabledLocally(true);
  return {
    status: await fetchPushStatus(),
    subscription,
  };
}

async function unsubscribeFromPush({ skipBellUpdate = false } = {}) {
  setNotificationsEnabledLocally(false);

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    const endpoint = subscription.endpoint;
    try {
      await fetch("/api/push/subscribe", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint }),
      });
    } catch (error) {
      console.warn("Server push unsubscribe failed:", error);
    }
    try {
      const removed = await subscription.unsubscribe();
      if (!removed) {
        console.warn("Browser reported push unsubscribe was not successful.");
      }
    } catch (error) {
      console.warn("Browser push unsubscribe failed:", error);
    }
  }

  const status = await fetchPushStatus();
  if (!skipBellUpdate) {
    const button = document.getElementById("notifications-btn");
    updateBellButton(button, { enabled: status.enabled !== false, subscribed: false });
  }
  return status;
}

async function ensureNotificationsEnabled({ prompt = true } = {}) {
  if (!supportsNotifications()) {
    return { enabled: false, subscribed: false, reason: "unsupported" };
  }

  let status = await fetchPushStatus();
  const button = document.getElementById("notifications-btn");
  if (!status.enabled) {
    updateBellButton(button, status);
    return { ...status, reason: "server-disabled" };
  }

  await registerServiceWorker();
  await reconcilePushSubscription();

  if (notificationsEnabledLocally()) {
    try {
      const result = await subscribeToPush();
      status = result.status;
      updateBellButton(button, {
        enabled: status.enabled !== false,
        subscribed: true,
      });
      return status;
    } catch (error) {
      console.warn("Notification subscribe failed:", error);
      setNotificationsEnabledLocally(false);
    }
  } else if (prompt && Notification.permission === "default") {
    await syncBellFromSubscription(button, status);
    return { ...status, reason: "permission-needed" };
  }

  await syncBellFromSubscription(button, status);
  return status;
}

function snapshotSignature(payload) {
  if (!payload) return "";
  return [
    payload.botState,
    payload.botActive,
    payload.gnbotsOnline,
    payload.gnbotsProcessRunning,
    payload.gnbotsApi?.healthy,
    payload.stack?.watcher?.running,
    payload.stack?.monitor?.healthy,
    payload.logs?.[payload.logs.length - 1]?.time,
    payload.logs?.[payload.logs.length - 1]?.message,
  ].join("|");
}

async function showLocalNotification(title, body, tag) {
  if (Notification.permission !== "granted") {
    return;
  }
  if (navigator.serviceWorker?.controller) {
    navigator.serviceWorker.controller.postMessage({
      type: "local-notification",
      title,
      body,
      tag,
      url: "/",
    });
    return;
  }
  const registration = await navigator.serviceWorker.ready;
  await registration.showNotification(title, {
    body,
    tag,
    icon: "/static/icons/notification-icon.png?v=1",
    badge: "/static/icons/notification-badge.png?v=1",
  });
}

function detectClientEvents(previous, current) {
  if (!previous || !current) return [];

  const events = [];
  const prevState = previous.botState || "Unknown";
  const curState = current.botState || "Unknown";
  if (prevState !== curState) {
    if (curState === "Running") {
      events.push({ tag: "bot_started", title: "Bot started", body: "GnBots run loop is active." });
    } else if (curState === "Paused") {
      events.push({ tag: "bot_paused", title: "Bot paused", body: "GnBots run loop is paused." });
    } else if (curState === "Stopped" && (prevState === "Running" || prevState === "Paused")) {
      events.push({ tag: "bot_stopped", title: "Bot stopped", body: "GnBots run loop has stopped." });
    }
  }

  const prevProc = Boolean(previous.gnbotsProcessRunning);
  const curProc = Boolean(current.gnbotsProcessRunning);
  if (prevProc !== curProc) {
    events.push(
      curProc
        ? { tag: "gnbots_launched", title: "GnBots launched", body: "GnBots.exe is running." }
        : { tag: "gnbots_closed", title: "GnBots closed", body: "GnBots.exe is no longer running." },
    );
  }

  const prevApi = Boolean(previous.gnbotsOnline);
  const curApi = Boolean(current.gnbotsOnline);
  if (prevApi !== curApi) {
    events.push(
      curApi
        ? { tag: "api_recovered", title: "GnBots online", body: "Dashboard reconnected to GnBots." }
        : { tag: "api_down", title: "GnBots offline", body: current.gnbotsError || "Dashboard lost API connection." },
    );
  }

  const prevLog = previous.logs?.[previous.logs.length - 1];
  const curLog = current.logs?.[current.logs.length - 1];
  if (curLog && (prevLog?.time !== curLog.time || prevLog?.message !== curLog.message)) {
    const alertable = curLog.alertable !== false;
    if (alertable && curLog.level === "ERROR") {
      events.push({ tag: "log_error", title: "Bot error", body: curLog.message || "New error in bot log." });
    } else if (alertable && curLog.level === "WARN") {
      events.push({ tag: "log_warn", title: "Bot warning", body: curLog.message || "New warning in bot log." });
    }
  }

  return events;
}

let previousDashboardPayload = null;
let previousSignature = "";
let toggleBusy = false;

async function onDashboardUpdate(payload) {
  const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.ready : null;
  const pushSubscription = registration ? await registration.pushManager.getSubscription() : null;

  if (pushSubscription) {
    previousDashboardPayload = payload;
    previousSignature = snapshotSignature(payload);
    return;
  }

  if (!notificationsEnabledLocally() || Notification.permission !== "granted") {
    previousDashboardPayload = payload;
    previousSignature = snapshotSignature(payload);
    return;
  }

  const signature = snapshotSignature(payload);
  if (previousDashboardPayload && signature !== previousSignature) {
    const events = detectClientEvents(previousDashboardPayload, payload);
    for (const event of events) {
      await showLocalNotification(event.title, event.body, event.tag);
    }
  }

  previousDashboardPayload = payload;
  previousSignature = signature;
}

async function toggleNotifications(button) {
  if (!supportsNotifications()) {
    window.alert("This browser does not support installable web app notifications.");
    return;
  }
  if (toggleBusy) {
    return;
  }

  toggleBusy = true;
  button.disabled = true;
  try {
    await registerServiceWorker();
    const status = await fetchPushStatus();
    if (!status.enabled) {
      window.alert("Push notifications are not enabled on the server.");
      updateBellButton(button, { enabled: false, subscribed: false });
      return;
    }

    const wantsOff = button.classList.contains("active");
    if (wantsOff) {
      await unsubscribeFromPush({ skipBellUpdate: true });
      updateBellButton(button, { enabled: status.enabled !== false, subscribed: false });
      return;
    }

    await subscribeToPush();
    updateBellButton(button, { enabled: status.enabled !== false, subscribed: true });
  } catch (error) {
    window.alert(error.message || "Could not update notifications.");
    try {
      const status = await fetchPushStatus();
      await syncBellFromSubscription(button, status);
    } catch {
      updateBellButton(button, { enabled: true, subscribed: false });
    }
  } finally {
    toggleBusy = false;
    button.disabled = false;
  }
}

function isStandaloneApp() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function isMobileDevice() {
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
}

function installInstructions() {
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/i.test(ua)) {
    return {
      title: "Install on iPhone",
      text: "Use Safari (not Firefox): tap Share → Add to Home Screen. Then open Sentinel from your home screen and tap the bell for notifications.",
    };
  }
  if (/Android/i.test(ua)) {
    if (/Firefox/i.test(ua)) {
      return {
        title: "Install on Android",
        text: "Firefox: tap the menu ⋮ → Install or Add to Home screen. For the best experience, use Chrome: menu ⋮ → Install app or Add to Home screen.",
      };
    }
    return {
      title: "Install on Android",
      text: "Tap the browser menu ⋮ → Install app or Add to Home screen. Then open Sentinel from your home screen and tap the bell for notifications.",
    };
  }
  return {
    title: "Install this app",
    text: "Use your browser menu to install or add this site to your home screen for quick access.",
  };
}

function initInstallBanner() {
  const banner = document.getElementById("install-banner");
  const title = document.getElementById("install-banner-title");
  const text = document.getElementById("install-banner-text");
  const dismiss = document.getElementById("install-banner-dismiss");
  if (!banner || !title || !text || !dismiss) return;

  if (localStorage.getItem(INSTALL_BANNER_KEY) === "true" || isStandaloneApp() || !isMobileDevice()) {
    banner.classList.add("hidden");
    return;
  }

  const copy = installInstructions();
  title.textContent = copy.title;
  text.textContent = copy.text;
  banner.classList.remove("hidden");

  dismiss.addEventListener("click", () => {
    localStorage.setItem(INSTALL_BANNER_KEY, "true");
    banner.classList.add("hidden");
  });
}

async function initNotifications(button) {
  initInstallBanner();

  if (!button || !supportsNotifications()) {
    if (button) button.classList.add("hidden");
    return;
  }

  button.addEventListener("click", () => toggleNotifications(button));

  try {
    await ensureNotificationsEnabled({ prompt: false });
  } catch (error) {
    console.warn("Notification init failed:", error);
    updateBellButton(button, { enabled: false, subscribed: false });
  }
}

window.GnBotsNotifications = {
  initNotifications,
  onDashboardUpdate,
  ensureNotificationsEnabled,
  initInstallBanner,
};
