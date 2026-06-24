import { api } from "../api.js";
import { app, h, toast, refreshMe, navigate, setCleanup, syncThemeFromServer, applyFontSize } from "../app.js";

// Per-role field rules:
//   developer -> password only (no name, no photo)
//   operator  -> name + photo  (no password)
//   manager / others -> name + password (no photo)
function ruleFor(role, developerRole) {
  if (role === developerRole) return { name: false, pw: true, photo: false };
  if (role === "operator") return { name: true, pw: false, photo: true };
  return { name: true, pw: true, photo: false };
}

export async function renderLogin(view) {
  let data;
  try { data = await api.get("/api/roles"); }
  catch (e) { view.append(h("div", { class: "card" }, "無法載入角色：" + e.message)); return; }
  const roles = data.roles || [];
  const DEVELOPER = data.developer_role || "developer";
  if (data.theme) syncThemeFromServer(data.theme);
  if (data.font_size) applyFontSize(data.font_size);
  let camIndex = data.operator_camera_index ?? 0;
  let photoPath = "";

  // ---- left: form fields ----
  const roleSel = h("select", {}, ...roles.map((r) => h("option", { value: r.value }, `${r.label} (${r.value})`)));
  const nameInput = h("input", { type: "text", placeholder: "操作者姓名" });
  const pwInput = h("input", { type: "password", placeholder: "密碼" });
  const nameRow = h("div", { class: "col" }, h("label", {}, "姓名"), nameInput);
  const pwRow = h("div", { class: "col" }, h("label", {}, "密碼"), pwInput);

  // ---- right: camera + photo ----
  const camSel = h("select", {});
  const scanBtn = h("button", { class: "btn", onclick: scanCameras }, "掃描相機");
  const preview = h("img", { alt: "operator preview",
    style: "width:100%; aspect-ratio:4/3; object-fit:contain; background:#000; border:1px solid var(--border); border-radius:10px; display:block" });
  const photoStatus = h("span", { class: "muted" }, "尚未拍照");
  const photoBtn = h("button", { class: "btn btn-primary", onclick: capturePhoto }, "拍攝照片");
  const rightCol = h("div", { style: "flex:1; min-width:320px; display:flex; flex-direction:column; gap:8px" },
    h("h2", {}, "拍攝相機"),
    h("div", { class: "row" }, h("div", { class: "col", style: "flex:1" }, h("label", {}, "選擇相機"), camSel), scanBtn),
    preview,
    h("div", { class: "row" }, photoBtn, photoStatus)
  );

  function setCamOptions(list, selected) {
    camSel.innerHTML = "";
    (list.length ? list : [camIndex]).forEach((i) =>
      camSel.append(h("option", { value: i }, `Camera index ${i}`)));
    camSel.value = String(selected ?? (list[0] ?? camIndex));
  }
  setCamOptions([camIndex], camIndex);

  function startPreview() {
    camIndex = parseInt(camSel.value) || 0;
    preview.src = `/api/operator/stream?index=${camIndex}&t=${Date.now()}`;
  }
  function stopPreview() {
    preview.src = "";
    api.post("/api/operator/preview/stop").catch(() => {});
  }
  camSel.addEventListener("change", () => { photoPath = ""; photoStatus.textContent = "尚未拍照"; startPreview(); });

  async function scanCameras() {
    scanBtn.disabled = true; scanBtn.textContent = "掃描中…";
    try {
      const r = await api.get("/api/operator/cameras");
      setCamOptions(r.cameras || [], (r.cameras || []).includes(r.current) ? r.current : (r.cameras || [])[0]);
      toast(r.cameras?.length ? `找到相機：${r.cameras.join(", ")}` : "未偵測到相機", r.cameras?.length ? "ok" : "error");
      startPreview();
    } catch (e) { toast(e.message, "error"); }
    finally { scanBtn.disabled = false; scanBtn.textContent = "掃描相機"; }
  }

  async function capturePhoto() {
    photoBtn.disabled = true; photoStatus.textContent = "擷取中…";
    try {
      const r = await api.post(`/api/operator-photo?index=${parseInt(camSel.value) || 0}`);
      photoPath = r.photo_path;
      photoStatus.textContent = "已拍照 ✔";
    } catch (e) { toast("拍照失敗：" + e.message, "error"); photoStatus.textContent = "拍照失敗"; }
    finally { photoBtn.disabled = false; }
  }

  // ---- role-driven visibility ----
  function syncRole() {
    const rule = ruleFor(roleSel.value, DEVELOPER);
    nameRow.classList.toggle("hidden", !rule.name);
    pwRow.classList.toggle("hidden", !rule.pw);
    rightCol.classList.toggle("hidden", !rule.photo);
    if (rule.photo) startPreview(); else stopPreview();
  }
  roleSel.addEventListener("change", () => { photoPath = ""; photoStatus.textContent = "尚未拍照"; syncRole(); });
  setCleanup(stopPreview);

  async function submit() {
    const role = roleSel.value;
    const rule = ruleFor(role, DEVELOPER);
    if (rule.name && !nameInput.value.trim()) { toast("請輸入操作者姓名", "error"); return; }
    if (rule.photo && !photoPath) { toast("請先拍攝操作者照片", "error"); return; }
    try {
      app.me = await api.post("/api/login", {
        role,
        password: rule.pw ? pwInput.value : "",
        name: rule.name ? nameInput.value.trim() : "",
        photo_path: rule.photo ? photoPath : "",
      });
      await refreshMe();
      toast("登入成功", "ok");
      navigate("monitor");
    } catch (e) { toast("登入失敗：" + e.message, "error"); }
  }
  pwInput.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });

  const leftCol = h("div", { style: "flex:1; min-width:300px; display:flex; flex-direction:column; gap:12px" },
    h("h2", {}, "操作者登入"),
    h("div", { class: "col" }, h("label", {}, "角色"), roleSel),
    nameRow,
    pwRow,
    h("div", { class: "row", style: "margin-top:6px" }, h("button", { class: "btn btn-success", onclick: submit }, "登入"))
  );

  view.append(h("div", { class: "card" },
    h("div", { class: "row", style: "align-items:flex-start; gap:28px" }, leftCol, rightCol)
  ));
  syncRole();
}
