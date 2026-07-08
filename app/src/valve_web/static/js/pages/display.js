import { api } from "../api.js";
import { h, toast, applyFontSize, applyTheme } from "../app.js";

export async function renderDisplay(view) {
  let cfg;
  try { cfg = await api.get("/api/config"); } catch (e) { toast(e.message, "error"); return; }
  const d = cfg.display || { font_size: 18, mode: "auto", width: 1440, height: 900, theme: "dark" };
  const fontSizes = [10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28];
  if (!fontSizes.includes(parseInt(d.font_size))) fontSizes.push(parseInt(d.font_size) || 18);
  fontSizes.sort((a, b) => a - b);

  const size = h("select", {},
    ...fontSizes.map((value) => h("option", { value, selected: value === parseInt(d.font_size) }, `${value} px`)));
  size.value = String(parseInt(d.font_size) || 18);
  size.addEventListener("change", () => {
    applyFontSize(size.value);  // live preview
  });

  const themeSel = h("select", {},
    h("option", { value: "dark" }, "深色模式"),
    h("option", { value: "light" }, "淺色模式"));
  themeSel.value = d.theme || "dark";
  themeSel.addEventListener("change", () => applyTheme(themeSel.value));  // live preview

  async function save() {
    try {
      cfg = await api.put("/api/config/display", {
        mode: d.mode || "auto",
        width: d.width || 1440,
        height: d.height || 900,
        font_size: parseInt(size.value) || 18,
        theme: themeSel.value,
      });
      applyFontSize(size.value);
      applyTheme(themeSel.value);
      toast("顯示設定已儲存", "ok");
    } catch (e) { toast(e.message, "error"); }
  }

  view.append(h("div", { class: "card" },
    h("h2", {}, "顯示設定"),
    h("div", { class: "col" }, h("label", {}, "介面字級"), size),
    h("div", { class: "col", style: "margin-top:8px" }, h("label", {}, "佈景主題"), themeSel),
    h("p", { class: "muted" }, "字級與主題會即時預覽並儲存到後端，可跨裝置 / 與桌面版共用。全螢幕請用瀏覽器 F11。"),
    h("div", { class: "row", style: "margin-top:12px" }, h("button", { class: "btn btn-success", onclick: save }, "儲存顯示設定"))
  ));
}
