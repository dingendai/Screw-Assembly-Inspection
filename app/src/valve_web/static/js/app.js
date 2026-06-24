import { api } from "./api.js";
import { renderLogin } from "./pages/login.js";
import { renderMonitor } from "./pages/monitor.js";
import { renderHistory } from "./pages/history.js";
import { renderSettings } from "./pages/settings.js";
import { renderRegions } from "./pages/regions.js";
import { renderDisplay } from "./pages/display.js";
import { renderUsers } from "./pages/users.js";

export const app = { me: null, current: null };

// ---- theme (dark / light) ----
export function applyTheme(theme) {
  const t = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);
  const btn = document.getElementById("theme-btn");
  if (btn) btn.textContent = t === "light" ? "☀️ 淺色" : "🌙 深色";
  try { localStorage.setItem("valve_theme", t); } catch {}
}
// Server theme is the source of truth (so the choice follows across devices);
// localStorage just paints instantly before the first request returns.
export function syncThemeFromServer(theme) { if (theme) applyTheme(theme); }
function initTheme() {
  let theme = "dark";
  try { theme = localStorage.getItem("valve_theme") || "dark"; } catch {}
  applyTheme(theme);
  const btn = document.getElementById("theme-btn");
  if (btn) btn.addEventListener("click", async () => {
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    applyTheme(next);
    if (app.me && app.me.logged_in) {
      try { await api.post("/api/config/theme?theme=" + next); } catch {}
    }
  });
}

// Pages can register a teardown callback (stop timers, close MJPEG streams).
let activeCleanup = null;
export function setCleanup(fn) { activeCleanup = fn; }
function runCleanup() {
  if (activeCleanup) { try { activeCleanup(); } catch {} activeCleanup = null; }
}

// ---- small DOM + toast helpers (shared by all pages) ----
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(c));
  }
  return el;
}

// Centered modal dialog (for messages that should interrupt, e.g. login errors).
export function showModal(message, kind = "") {
  const old = document.getElementById("app-modal");
  if (old) old.remove();
  const icon = kind === "error" ? "⛔" : kind === "ok" ? "✅" : "ℹ️";
  let overlay;
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Enter" || e.key === "Escape") close(); };
  const box = h("div", { class: "modal-box " + kind },
    h("div", { class: "modal-icon" }, icon),
    h("div", { class: "modal-msg" }, message),
    h("button", { class: "btn btn-primary", onclick: close }, "確定"));
  overlay = h("div", { class: "modal-overlay", id: "app-modal", onclick: (e) => { if (e.target === overlay) close(); } }, box);
  document.body.appendChild(overlay);
  document.addEventListener("keydown", onKey);
  box.querySelector("button").focus();
}

let toastTimer;
export function toast(msg, kind = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3200);
}

const PAGES = {
  monitor: { label: "監視", perm: "open_monitor", render: renderMonitor },
  settings: { label: "相機 / 模型設定", perm: "open_settings", render: renderSettings },
  regions: { label: "指定範圍監視", perm: "open_settings", render: renderRegions },
  display: { label: "顯示設定", perm: "open_settings", render: renderDisplay },
  history: { label: "歷史紀錄", perm: "open_history", render: renderHistory },
  users: { label: "用戶管理", perm: "__developer__", render: renderUsers },
};

export function applyFontSize(px) {
  const n = parseInt(px);
  if (n >= 10 && n <= 28) document.body.style.fontSize = n + "px";
}

function canSee(page) {
  if (!app.me || !app.me.logged_in) return false;
  if (page.perm === "__developer__") return app.me.is_developer;
  return !!(app.me.permissions && app.me.permissions[page.perm]);
}

export async function navigate(key) {
  const view = document.getElementById("view");
  runCleanup();
  view.innerHTML = "";
  if (!app.me || !app.me.logged_in) {
    app.current = "login";
    renderLogin(view);
    renderNav();
    return;
  }
  const page = PAGES[key];
  if (!page || !canSee(page)) {
    // fall back to first visible page
    key = Object.keys(PAGES).find((k) => canSee(PAGES[k]));
    if (!key) {
      app.current = null;
      renderNav();
      view.append(h("div", { class: "card" }, "目前角色沒有可用的頁面。"));
      return;
    }
  }
  app.current = key;
  renderNav();
  try {
    await PAGES[key].render(view);
  } catch (e) {
    view.append(h("div", { class: "card" }, "載入失敗：" + e.message));
  }
}

function renderNav() {
  const nav = document.getElementById("nav");
  nav.innerHTML = "";
  const badge = document.getElementById("role-badge");
  const logoutBtn = document.getElementById("logout-btn");
  if (!app.me || !app.me.logged_in) {
    badge.textContent = "未登入";
    logoutBtn.classList.add("hidden");
    return;
  }
  badge.textContent = `${app.me.operator_name} · ${app.me.role_label}`;
  logoutBtn.classList.remove("hidden");
  for (const [key, page] of Object.entries(PAGES)) {
    if (!canSee(page)) continue;
    nav.append(
      h("button", {
        class: "nav-btn" + (key === app.current ? " active" : ""),
        onclick: () => navigate(key),
      }, page.label)
    );
  }
}

export async function refreshMe() {
  try {
    app.me = await api.get("/api/me");
    if (app.me && app.me.font_size) applyFontSize(app.me.font_size);
    if (app.me && app.me.theme) syncThemeFromServer(app.me.theme);
  } catch {
    app.me = null;
  }
}

document.getElementById("logout-btn").addEventListener("click", async () => {
  try { await api.post("/api/logout"); } catch {}
  app.me = null;
  toast("已登出", "ok");
  navigate("login");
});

async function boot() {
  initTheme();
  await refreshMe();
  if (app.me && app.me.logged_in) {
    const first = Object.keys(PAGES).find((k) => canSee(PAGES[k]));
    navigate(first || "login");
  } else {
    navigate("login");
  }
}

boot();
