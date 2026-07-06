import { api } from "../api.js";
import { h, toast, setCleanup } from "../app.js";
import { createDecisionSettingsCard } from "./decision.js";

export async function renderRegions(view) {
  let cfg;
  try { cfg = await api.get("/api/config"); } catch (e) { toast(e.message, "error"); return; }

  // Deep-ish working copy of region data per camera.
  const cams = cfg.cameras.map((c) => ({
    ...c,
    detection_regions: (c.detection_regions || []).map((r) => ({ ...r })),
    exclusion_regions: (c.exclusion_regions || []).map((r) => ({ ...r })),
  }));
  const ov = cfg.region_overlay || {};
  const modelNames = (cfg.models || []).map((m) => m.name);
  let decisionPanel = null;

  const slotSel = h("select", {}, ...cams.map((c) => h("option", { value: c.slot }, `Camera ${c.slot}`)));
  const enableBox = h("input", { type: "checkbox" });
  const modeSel = h("select", {}, h("option", { value: "detection" }, "偵測區 ROI"), h("option", { value: "exclusion" }, "排除區 EX"));
  const regionList = h("div", {});
  const decisionMount = h("div", {});

  const img = h("img", { style: "display:block; max-width:640px;" });
  const canvas = h("canvas", {});
  const wrap = h("div", { class: "region-canvas-wrap" }, img, canvas);

  function current() { return cams.find((c) => String(c.slot) === slotSel.value); }
  function listFor(cam) { return modeSel.value === "detection" ? cam.detection_regions : cam.exclusion_regions; }

  let sized = false;
  function loadSnapshot() {
    const slot = slotSel.value;
    sized = false;
    // Live stream as the drawing backdrop (multipart fires load per frame).
    img.onload = () => {
      if (!sized && img.clientWidth) {
        canvas.width = img.clientWidth;
        canvas.height = img.clientHeight;
        sized = true;
        redraw();
      }
    };
    img.src = `/api/stream/${slot}`;
    const cam = current();
    enableBox.checked = !!cam.region_detection_enabled;
    renderList();
    renderDecisionPanel();
  }
  setCleanup(() => { img.src = ""; });

  function redraw(preview) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cam = current();
    drawSet(ctx, cam.detection_regions, "#22c55e", "ROI");
    drawSet(ctx, cam.exclusion_regions, "#ef4444", "EX");
    if (preview) {
      ctx.strokeStyle = modeSel.value === "detection" ? "#22c55e" : "#ef4444";
      ctx.setLineDash([5, 4]);
      ctx.strokeRect(preview.x, preview.y, preview.w, preview.h);
      ctx.setLineDash([]);
    }
  }
  function drawSet(ctx, regions, color, label) {
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 2; ctx.font = "13px sans-serif";
    regions.forEach((r, i) => {
      const x = r.x * canvas.width, y = r.y * canvas.height, w = r.w * canvas.width, hh = r.h * canvas.height;
      ctx.strokeRect(x, y, w, hh);
      ctx.fillText(`${label}${i + 1}`, x + 3, y + 15);
    });
  }

  function modelCheckboxes(region) {
    if (!modelNames.length) return h("span", { class: "muted", style: "font-size:12px" }, "（無模型，套用全部）");
    region.model_names = region.model_names || [];
    return h("div", { style: "font-size:12px" }, ...modelNames.map((name) => {
      const cb = h("input", { type: "checkbox" });
      cb.checked = region.model_names.includes(name);
      cb.addEventListener("change", () => {
        const set = new Set(region.model_names);
        if (cb.checked) set.add(name); else set.delete(name);
        region.model_names = [...set];
      });
      return h("label", { style: "margin-right:10px" }, cb, " " + name);
    }));
  }

  function renderList() {
    regionList.innerHTML = "";
    const cam = current();
    [["detection", "偵測區 ROI", cam.detection_regions], ["exclusion", "排除區 EX", cam.exclusion_regions]].forEach(([kind, title, arr]) => {
      regionList.append(h("h4", {}, title));
      if (!arr.length) { regionList.append(h("p", { class: "muted" }, "（無）")); return; }
      arr.forEach((r, i) => {
        const head = h("div", { class: "row" },
          h("span", { class: "pill" }, `${i + 1}: x${r.x.toFixed(2)} y${r.y.toFixed(2)} w${r.w.toFixed(2)} h${r.h.toFixed(2)}`),
          h("button", { class: "btn", onclick: () => { arr.splice(i, 1); renderList(); redraw(); } }, "刪除"));
        const controls = h("div", { class: "row", style: "margin:4px 0 12px" });
        if (kind === "detection") {
          const roi = h("input", { type: "number", min: "0", max: "99", value: r.roi_id || 0, style: "width:70px" });
          roi.addEventListener("change", () => { const v = parseInt(roi.value) || 0; r.roi_id = v > 0 ? v : undefined; });
          controls.append(h("label", {}, "ROI 編號(0=不共用)"), roi);
        }
        controls.append(h("div", { class: "col" }, h("label", {}, "套用模型(不勾=全部)"), modelCheckboxes(r)));
        regionList.append(h("div", {}, head, controls));
      });
    });
  }

  function renderDecisionPanel() {
    const cam = current();
    decisionMount.innerHTML = "";
    decisionPanel = createDecisionSettingsCard(cfg, {
      cameraSlot: cam.slot,
      title: `Camera ${cam.slot} 判定設定`,
      buttonText: "儲存判定設定",
      showToast: false,
    });
    decisionMount.append(decisionPanel.card);
  }

  // ---- drawing interaction ----
  let dragging = null;
  canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    dragging = { sx: e.clientX - rect.left, sy: e.clientY - rect.top };
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    redraw({ x: Math.min(dragging.sx, x), y: Math.min(dragging.sy, y), w: Math.abs(x - dragging.sx), h: Math.abs(y - dragging.sy) });
  });
  canvas.addEventListener("mouseup", (e) => {
    if (!dragging) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    const px = Math.min(dragging.sx, x), py = Math.min(dragging.sy, y);
    const pw = Math.abs(x - dragging.sx), ph = Math.abs(y - dragging.sy);
    dragging = null;
    if (pw < 6 || ph < 6) { redraw(); return; }
    const region = {
      x: px / canvas.width, y: py / canvas.height,
      w: pw / canvas.width, h: ph / canvas.height,
      model_names: [],
    };
    listFor(current()).push(region);
    renderList(); redraw();
  });

  slotSel.addEventListener("change", loadSnapshot);
  enableBox.addEventListener("change", () => { current().region_detection_enabled = enableBox.checked; });

  // ---- overlay settings ----
  const showBox = h("input", { type: "checkbox" }); showBox.checked = ov.show_on_monitor !== false;
  const detColor = h("input", { type: "color", value: ov.detection_color || "#22c55e" });
  const excColor = h("input", { type: "color", value: ov.exclusion_color || "#ef4444" });

  async function save() {
    const payload = {
      cameras: cams.map((c) => ({
        slot: c.slot, device_index: c.device_index, enabled: c.enabled,
        flip_horizontal: c.flip_horizontal, flip_vertical: c.flip_vertical, rotation_degrees: c.rotation_degrees,
        assigned_model_names: c.assigned_model_names || [],
        region_detection_enabled: c.region_detection_enabled,
        detection_regions: c.detection_regions, exclusion_regions: c.exclusion_regions,
        barcode_read_enabled: c.barcode_read_enabled,
        focus_mode: c.focus_mode || "auto",
        manual_focus_value: c.manual_focus_value ?? 120,
      })),
      region_overlay: {
        show_on_monitor: showBox.checked,
        detection_color: detColor.value,
        exclusion_color: excColor.value,
      },
    };
    try {
      if (decisionPanel) await decisionPanel.save();
      await api.put("/api/config/regions", payload);
      toast("指定範圍與判定設定已儲存", "ok");
    }
    catch (e) { toast(e.message, "error"); }
  }

  view.append(
    h("div", { class: "card" },
      h("h2", {}, "指定範圍監視"),
      h("div", { class: "row" },
        h("div", { class: "col" }, h("label", {}, "相機"), slotSel),
        h("label", {}, enableBox, " 啟用此相機的範圍偵測"),
        h("div", { class: "col" }, h("label", {}, "繪製模式"), modeSel)
      ),
      h("p", { class: "muted" }, "在影像上拖曳滑鼠框出區域；座標會正規化為 0~1。"),
      h("div", { class: "row", style: "align-items:flex-start" },
        wrap,
        h("div", { style: "flex:1; min-width:260px" }, regionList, decisionMount),
      )
    ),
    h("div", { class: "card" },
      h("h2", {}, "監視疊圖設定"),
      h("div", { class: "row" },
        h("label", {}, showBox, " 在監視畫面顯示區域"),
        h("div", { class: "col" }, h("label", {}, "偵測區顏色"), detColor),
        h("div", { class: "col" }, h("label", {}, "排除區顏色"), excColor)
      ),
      h("div", { class: "row", style: "margin-top:12px" }, h("button", { class: "btn btn-success", onclick: save }, "儲存區域設定"))
    )
  );

  loadSnapshot();
}
