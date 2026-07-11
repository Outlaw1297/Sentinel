/** Sentinel UI icons — thin-line set from the brand icon system. */

const SENTINEL_ICON_SVGS = {
  "real-time": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="4" y="4" width="16" height="16" rx="3.5" stroke="currentColor" stroke-width="1.5"/>
    <path d="M7 12h3.2l1.4-2.6 2.2 5.2 1.6-2.6H17" stroke="#3b82f6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
  inspect: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="10.5" cy="10.5" r="5.25" stroke="currentColor" stroke-width="1.5"/>
    <path d="M14.6 14.6 19 19" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    <path d="M8.8 10.2a3.2 3.2 0 0 1 3.4-3.4" stroke="#6366f1" stroke-width="1.5" stroke-linecap="round"/>
  </svg>`,
  analyze: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="5.5" y="13" width="2.5" height="5" rx="0.75" fill="#22c55e"/>
    <rect x="9.75" y="10" width="2.5" height="8" rx="0.75" fill="#3b82f6"/>
    <rect x="14" y="7" width="2.5" height="11" rx="0.75" fill="#6366f1"/>
    <rect x="18.25" y="4.5" width="2.5" height="13.5" rx="0.75" fill="#4f46e5"/>
  </svg>`,
  focus: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="5.5" stroke="currentColor" stroke-width="1.5"/>
    <path d="M12 4.5v2.25M12 17.25V19.5M4.5 12h2.25M17.25 12H19.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="12" cy="12" r="1.75" fill="#6366f1"/>
  </svg>`,
  reliable: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 3.5 18 6.25V11.5c0 3.45-2.45 6.35-6 7.5-3.55-1.15-6-4.05-6-7.5V6.25L12 3.5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    <path d="m8.6 12.1 2.1 2.1 4.7-4.8" stroke="#22c55e" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
};

/**
 * @param {string} name
 * @param {{ className?: string, size?: number }} [options]
 */
function sentinelIcon(name, options = {}) {
  const className = options.className || "sentinel-icon";
  const size = options.size || 20;
  const svg = SENTINEL_ICON_SVGS[name];
  if (!svg) return "";
  return svg
    .replace("<svg ", `<svg class="${className}" width="${size}" height="${size}" `)
    .replace('aria-hidden="true"', `aria-hidden="true" focusable="false"`);
}

function sentinelIconHtml(name, options = {}) {
  return sentinelIcon(name, options);
}

function mountSentinelIcons(root = document) {
  root.querySelectorAll("[data-sentinel-icon]").forEach((el) => {
    const name = el.getAttribute("data-sentinel-icon");
    if (!name) return;
    const size = Number(el.getAttribute("data-icon-size")) || 18;
    let className = "sentinel-icon";
    if (el.classList.contains("tagline-icon")) {
      className += " sentinel-icon-tag";
    } else if (
      el.classList.contains("panel-head-icon")
      || el.closest(".panel-head-title")
      || el.closest(".banner-title-row")
    ) {
      className += " sentinel-icon-panel";
    }
    el.innerHTML = sentinelIconHtml(name, { className, size });
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => mountSentinelIcons());
} else {
  mountSentinelIcons();
}

window.SentinelIcons = {
  names: Object.keys(SENTINEL_ICON_SVGS),
  icon: sentinelIcon,
  html: sentinelIconHtml,
  mount: mountSentinelIcons,
};
