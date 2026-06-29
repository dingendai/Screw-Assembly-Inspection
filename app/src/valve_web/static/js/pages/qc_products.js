import { api } from "../api.js";
import { h, toast } from "../app.js";

// 品項主檔：補齊只有條碼、沒有品名/規格的項目。
export async function renderQcProducts(view) {
  const mount = h("div", { class: "table-wrap" });

  async function load() {
    let data;
    try { data = await api.get("/api/qc/products"); }
    catch (e) { toast(e.message, "error"); return; }
    const rows = (data.products || []).map((p) => {
      const name = h("input", { type: "text", value: p.name || "", style: "width:160px" });
      const spec = h("input", { type: "text", value: p.spec || "", style: "width:160px" });
      const save = h("button", { class: "btn", onclick: async () => {
        try {
          await api.put("/api/qc/products/" + encodeURIComponent(p.barcode), { name: name.value, spec: spec.value });
          toast("已儲存 " + p.barcode, "ok");
        } catch (e) { toast(e.message, "error"); }
      } }, "儲存");
      return h("tr", {},
        h("td", {}, p.barcode),
        h("td", {}, name),
        h("td", {}, spec),
        h("td", {}, p.inspection_count),
        h("td", {}, p.created_at),
        h("td", {}, save),
      );
    });
    mount.innerHTML = "";
    mount.append(h("table", {},
      h("thead", {}, h("tr", {}, ...["條碼", "品名", "規格", "檢驗數", "建檔時間", ""].map((t) => h("th", {}, t)))),
      h("tbody", {}, ...(rows.length ? rows : [h("tr", {}, h("td", { colspan: "6", class: "muted" }, "（尚無品項，檢驗一次條碼後自動建檔）"))])),
    ));
  }

  view.append(h("div", { class: "card" },
    h("h2", {}, "品項主檔"),
    h("p", { class: "muted" }, "條碼為品項唯一鍵；同一條碼的多次檢驗會累計於檢驗數。可補上品名與規格。"),
    mount,
  ));

  load();
}
