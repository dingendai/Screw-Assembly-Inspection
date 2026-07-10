import { api } from "../api.js";
import { h, toast } from "../app.js";

export async function renderUsers(view) {
  let data;
  try { data = await api.get("/api/users"); } catch (e) { toast(e.message, "error"); return; }

  const roleKeys = Object.keys(data.role_labels);
  const permLabels = data.permission_labels || {};
  const configurable = data.configurable_permissions || [];

  // ---------- user accounts ----------
  const userBody = h("tbody", {});
  function userRow(u = { username: "", display_name: "", role: "operator", password: "", enabled: true }) {
    const username = h("input", { type: "text", value: u.username, style: "width:120px" });
    const display = h("input", { type: "text", value: u.display_name, style: "width:120px" });
    const role = h("select", {}, ...roleKeys.map((r) => h("option", { value: r }, `${data.role_labels[r]} (${r})`)));
    role.value = u.role;
    const pw = h("input", { type: "password", placeholder: u.password ? "（已設定，留空不變）" : "密碼", style: "width:140px" });
    const enabled = h("input", { type: "checkbox" }); enabled.checked = u.enabled;
    const tr = h("tr", {},
      h("td", {}, username), h("td", {}, display), h("td", {}, role), h("td", {}, pw), h("td", {}, enabled),
      h("td", {}, h("button", { class: "btn", onclick: () => tr.remove() }, "刪除")));
    tr._read = () => ({
      username: username.value.trim(), display_name: display.value.trim(), role: role.value,
      password: pw.value ? pw.value : u.password || "", enabled: enabled.checked,
    });
    return tr;
  }
  (data.users || []).forEach((u) => userBody.append(userRow(u)));

  async function saveUsers() {
    const items = [...userBody.children].map((tr) => tr._read()).filter((u) => u.username);
    try { data = await api.put("/api/users", items); toast("用戶已儲存", "ok"); }
    catch (e) { toast(e.message, "error"); }
  }

  view.append(h("div", { class: "card" },
    h("div", { class: "row" }, h("h2", { style: "flex:1" }, "用戶帳號"),
      h("button", { class: "btn", onclick: () => userBody.append(userRow()) }, "新增用戶"),
      h("button", { class: "btn btn-success", onclick: saveUsers }, "儲存用戶")),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ...["帳號", "顯示名稱", "角色", "密碼", "啟用", ""].map((t) => h("th", {}, t)))),
      userBody))
  ));

  // ---------- roles, labels, passwords, permissions ----------
  const roleRows = roleKeys.filter((r) => r !== data.protected_role).map((role) => {
    const label = h("input", { type: "text", value: data.role_labels[role], style: "width:120px" });
    const pw = h("input", { type: "password", placeholder: "留空不變", style: "width:120px" });
    const perms = data.role_permissions[role] || [];
    const checks = configurable.map((p) => {
      const cb = h("input", { type: "checkbox" }); cb.checked = perms.includes(p); cb._perm = p;
      return h("label", { style: "display:inline-block; margin-right:12px" }, cb, " " + (permLabels[p] || p));
    });
    return {
      role, label, pw, checks,
      node: h("div", { class: "card", style: "background:var(--panel-2)" },
        h("div", { class: "row" },
          h("div", { class: "col" }, h("label", {}, `角色代碼：${role}`), label),
          h("div", { class: "col" }, h("label", {}, "密鑰"), pw)),
        h("div", { style: "margin-top:8px" }, ...checks)),
    };
  });

  async function savePermissions() {
    const role_permissions = {}, role_labels = {}, role_passwords = {};
    for (const r of roleRows) {
      role_permissions[r.role] = r.checks.map((l) => l.firstChild).filter((cb) => cb.checked).map((cb) => cb._perm);
      role_labels[r.role] = r.label.value.trim() || r.role;
      if (r.pw.value) role_passwords[r.role] = r.pw.value;
    }
    try { data = await api.put("/api/permissions", { role_permissions, role_labels, role_passwords }); toast("角色權限已儲存", "ok"); }
    catch (e) { toast(e.message, "error"); }
  }

  view.append(h("div", { class: "card" },
    h("div", { class: "row" }, h("h2", { style: "flex:1" }, "角色位階與畫面權限"),
      h("button", { class: "btn btn-success", onclick: savePermissions }, "儲存角色權限")),
    h("p", { class: "muted" }, `開發者 (${data.protected_role}) 擁有全部權限，不可修改。`),
    ...roleRows.map((r) => r.node)
  ));
}
