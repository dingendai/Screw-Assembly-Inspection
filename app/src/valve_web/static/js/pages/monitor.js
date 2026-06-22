import { api } from "../api.js";
import { h, toast, setCleanup } from "../app.js";

let pollTimer = null;

export async function renderMonitor(view) {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }

  let status = { active_slots: [], status: {} };
  try { status = await api.get("/api/cameras/status"); } catch (e) { toast(e.message, "error"); }
  const slots = status.active_slots || [];

  // Stop the poll timer, close MJPEG connections and halt any server-side
  // continuous inspection when leaving this page.
  setCleanup(() => {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    view.querySelectorAll("img").forEach((im) => { im.src = ""; });
    if (continuous) { api.post("/api/inspect/continuous/stop").catch(() => {}); }
  });

  const partInput = h("input", { type: "text", placeholder: "工件編號（可留空自動產生）" });
  const resultBig = h("div", { class: "result-big result-wait" }, "WAITING");
  const confLabel = h("div", { class: "muted", style: "text-align:center" }, "Confidence: --");
  const reasons = h("div", {});
  const roiBox = h("div", {});

  const tiles = slots.map((slot) =>
    h("div", { class: "cam-tile" },
      h("div", { class: "cam-title" }, `Camera ${slot}`),
      // No cache-buster: MJPEG is a live stream; a ?t= query forces the browser
      // to open a brand-new connection on every render and exhaust the per-host
      // connection limit.
      h("img", { src: `/api/stream/${slot}`, alt: `camera ${slot}` })
    )
  );
  const grid = h("div", { class: "grid-cams" }, ...(tiles.length ? tiles : [h("div", { class: "card" }, "沒有啟用的相機，請至『相機設定』啟用。")]));

  const fmtConf = (v) => (typeof v === "number" ? v.toFixed(3) : "--");

  function applyResult(r) {
    if (!r || !r.result) return;
    resultBig.textContent = r.result;
    resultBig.className = "result-big " + (r.result === "PASS" ? "result-pass" : "result-ng");
    confLabel.textContent = `Confidence: ${fmtConf(r.confidence)}`;
    reasons.innerHTML = "";
    const cams = r.camera_results || {};
    Object.keys(cams).sort().forEach((slot) => {
      const c = cams[slot];
      const box = h("div", { class: "reason-box " + (c.result === "PASS" ? "reason-pass" : "reason-ng") },
        h("strong", {}, `Camera ${slot}: ${c.result} (${fmtConf(c.confidence)})`),
        ...(c.reasons || []).map((x) => h("div", {}, "• " + x))
      );
      reasons.append(box);
    });
    roiBox.innerHTML = "";
    const rois = r.roi_confirmations || {};
    const rids = Object.keys(rois);
    if (rids.length) {
      roiBox.append(h("h3", {}, "ROI 確認"));
      rids.sort().forEach((rid) => {
        const info = rois[rid];
        roiBox.append(h("div", { class: "reason-box " + (info.confirmed ? "reason-pass" : "reason-ng") },
          `ROI ${rid}: ${info.confirmed ? "已確認" : "未確認"} (${info.votes}/${info.total})`));
      });
    }
  }

  const inspectBtn = h("button", { class: "btn btn-success", onclick: doInspect }, "單次檢測");
  const contBtn = h("button", { class: "btn", onclick: toggleContinuous }, "連續檢測");
  let continuous = false;

  async function doInspect() {
    inspectBtn.disabled = true;
    try {
      const r = await api.post("/api/inspect?part_id=" + encodeURIComponent(partInput.value.trim()));
      applyResult(r);
    } catch (e) { toast("檢測失敗：" + e.message, "error"); }
    finally { inspectBtn.disabled = false; }
  }

  async function toggleContinuous() {
    try {
      if (!continuous) {
        await api.post("/api/inspect/continuous/start?part_id=" + encodeURIComponent(partInput.value.trim()));
        continuous = true;
        contBtn.textContent = "停止連續檢測";
        contBtn.classList.add("btn-danger");
        inspectBtn.disabled = true;
        pollTimer = setInterval(async () => {
          try { applyResult(await api.get("/api/results/latest")); } catch {}
        }, 600);
      } else {
        await api.post("/api/inspect/continuous/stop");
        stopContinuous();
      }
    } catch (e) { toast(e.message, "error"); }
  }

  function stopContinuous() {
    continuous = false;
    contBtn.textContent = "連續檢測";
    contBtn.classList.remove("btn-danger");
    inspectBtn.disabled = false;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  view.append(
    h("div", { class: "card" },
      h("div", { class: "row" }, h("div", { class: "col", style: "flex:1" }, h("label", {}, "工件編號"), partInput), inspectBtn, contBtn)
    ),
    h("div", { class: "row", style: "align-items:flex-start" },
      h("div", { style: "flex:2; min-width:320px" }, grid),
      h("div", { class: "card", style: "flex:1; min-width:280px" }, resultBig, confLabel, reasons, roiBox)
    )
  );
}
