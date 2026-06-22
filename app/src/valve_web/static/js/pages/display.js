import { api } from "../api.js";
import { h, toast, applyFontSize } from "../app.js";

export async function renderDisplay(view) {
  let cfg;
  try { cfg = await api.get("/api/config"); } catch (e) { toast(e.message, "error"); return; }
  const d = cfg.display || { font_size: 14, mode: "auto", width: 1440, height: 900 };

  const size = h("input", { type: "range", min: "10", max: "28", value: d.font_size, style: "width:240px" });
  const sizeLabel = h("span", {}, `${d.font_size}px`);
  size.addEventListener("input", () => {
    sizeLabel.textContent = size.value + "px";
    applyFontSize(size.value);  // live preview
  });

  async function save() {
    try {
      cfg = await api.put("/api/config/display", {
        mode: d.mode || "auto",
        width: d.width || 1440,
        height: d.height || 900,
        font_size: parseInt(size.value) || 14,
      });
      applyFontSize(size.value);
      toast("顯示設定已儲存", "ok");
    } catch (e) { toast(e.message, "error"); }
  }

  view.append(h("div", { class: "card" },
    h("h2", {}, "顯示設定"),
    h("div", { class: "col" }, h("label", {}, "介面字級"), h("div", { class: "row" }, size, sizeLabel)),
    h("p", { class: "muted" }, "全螢幕請用瀏覽器 F11；視窗大小用瀏覽器縮放（Ctrl +/-）。字級會套用到整個介面並與桌面版共用設定。"),
    h("div", { class: "row", style: "margin-top:12px" }, h("button", { class: "btn btn-success", onclick: save }, "儲存顯示設定"))
  ));
}
