import { api } from "../api.js";
import { h, toast } from "../app.js";

export async function renderQcSystem(view) {
  let data;
  try {
    data = await api.get("/api/users");
  } catch (e) {
    toast(e.message, "error");
    return;
  }

  const qcOutput = h("input", {
    type: "text",
    value: data.qc_output_dir || "",
    style: "width: min(760px, 100%)",
  });

  async function saveQcOutput() {
    try {
      data = await api.put("/api/users/qc-output", { qc_output_dir: qcOutput.value.trim() });
      qcOutput.value = data.qc_output_dir || qcOutput.value;
      toast("品管資料位置已儲存", "ok");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  view.append(h("div", { class: "card" },
    h("div", { class: "row" },
      h("h2", { style: "flex:1" }, "品管系統"),
      h("button", { class: "btn btn-success", onclick: saveQcOutput }, "儲存位置")
    ),
    h("p", { class: "muted" }, "檢測 CSV、SQLite 品管資料庫、操作者照片與個人紀錄都會寫入此資料夾。"),
    h("label", {}, "品管資料位置"),
    qcOutput
  ));
}
