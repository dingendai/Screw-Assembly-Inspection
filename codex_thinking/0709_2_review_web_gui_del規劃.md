# Web GUI 刪除規劃報告

日期：2026-07-09

## 目的

本文件整理 5 人 agent 對專案內「網頁設計 code / Web GUI」的掃描結果，並分析若刪除相關檔案，是否會影響整體運行。

本次僅做分析與規劃，不修改、不刪除任何程式碼。

## 掃描結論

專案內確實存在 Web GUI code，主要集中在：

```text
app/src/valve_web/
```

此 Web GUI 不是 React、Vue、Angular、Svelte、Next、Vite、Tailwind 或 Bootstrap 專案，而是：

```text
FastAPI 後端 + 靜態 HTML/CSS/原生 JavaScript ES Modules
```

專案主入口 `main.py` 啟動的是 PyQt6 桌面 GUI，主要匯入 `valve_gui`，目前沒有看到桌面 GUI 主流程直接依賴 `valve_web`。

## Web GUI 前端檔案

| 類型 | 路徑 | 用途 | 刪除影響 |
| --- | --- | --- | --- |
| HTML 入口 | `app/src/valve_web/static/index.html` | Web 首頁骨架，載入 CSS 與 JS | Web 首頁無法正常顯示 |
| CSS 設計 | `app/src/valve_web/static/css/app.css` | Web UI 樣式、深色/淺色主題、卡片、按鈕、表格、toast、modal、相機 grid | Web UI 失去樣式 |
| 前端主控 | `app/src/valve_web/static/js/app.js` | 前端頁面切換、登入狀態、navigation、theme、DOM helper | Web 前端主流程壞掉 |
| API 封裝 | `app/src/valve_web/static/js/api.js` | 使用 `fetch()` 呼叫後端 API | Web 前端無法正常呼叫 API |
| 頁面模組 | `app/src/valve_web/static/js/pages/*.js` | 各功能頁畫面與互動 | 對應 Web 功能頁壞掉 |

頁面模組包含：

```text
decision.js
display.js
history.js
login.js
monitor.js
qc_products.js
qc_stats.js
qc_system.js
regions.js
settings.js
users.js
```

## Web GUI 後端檔案

| 類型 | 路徑 | 用途 | 刪除影響 |
| --- | --- | --- | --- |
| FastAPI app | `app/src/valve_web/server.py` | 建立 Web server，掛載 static，註冊 routers | Web server 無法啟動 |
| Web 狀態 | `app/src/valve_web/state.py` | Web 端共用狀態與 context | Web API 狀態管理壞掉 |
| Session | `app/src/valve_web/session.py` | Web 登入 session | Web 登入/登出壞掉 |
| 權限依賴 | `app/src/valve_web/deps.py` | FastAPI 權限檢查 | Web API 權限驗證壞掉 |
| Schema | `app/src/valve_web/schemas.py` | Web API request/response model | Web API 資料格式驗證壞掉 |
| 相機管理 | `app/src/valve_web/camera_manager.py` | Web 端相機背景擷取 | Web 相機串流/預覽壞掉 |
| 影像疊圖 | `app/src/valve_web/overlay.py` | Web 端 JPEG 編碼與區域疊圖 | Web 預覽疊圖壞掉 |
| API routes | `app/src/valve_web/routers/*.py` | Web API 功能 | 對應 API 全部失效 |

routers 包含：

```text
auth.py
config.py
history.py
inspect.py
qc.py
stream.py
users.py
```

## 其他相關線索

`app/src/requirements.txt` 內有 Web UI 依賴：

```text
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.9
```

註解提到 `web_main.py`，但目前專案內沒有找到 `web_main.py`。代表 Web 子系統存在，但目前啟動入口可能已缺失、曾被移除，或尚未補上。

`training/requirements.txt` 有 Django 依賴，但沒有看到 `manage.py`、`settings.py`、`urls.py` 等 Django 專案入口，因此不判定為本專案 Web GUI。

`.venv` 內第三方套件帶有 HTML/CSS/template 檔案，但那些是依賴套件內容，不列為本專案 Web GUI code。

## 不是 Web GUI、不可誤刪的項目

| 路徑 | 判斷 |
| --- | --- |
| `main.py` | 桌面 GUI 主入口，不是 Web GUI |
| `app/src/valve_gui/` | PyQt6 桌面 GUI 核心，不是 Web GUI |
| `app/src/valve_gui/styles.py` | PyQt QSS 樣式，不是 Web CSS |
| `app/src/valve_gui/pages/` | 桌面 GUI 頁面，不是 Web 頁面 |
| `icon/icon.png`、`icon/icon.ico` | exe/icon 資源，不應視為 Web GUI 刪除目標 |
| `screw_inspection.spec`、`build_exe.ps1` | PyInstaller 桌面打包設定，不是前端 build |

## 刪除影響分析

### 情境 A：只使用桌面 GUI

若正式運行方式只有：

```powershell
python main.py
```

且不需要瀏覽器 Web UI，則刪除 `app/src/valve_web/` 大概率不影響桌面主程式啟動。

理由：

- `main.py` 匯入的是 `valve_gui.main_window` 與 `valve_gui.styles`。
- 目前掃描沒有看到 `main.py` 或 `valve_gui` 直接匯入 `valve_web`。
- PyInstaller spec 以 `main.py` 為入口，沒有明確把 `valve_web/static` 當作必要資料加入。

風險：

- 若現場有人用 Web UI 遠端監控、設定、相機串流、歷史查詢、品管統計，刪除後這些功能會消失。
- 若之後要恢復 Web UI，需要從版本控制還原整包 `valve_web`。

### 情境 B：仍需要 Web UI

不可刪除 `app/src/valve_web/`。

刪除後會失效的 Web 功能包括：

- Web 登入/登出
- Web 權限控管
- Web 相機串流
- Web 單次檢測與連續檢測
- Web 設定相機、模型、ROI、顯示、theme
- Web 歷史紀錄查詢與匯出
- Web 品管統計、產品資料
- Web 使用者管理

### 情境 C：只刪 Web 前端 static

不建議。

若只刪：

```text
app/src/valve_web/static/
```

後端 API 仍可能存在，但瀏覽器畫面會壞，`server.py` 的 `/` 也找不到 `index.html`。

這會留下半套 Web 後端，維護上更容易混亂。

### 情境 D：只刪 Web 後端 routers

不建議。

前端仍存在，但 API 會失效，登入、相機串流、設定、檢測等功能都無法正常運作。

## 可刪與不可刪初步分類

| 分類 | 項目 | 建議 |
| --- | --- | --- |
| 可安全清理 | `app/src/valve_web/**/__pycache__/` | 可刪，屬 Python 快取，不是原始碼 |
| 可考慮刪除 | `app/src/valve_web/` | 僅在確認不需要 Web UI 後刪 |
| 可考慮移除依賴 | `fastapi`、`uvicorn[standard]`、`python-multipart` | 僅在刪除 Web UI 且確認無其他用途後移除 |
| 不建議單獨刪 | `app/src/valve_web/static/` | 會造成 Web 半殘 |
| 不建議單獨刪 | `app/src/valve_web/routers/` | 會造成 Web 半殘 |
| 不可刪 | `app/src/valve_gui/` | 桌面 GUI 核心 |
| 不可刪 | `main.py` | 桌面 GUI 主入口 |

## 建議刪除規劃

### Phase 0：確認需求

先確認產品方向：

1. 是否確定正式系統只保留 PyQt6 桌面 GUI？
2. 是否有任何人使用瀏覽器介面？
3. 是否需要遠端監控、Web 相機串流或 Web 品管統計？
4. 是否計畫未來恢復 Web UI？

若任一答案是「需要」，不建議刪除 `valve_web`。

### Phase 1：先做只讀驗證

刪除前建議再次檢查引用：

```powershell
rg -n "valve_web|create_app|FastAPI|uvicorn|/api/" .
```

預期結果：

- 只剩 `valve_web` 自己內部互相引用。
- `codex_thinking`、`codex_to_do` 文件內可能仍有歷史紀錄引用，這不影響程式運行。

### Phase 2：先清快取

可先清理：

```text
app/src/valve_web/**/__pycache__/
```

這不影響原始碼邏輯。

### Phase 3：若確認不要 Web UI，再刪整包

建議刪除範圍：

```text
app/src/valve_web/
```

不建議只刪前端或只刪後端，因為會留下半套不可用系統。

### Phase 4：同步整理依賴

確認刪除 `valve_web` 後，再評估是否從 `app/src/requirements.txt` 移除：

```text
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.9
```

移除前要確認沒有其他模組使用 FastAPI、uvicorn 或 multipart。

### Phase 5：驗證桌面 GUI

刪除後至少驗證：

```powershell
python main.py
```

需要檢查：

- 程式可啟動
- 登入頁正常
- 相機設定正常
- 檢測流程正常
- 歷史紀錄正常
- PyInstaller 打包流程正常

若有打包需求，再驗證：

```powershell
.\build_exe.ps1
```

## 最終建議

如果目前產品目標是「只保留桌面版檢測系統」，可以規劃刪除：

```text
app/src/valve_web/
```

並在驗證後移除 Web-only dependencies。

如果未來仍可能需要瀏覽器操作、遠端監控、相機串流、品管統計或 Web 設定頁，則不要刪除 `valve_web`，最多只清理 `__pycache__`。

目前最保守的判斷是：

```text
桌面 GUI 運行：刪除 valve_web 大概率不影響
Web GUI 運行：刪除 valve_web 會完全失效
```
