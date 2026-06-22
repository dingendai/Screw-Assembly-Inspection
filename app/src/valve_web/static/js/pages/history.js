import { api, downloadCsv } from "../api.js";
import { h, toast } from "../app.js";

export async function renderHistory(view) {
  let data;
  try { data = await api.get("/api/records"); } catch (e) { toast(e.message, "error"); return; }

  const recCols = ["時間", "操作者", "角色", "結果", "工件", "相機", "信心度", "備註"];
  const recRows = (data.records || []).map((r) => h("tr", {},
    h("td", {}, r.timestamp || ""),
    h("td", {}, r.operator_name || ""),
    h("td", {}, r.role_label || r.operator_role || ""),
    h("td", {}, r.result || ""),
    h("td", {}, r.part_id || ""),
    h("td", {}, r.active_cameras || ""),
    h("td", {}, r.confidence || ""),
    h("td", {}, r.note || "")
  ));

  const recCard = h("div", { class: "card" },
    h("div", { class: "row" },
      h("h2", { style: "flex:1" }, "檢測歷史紀錄"),
      data.can_export ? h("button", { class: "btn btn-primary", onclick: () => downloadCsv("/api/records/export") }, "匯出檢測 CSV") : null
    ),
    h("div", { class: "table-wrap" },
      h("table", {}, h("thead", {}, h("tr", {}, ...recCols.map((c) => h("th", {}, c)))), h("tbody", {}, ...recRows))
    ),
    recRows.length ? null : h("p", { class: "muted" }, "目前沒有檢測紀錄。")
  );
  view.append(recCard);

  if (data.can_view_sessions) {
    const sCols = ["操作者", "角色", "登入時間", "登出時間", "照片"];
    const sRows = (data.sessions || []).map((s) => h("tr", {},
      h("td", {}, s.operator_name || ""),
      h("td", {}, s.role_label || s.operator_role || ""),
      h("td", {}, s.login_time || ""),
      h("td", {}, s.logout_time || ""),
      h("td", {}, s.photo_path || "")
    ));
    view.append(h("div", { class: "card" },
      h("div", { class: "row" },
        h("h2", { style: "flex:1" }, "操作者登入 / 登出紀錄"),
        data.can_export ? h("button", { class: "btn", onclick: () => downloadCsv("/api/sessions/export") }, "匯出登入紀錄 CSV") : null
      ),
      h("div", { class: "table-wrap" },
        h("table", {}, h("thead", {}, h("tr", {}, ...sCols.map((c) => h("th", {}, c)))), h("tbody", {}, ...sRows))
      )
    ));
  }
}
