import { api } from "../api.js";
import { app, h, toast, refreshMe, navigate, setCleanup } from "../app.js";

export async function renderLogin(view) {
  let roles = [];
  try {
    const data = await api.get("/api/roles");
    roles = data.roles || [];
  } catch (e) {
    view.append(h("div", { class: "card" }, "無法載入角色：" + e.message));
    return;
  }

  let photoPath = "";
  const DEVELOPER = "developer";

  const roleSel = h("select", {}, ...roles.map((r) => h("option", { value: r.value }, `${r.label} (${r.value})`)));
  const nameInput = h("input", { type: "text", placeholder: "操作者姓名" });
  const pwInput = h("input", { type: "password", placeholder: "密鑰（若有設定）" });
  const photoStatus = h("span", { class: "muted" }, "尚未拍照");
  const photoBtn = h("button", { class: "btn", onclick: capturePhoto }, "拍攝操作者照片");
  const preview = h("img", { alt: "operator preview",
    style: "width:320px; aspect-ratio:4/3; object-fit:contain; background:#000; border:1px solid var(--border); border-radius:8px; display:block" });

  const photoRow = h("div", { class: "col" },
    h("label", {}, "操作者相機即時預覽"),
    preview,
    h("div", { class: "row" }, photoBtn, photoStatus)
  );

  function isDeveloper() { return roleSel.value === DEVELOPER; }
  function startPreview() {
    preview.src = `/api/operator/stream?t=${Date.now()}`;
  }
  function stopPreview() {
    preview.src = "";
    api.post("/api/operator/preview/stop").catch(() => {});
  }
  function syncVisibility() {
    const dev = isDeveloper();
    photoRow.classList.toggle("hidden", dev);
    if (dev) stopPreview(); else startPreview();
  }
  roleSel.addEventListener("change", syncVisibility);
  setCleanup(stopPreview);

  async function capturePhoto() {
    photoBtn.disabled = true;
    photoStatus.textContent = "擷取中…";
    try {
      const r = await api.post("/api/operator-photo");
      photoPath = r.photo_path;
      photoStatus.textContent = "已拍照 ✔";
    } catch (e) {
      toast("拍照失敗：" + e.message, "error");
      photoStatus.textContent = "拍照失敗";
    } finally {
      photoBtn.disabled = false;
    }
  }

  async function submit() {
    const role = roleSel.value;
    const body = { role, password: pwInput.value, name: nameInput.value.trim(), photo_path: photoPath };
    if (role !== DEVELOPER && !body.name) { toast("請輸入操作者姓名", "error"); return; }
    try {
      app.me = await api.post("/api/login", body);
      await refreshMe();
      toast("登入成功", "ok");
      navigate("monitor");
    } catch (e) {
      toast("登入失敗：" + e.message, "error");
    }
  }

  const card = h("div", { class: "card" },
    h("h2", {}, "操作者登入"),
    h("div", { class: "col" }, h("label", {}, "角色"), roleSel),
    h("div", { class: "col" }, h("label", {}, "姓名"), nameInput),
    h("div", { class: "col" }, h("label", {}, "密鑰"), pwInput),
    photoRow,
    h("div", { class: "row", style: "margin-top:14px" },
      h("button", { class: "btn btn-primary", onclick: submit }, "登入")),
    h("p", { class: "muted" }, "預設：開發者密鑰 0000 / 管理者 1234 / 作業員 無。非開發者需拍照。")
  );
  view.append(h("div", { class: "login-wrap" }, card));
  pwInput.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  syncVisibility();
}
