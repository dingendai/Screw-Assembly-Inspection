import { h } from "../app.js";

// 說明頁：兩個子分頁 —— 使用者操作手冊 / 關於
// 內容由使用者後續提供，這裡先建立空白結構與占位區塊。

function renderManual() {
  // 使用者操作手冊：內容待匯入。把文字 / HTML 放進下方的 #manual-body 即可。
  return h("div", { class: "col", style: "gap:12px" },
    h("div", { id: "manual-body", class: "muted" },
      "（使用者操作手冊內容待匯入）")
  );
}

function renderAbout() {
  // 關於：比照業界軟體 —— 致謝、開發者、版本資訊。內容待填。
  const section = (title, ...body) =>
    h("div", { class: "col", style: "gap:6px; margin-bottom:18px" },
      h("h3", {}, title), ...body);

  return h("div", { class: "col", style: "gap:4px" },
    section("致謝",
      h("p", { class: "muted" }, "（致謝對象待填）")),
    section("開發者",
      h("p", { class: "muted" }, "（開發者資訊待填）")),
    section("版本資訊",
      h("p", { class: "muted" }, "（詳細版本內容待填）"))
  );
}

export async function renderHelp(view) {
  const tabs = [
    { key: "manual", label: "使用者操作手冊", render: renderManual },
    { key: "about", label: "關於", render: renderAbout },
  ];
  let active = "manual";

  const body = h("div", {});
  const tabBar = h("div", { class: "row", style: "gap:8px; margin-bottom:14px" });

  function show(key) {
    active = key;
    body.innerHTML = "";
    body.append(tabs.find((t) => t.key === key).render());
    Array.from(tabBar.children).forEach((b) =>
      b.classList.toggle("active", b.dataset.key === key));
  }

  tabs.forEach((t) => {
    const btn = h("button", { class: "nav-btn", onclick: () => show(t.key) }, t.label);
    btn.dataset.key = t.key;
    tabBar.append(btn);
  });

  view.append(h("div", { class: "card" },
    h("h2", {}, "說明"),
    tabBar,
    body
  ));
  show(active);
}
