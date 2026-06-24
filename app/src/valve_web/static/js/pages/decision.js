import { api } from "../api.js";
import { h, toast } from "../app.js";

export function createDecisionSettingsCard(cfg, options = {}) {
  const dec = cfg.decision || { pass_confidence_threshold: 0.5, model_rules: {} };
  const title = options.title || "判定設定";
  const buttonText = options.buttonText || "儲存判定設定";
  const showToast = options.showToast !== false;
  const onSaved = options.onSaved;

  const globalInput = h("input", {
    type: "number",
    step: "0.01",
    min: "0",
    max: "1",
    value: dec.pass_confidence_threshold,
    style: "width:100px",
  });

  const rows = [];
  for (const c of cfg.cameras || []) {
    if (!c.enabled) continue;
    for (const name of (c.assigned_model_names || [])) {
      const key = `${c.slot}::${name}`;
      const rule = dec.model_rules[key] || {};
      const conf = h("input", {
        type: "number",
        step: "0.01",
        min: "0",
        max: "1",
        value: rule.confidence_threshold ?? dec.pass_confidence_threshold,
        style: "width:100px",
      });
      const count = h("input", {
        type: "number",
        min: "0",
        value: rule.required_object_count ?? 1,
        style: "width:80px",
      });
      rows.push({
        key,
        tr: h("tr", {},
          h("td", {}, `C${c.slot}`),
          h("td", {}, name),
          h("td", {}, conf),
          h("td", {}, count),
        ),
        read: () => [key, {
          confidence_threshold: parseFloat(conf.value) || 0,
          required_object_count: parseInt(count.value) || 0,
        }],
      });
    }
  }

  async function save() {
    const model_rules = {};
    for (const r of rows) {
      const [key, value] = r.read();
      model_rules[key] = value;
    }
    const updated = await api.put("/api/config/decision", {
      pass_confidence_threshold: parseFloat(globalInput.value) || 0,
      model_rules,
    });
    cfg.decision = updated.decision;
    if (showToast) toast("判定設定已儲存", "ok");
    if (onSaved) onSaved(updated);
    return updated;
  }

  const card = h("div", { class: "card" },
    h("h2", {}, title),
    h("div", { class: "row" },
      h("div", { class: "col" },
        h("label", {}, "全域 PASS 信心門檻 (0~1)"),
        globalInput,
      ),
    ),
    h("h3", {}, "Camera / 模型判定規則"),
    rows.length
      ? h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {},
            ...["相機", "模型", "信心門檻", "必要數量"].map((text) => h("th", {}, text)),
          )),
          h("tbody", {}, ...rows.map((r) => r.tr)),
        ))
      : h("p", { class: "muted" }, "目前沒有啟用的 Camera / 模型判定規則。"),
    h("div", { class: "row", style: "margin-top:12px" },
      h("button", {
        class: "btn btn-success",
        onclick: async () => {
          try { await save(); }
          catch (e) { toast(e.message, "error"); }
        },
      }, buttonText),
    ),
  );

  return { card, save };
}

export async function renderDecision(view) {
  let cfg;
  try {
    cfg = await api.get("/api/config");
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  view.append(createDecisionSettingsCard(cfg).card);
}
