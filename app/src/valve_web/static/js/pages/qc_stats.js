import { api, downloadCsv } from "../api.js";
import { h, toast } from "../app.js";

// 品管統計 / 歷史查詢頁：不良率統計、NG 品項排行、條件查詢與匯出。
export async function renderQcStats(view) {
  const barcodeInput = h("input", { type: "text", placeholder: "條碼（留空=全部）", style: "width:200px" });
  const startInput = h("input", { type: "date", style: "width:150px" });
  const endInput = h("input", { type: "date", style: "width:150px" });
  const resultSel = h("select", {},
    h("option", { value: "" }, "全部判定"),
    h("option", { value: "PASS" }, "PASS"),
    h("option", { value: "NG" }, "NG"),
  );

  const statBox = h("div", { class: "row", style: "gap:24px; flex-wrap:wrap" });
  const tableMount = h("div", { class: "table-wrap" });
  const rankMount = h("div", { class: "table-wrap" });

  function query() {
    const p = new URLSearchParams();
    if (barcodeInput.value.trim()) p.set("barcode", barcodeInput.value.trim());
    if (startInput.value) p.set("start", startInput.value);
    if (endInput.value) p.set("end", endInput.value);
    if (resultSel.value) p.set("result", resultSel.value);
    return p;
  }

  function statCard(label, value, kind) {
    return h("div", { class: "col", style: "min-width:120px" },
      h("div", { class: "muted" }, label),
      h("div", { style: "font-size:26px; font-weight:700" + (kind ? `; color:${kind}` : "") }, value));
  }

  async function loadStats() {
    const p = new URLSearchParams();
    if (barcodeInput.value.trim()) p.set("barcode", barcodeInput.value.trim());
    let s;
    try { s = await api.get("/api/qc/stats?" + p.toString()); }
    catch (e) { toast(e.message, "error"); return; }
    statBox.innerHTML = "";
    statBox.append(
      statCard("總檢驗數", s.total, ""),
      statCard("PASS", s.ok, "#22c55e"),
      statCard("NG", s.ng, "#ef4444"),
      statCard("不良率", s.ng_rate + " %", s.ng_rate > 0 ? "#ef4444" : ""),
    );
  }

  async function loadHistory() {
    let data;
    try { data = await api.get("/api/qc/history?" + query().toString()); }
    catch (e) { toast(e.message, "error"); return; }
    const rows = (data.records || []).map((r) => h("tr", {},
      h("td", {}, r.inspected_at),
      h("td", {}, r.barcode),
      h("td", {}, r.product_name || "—"),
      h("td", { style: r.result === "NG" ? "color:#ef4444; font-weight:700" : "color:#22c55e" }, r.result),
      h("td", {}, r.operator || "—"),
      h("td", {}, r.confidence || "—"),
      h("td", {}, r.note || ""),
    ));
    tableMount.innerHTML = "";
    tableMount.append(h("table", {},
      h("thead", {}, h("tr", {}, ...["時間", "條碼", "品名", "判定", "操作者", "信心", "備註"].map((t) => h("th", {}, t)))),
      h("tbody", {}, ...(rows.length ? rows : [h("tr", {}, h("td", { colspan: "7", class: "muted" }, "（無資料）"))])),
    ));
  }

  async function loadRanking() {
    let data;
    try { data = await api.get("/api/qc/ranking?top=10"); }
    catch (e) { toast(e.message, "error"); return; }
    const rows = (data.ranking || []).map((r, i) => h("tr", {},
      h("td", {}, i + 1),
      h("td", {}, r.barcode),
      h("td", {}, r.product_name || "—"),
      h("td", {}, r.total),
      h("td", { style: "color:#ef4444; font-weight:700" }, r.ng),
      h("td", { style: "color:#ef4444" }, r.ng_rate + " %"),
    ));
    rankMount.innerHTML = "";
    rankMount.append(h("table", {},
      h("thead", {}, h("tr", {}, ...["#", "條碼", "品名", "總數", "NG", "不良率"].map((t) => h("th", {}, t)))),
      h("tbody", {}, ...(rows.length ? rows : [h("tr", {}, h("td", { colspan: "6", class: "muted" }, "（尚無 NG 紀錄）"))])),
    ));
  }

  async function refresh() { await Promise.all([loadStats(), loadHistory(), loadRanking()]); }
  function exportCsv() { downloadCsv("/api/qc/history/export?" + query().toString()); }

  view.append(
    h("div", { class: "card" },
      h("h2", {}, "品管統計"),
      statBox,
    ),
    h("div", { class: "card" },
      h("div", { class: "row", style: "gap:10px; flex-wrap:wrap; align-items:flex-end" },
        h("div", { class: "col" }, h("label", {}, "條碼"), barcodeInput),
        h("div", { class: "col" }, h("label", {}, "起"), startInput),
        h("div", { class: "col" }, h("label", {}, "迄"), endInput),
        h("div", { class: "col" }, h("label", {}, "判定"), resultSel),
        h("button", { class: "btn btn-primary", onclick: refresh }, "查詢"),
        h("button", { class: "btn", onclick: exportCsv }, "匯出 CSV"),
      ),
      tableMount,
    ),
    h("div", { class: "card" },
      h("h2", {}, "NG 品項排行（不良率前 10）"),
      rankMount,
    ),
  );

  refresh();
}
