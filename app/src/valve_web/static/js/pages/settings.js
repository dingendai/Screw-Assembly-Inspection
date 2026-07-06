import { api } from "../api.js";
import { h, toast, setCleanup } from "../app.js";

export async function renderSettings(view) {
  let cfg;
  try { cfg = await api.get("/api/config"); } catch (e) { toast(e.message, "error"); return; }

  const modelNames = () => cfg.models.map((m) => m.name);

  // ---------- camera / general section ----------
  const simBox = h("input", { type: "checkbox" });
  simBox.checked = !!cfg.use_simulation;
  const opCamInput = h("input", { type: "number", value: cfg.operator_camera_index, style: "width:80px" });
  const detectedLabel = h("span", { class: "muted" }, cfg.detected_cameras?.length ? "偵測到：" + cfg.detected_cameras.join(", ") : "尚未掃描");

  async function scan() {
    toast("掃描相機中…");
    try {
      const r = await api.post("/api/config/cameras/scan");
      cfg.detected_cameras = r.detected_cameras;
      detectedLabel.textContent = "偵測到：" + (r.detected_cameras.join(", ") || "無");
    } catch (e) { toast(e.message, "error"); }
  }

  const camRows = cfg.cameras.map((c) => buildCameraRow(c, modelNames));
  const camTable = h("table", {},
    h("thead", {}, h("tr", {}, ...["啟用", "Slot", "裝置index", "水平翻轉", "垂直翻轉", "旋轉", "模型"].map((t) => h("th", {}, t)))),
    h("tbody", {}, ...camRows.map((r) => r.tr))
  );

  async function saveCameras() {
    const payload = {
      use_simulation: simBox.checked,
      operator_camera_index: parseInt(opCamInput.value) || 0,
      cameras: camRows.map((r) => r.read()),
    };
    try {
      cfg = await api.put("/api/config/cameras", payload);
      toast("相機設定已儲存", "ok");
    } catch (e) { toast("儲存失敗：" + e.message, "error"); }
  }

  // Live preview of a chosen running slot (reflects last-saved config).
  const previewImg = h("img", { alt: "preview",
    style: "width:100%; aspect-ratio:4/3; object-fit:contain; background:#000; border:1px solid var(--border); border-radius:10px; display:block" });
  const previewSel = h("select", {}, ...cfg.cameras.filter((c) => c.enabled).map((c) => h("option", { value: c.slot }, `Camera ${c.slot}`)));
  function loadPreview() { if (previewSel.value) previewImg.src = `/api/stream/${previewSel.value}`; }
  previewSel.addEventListener("change", loadPreview);
  setCleanup(() => { previewImg.src = ""; });

  // Left = controls + camera table + save; Right = live preview.
  const leftCol = h("div", { style: "flex:2; min-width:420px; display:flex; flex-direction:column; gap:14px" },
    h("h2", {}, "相機設定"),
    h("div", { class: "row" },
      h("label", {}, simBox, " 使用模擬相機"),
      h("div", { class: "col" }, h("label", {}, "操作者相機 index"), opCamInput),
      h("button", { class: "btn", onclick: scan }, "掃描相機"),
      detectedLabel
    ),
    h("div", { class: "table-wrap" }, camTable),
    h("div", { class: "row" },
      h("button", { class: "btn btn-success", onclick: saveCameras }, "儲存 / 套用相機設定"))
  );
  const rightCol = h("div", { style: "flex:1; min-width:300px; display:flex; flex-direction:column; gap:8px" },
    h("h2", {}, "即時預覽"),
    previewSel,
    previewImg,
    h("p", { class: "muted" }, "顯示目前已套用的相機；變更 device/翻轉等需按左側儲存後才會反映。")
  );

  view.append(h("div", { class: "card" },
    h("div", { class: "row", style: "align-items:flex-start; gap:24px" }, leftCol, rightCol)
  ));
  loadPreview();

  // ---------- models section ----------
  const modelsContainer = h("div", {});
  function renderModels() {
    modelsContainer.innerHTML = "";
    const rows = cfg.models.map((m) => {
      const enabled = h("input", { type: "checkbox" }); enabled.checked = m.enabled;
      const name = h("input", { type: "text", value: m.name, style: "width:160px" });
      const path = h("input", { type: "text", value: m.file_path, style: "width:360px" });
      return {
        tr: h("tr", {}, h("td", {}, enabled), h("td", {}, name), h("td", {}, path)),
        read: () => ({ name: name.value.trim(), file_path: path.value.trim(), enabled: enabled.checked, modality: m.modality || "vision" }),
      };
    });
    modelsContainer._rows = rows;
    modelsContainer.append(h("div", { class: "table-wrap" },
      h("table", {}, h("thead", {}, h("tr", {}, ...["啟用", "名稱", "權重檔路徑"].map((t) => h("th", {}, t)))), h("tbody", {}, ...rows.map((r) => r.tr)))
    ));
  }
  renderModels();

  async function rescan() {
    try { cfg = await api.post("/api/config/models/rescan"); renderModels(); toast("已重新搜尋模型", "ok"); }
    catch (e) { toast(e.message, "error"); }
  }
  async function saveModels() {
    try {
      cfg = await api.put("/api/config/models", { models: modelsContainer._rows.map((r) => r.read()) });
      renderModels();
      toast("模型設定已儲存", "ok");
    } catch (e) { toast(e.message, "error"); }
  }

  view.append(h("div", { class: "card" },
    h("div", { class: "row" }, h("h2", { style: "flex:1" }, "模型設定"),
      h("button", { class: "btn", onclick: rescan }, "重新搜尋模型"),
      h("button", { class: "btn btn-success", onclick: saveModels }, "儲存模型")),
    modelsContainer,
    h("p", { class: "muted" }, "模型權重會從 models/ 資料夾搜尋。相機可指定多個模型，於上方相機表格勾選。")
  ));
}

function buildCameraRow(c, modelNames) {
  const enabled = h("input", { type: "checkbox" }); enabled.checked = c.enabled;
  const dev = h("input", { type: "number", value: c.device_index, style: "width:70px" });
  const fh = h("input", { type: "checkbox" }); fh.checked = c.flip_horizontal;
  const fv = h("input", { type: "checkbox" }); fv.checked = c.flip_vertical;
  const rot = h("select", {}, ...[0, 90, 180, 270].map((d) => h("option", { value: d }, d + "°")));
  rot.value = c.rotation_degrees;
  const assigned = new Set(c.assigned_model_names || []);
  const modelChecks = modelNames().map((name) => {
    const cb = h("input", { type: "checkbox" }); cb.checked = assigned.has(name);
    cb._name = name;
    return h("label", { style: "display:block" }, cb, " " + name);
  });
  const modelCell = h("div", {}, ...(modelChecks.length ? modelChecks : [h("span", { class: "muted" }, "無可用模型")]));

  return {
    tr: h("tr", {},
      h("td", {}, enabled), h("td", {}, "C" + c.slot), h("td", {}, dev),
      h("td", {}, fh), h("td", {}, fv), h("td", {}, rot), h("td", {}, modelCell)),
    read: () => ({
      slot: c.slot,
      device_index: parseInt(dev.value) || 0,
      enabled: enabled.checked,
      flip_horizontal: fh.checked,
      flip_vertical: fv.checked,
      rotation_degrees: parseInt(rot.value) || 0,
      assigned_model_names: modelChecks.map((l) => l.firstChild).filter((cb) => cb.checked).map((cb) => cb._name),
      region_detection_enabled: c.region_detection_enabled,
      detection_regions: c.detection_regions || [],
      exclusion_regions: c.exclusion_regions || [],
    }),
  };
}
