async function loadSetupStatus() {
  const statusEl = document.getElementById("setup-status");
  const advanced = document.getElementById("setup-advanced-section");
  try {
    const res = await fetch("/api/setup/status");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not load setup status.");
    const rootEl = document.getElementById("setup-install-root");
    if (rootEl && data.installRoot) {
      rootEl.textContent = data.installRoot;
    }
    if (data.setupComplete) {
      statusEl.textContent = "Setup is complete. Use Settings → Sentinel to change paths later.";
      statusEl.className = "settings-status controls-meta ok";
      if (advanced) advanced.classList.add("hidden");
    } else {
      statusEl.textContent = "Setup is not complete — run the desktop wizard from your install folder.";
      statusEl.className = "settings-status controls-meta warn";
    }
    return data;
  } catch (error) {
    statusEl.textContent = error.message || "Setup status unavailable.";
    statusEl.className = "settings-status controls-meta error";
    return null;
  }
}

document.getElementById("setup-launch-wizard-btn")?.addEventListener("click", async () => {
  const btn = document.getElementById("setup-launch-wizard-btn");
  const statusEl = document.getElementById("setup-status");
  btn.disabled = true;
  try {
    const res = await fetch("/api/setup/launch-wizard", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not launch wizard.");
    statusEl.textContent = "Desktop Setup Wizard launched. Complete it on this PC, then refresh the dashboard.";
    statusEl.className = "settings-status controls-meta ok";
  } catch (error) {
    statusEl.textContent = error.message || "Launch failed. Run Setup Wizard.bat from the install folder.";
    statusEl.className = "settings-status controls-meta error";
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("setup-toggle-advanced-btn")?.addEventListener("click", () => {
  const section = document.getElementById("setup-advanced-section");
  const btn = document.getElementById("setup-toggle-advanced-btn");
  if (!section || !btn) return;
  const show = section.classList.contains("hidden");
  section.classList.toggle("hidden", !show);
  btn.textContent = show ? "Hide advanced override" : "Show advanced override";
});

document.getElementById("setup-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const btn = document.getElementById("setup-save-btn");
  const statusEl = document.getElementById("setup-status");
  btn.disabled = true;
  statusEl.textContent = "Saving…";
  statusEl.className = "settings-status controls-meta pending";
  const payload = {
    gnbots_exe: document.getElementById("setup-gnbots-exe").value.trim(),
    gnbots_root: document.getElementById("setup-gnbots-root").value.trim(),
    ldplayer_path: document.getElementById("setup-ldplayer-path").value.trim(),
    ldplayer_backups_dir: document.getElementById("setup-backups-dir").value.trim(),
    setup_complete: true,
  };
  try {
    const res = await fetch("/api/setup/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Save failed.");
    statusEl.textContent = "Paths saved. Refresh the dashboard.";
    statusEl.className = "settings-status controls-meta ok";
  } catch (error) {
    statusEl.textContent = error.message || "Save failed.";
    statusEl.className = "settings-status controls-meta error";
  } finally {
    btn.disabled = false;
  }
});

loadSetupStatus();
