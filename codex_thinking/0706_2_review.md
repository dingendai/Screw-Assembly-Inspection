# 相機焦距功能整合到系統相機設定頁規劃

## 文件目的

本文件延續 `codex_thinking/0706_1_review.md`，將 `0.py` 小規模 MVP 測試中的相機焦距控制能力，規劃成可整合到目前正式系統的功能方向。

本文件不是實作清單；它的用途是先明確定義功能邊界、資料結構、UI 呈現、相機啟動流程、驗證方法與分階段導入策略。

若本方向確認，後續再依 `Collaboration_Standards` 建立：

```text
codex_to_do/0706_2_list1.md
codex_to_do/0706_2_list2.md
```

## 一句話方向

將 `0.py` 的手動焦距控制整合到「相機設定」頁，讓每台檢測相機可以選擇：

1. **原廠自動焦距 / 自動對焦模式**
   - 程式不主動控制焦距。
   - 不呼叫 `cv2.CAP_PROP_AUTOFOCUS`。
   - 不呼叫 `cv2.CAP_PROP_FOCUS`。
   - 完全交給相機、驅動或設備本身的自動對焦機制。

2. **手動固定焦距模式**
   - 程式在相機啟動後關閉自動對焦。
   - 程式套用使用者設定的固定焦距值。
   - 每次進入監視、預覽、Web 串流時都依設定重新套用。

## 名詞釐清

使用者描述中提到「變焦」，但 `0.py` 實際測試的是 OpenCV 的 `CAP_PROP_FOCUS`，也就是相機焦距 / 對焦控制，而不是光學變焦或數位變焦。

因此本次規劃先以「焦距 / 對焦」為準。

若未來設備真的需要控制 zoom，應另開功能，使用不同欄位，例如：

```text
zoom_mode
manual_zoom_value
cv2.CAP_PROP_ZOOM
```

不要把 focus 和 zoom 混在同一個設定中，避免現場調機時誤解。

## 功能目標

### 使用者目標

在相機設定頁中，每一台檢測相機都能設定焦距控制方式：

1. 使用原廠自動焦距。
2. 使用手動固定焦距值。
3. 在預覽畫面確認設定是否有套用。
4. 儲存後，下次進入監視頁或重啟系統仍保留設定。

### 系統目標

1. 每台 Camera slot 有獨立焦距設定。
2. 焦距設定與既有相機設定一起存在 `app_config.json`。
3. 桌面 GUI 與 Web UI 使用同一份設定。
4. 模擬相機模式不套用焦距設定。
5. 原廠自動模式不對相機做任何焦距控制。
6. 手動固定模式只在實體相機成功開啟後套用。
7. 套用失敗時不讓整個系統崩潰，只顯示狀態或警告。

## 非目標

第一版不做以下內容：

1. 不做全自動最佳焦距搜尋。
2. 不做 Laplacian 清晰度評分。
3. 不做 ROI 自動校正。
4. 不做不同相機型號的焦距範圍自動偵測。
5. 不做焦距變更操作紀錄。
6. 不做正式校正報表。
7. 不控制真正的 zoom。

理由：

目前 `0.py` 只是 MVP 測試。第一階段應先把「使用者可手動設定模式與焦距值，系統可穩定套用」做穩，不要一次導入自動校正與評分。

## 建議功能名稱

建議 UI 使用：

```text
焦距模式
```

兩個選項：

```text
原廠自動焦距
手動固定焦距
```

若現場人員習慣稱為「變焦」，可以在 label 寫成：

```text
焦距模式（對焦 / 變焦）
```

但程式欄位建議仍使用 `focus`，不要使用 `zoom`。

## 建議資料結構

目前 `CameraConfig` 位於：

```text
app/src/valve_gui/models.py
```

建議在 `CameraConfig` 新增欄位：

```python
focus_mode: str = "auto"
manual_focus_value: int = 120
```

欄位說明：

| 欄位 | 型別 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `focus_mode` | `str` | `"auto"` | `"auto"` 表示原廠自動；`"manual"` 表示手動固定 |
| `manual_focus_value` | `int` | `120` | 手動固定焦距值，建議範圍 0 到 255 |

為什麼預設 `"auto"`：

1. 不影響既有使用者。
2. 不會在升級後突然關閉自動對焦。
3. 不會對不支援手動焦距的相機造成額外風險。
4. 舊設定檔沒有欄位時可自然回到原本行為。

## 設定檔相容性

目前設定由：

```text
app/src/valve_gui/config_store.py
```

負責讀寫。

讀取舊版 `app_config.json` 時，如果沒有焦距欄位，應使用：

```python
focus_mode = "auto"
manual_focus_value = 120
```

建議新增正規化函式：

```python
def normalise_focus_mode(value):
    return value if value in {"auto", "manual"} else "auto"

def normalise_focus_value(value):
    try:
        return max(0, min(255, int(value)))
    except (TypeError, ValueError):
        return 120
```

這樣可以避免設定檔被手動改壞時造成錯誤。

## 相機控制邏輯

目前實體相機由：

```text
app/src/valve_gui/camera.py
```

中的 `VideoSource` 開啟。

建議在 `VideoSource` 增加焦距參數：

```python
class VideoSource:
    def __init__(
        self,
        label: str,
        index: int,
        simulate: bool,
        focus_mode: str = "auto",
        manual_focus_value: int = 120,
    ):
        ...
```

並在相機成功開啟後套用：

```python
if not simulate and self.capture and self.capture.isOpened():
    self.apply_focus_settings(focus_mode, manual_focus_value)
```

建議新增方法：

```python
def apply_focus_settings(self, focus_mode: str, manual_focus_value: int):
    if focus_mode != "manual":
        return
    self.capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    self.capture.set(cv2.CAP_PROP_FOCUS, manual_focus_value)
```

重要原則：

1. `focus_mode == "auto"` 時，不做任何事情。
2. `focus_mode == "manual"` 時，才關閉自動對焦並設定焦距。
3. 套用失敗只記錄狀態，不中斷相機啟動。
4. 模擬相機不套用焦距。

## 是否需要在原廠自動模式呼叫 `CAP_PROP_AUTOFOCUS = 1`

不建議。

使用者已明確希望「原廠自動變焦選項，程式中就不需要控制他，因為設備本身就是自動變焦的設備」。

因此原廠自動模式應該是：

```text
程式完全不控制焦距
```

而不是：

```text
程式幫忙打開 auto focus
```

原因：

1. 有些驅動的 `CAP_PROP_AUTOFOCUS` 行為不穩定。
2. 有些設備自動對焦由韌體或原廠工具管理，OpenCV 強行設定可能干擾。
3. 保持不控制最符合使用者需求。

## UI 規劃：桌面 GUI 相機設定頁

目前桌面相機設定頁位於：

```text
app/src/valve_gui/pages/settings.py
```

每台相機目前已有：

1. 啟用。
2. 相機 index。
3. 左右翻轉。
4. 上下翻轉。
5. 旋轉。
6. 條碼辨識。
7. 指定模型。

建議新增：

1. 焦距模式 `QComboBox`
2. 手動焦距值 `QSpinBox`

UI 建議：

```text
焦距模式：[原廠自動焦距 / 手動固定焦距]
固定焦距：[ 0 - 255 ]
```

互動規則：

1. 選擇「原廠自動焦距」時，固定焦距欄位 disabled。
2. 選擇「手動固定焦距」時，固定焦距欄位 enabled。
3. 改變模式或焦距值時，預覽可重新啟動，讓設定生效。
4. 按「儲存 / 套用設定」後寫入 `app_config.json`。

第一版不一定要做「即時滑桿連續調整」，避免相機頻繁重啟或驅動不穩。

建議第一版採用：

```text
改值 → 儲存 / 套用設定 → 預覽或監視重新開相機後生效
```

## UI 規劃：Web 相機設定頁

Web 相機設定頁位於：

```text
app/src/valve_web/static/js/pages/settings.js
```

後端 config API 位於：

```text
app/src/valve_web/routers/config.py
app/src/valve_web/schemas.py
```

如果桌面 GUI 要支援這個功能，Web 也建議同步支援，因為兩者共用同一份 `app_config.json`。

Web 相機表格建議新增欄位：

```text
焦距模式
固定焦距
```

行為與桌面一致：

1. `auto` 時不控制相機。
2. `manual` 時由後端相機 worker 套用固定焦距。
3. 儲存後呼叫 `/api/config/cameras`，後端重啟相機 worker。

## 需要修改的模組

若進入實作，預計修改以下檔案。

### 1. 資料模型

```text
app/src/valve_gui/models.py
```

修改：

- `CameraConfig` 新增 `focus_mode`
- `CameraConfig` 新增 `manual_focus_value`

### 2. 設定讀寫

```text
app/src/valve_gui/config_store.py
```

修改：

- `load_app_config()` 讀取焦距欄位。
- `save_app_config()` 可透過 `asdict()` 自然保存。
- 新增正規化 helper。

### 3. 相機底層

```text
app/src/valve_gui/camera.py
```

修改：

- `VideoSource` 接收焦距設定。
- 實體相機開啟成功後套用手動固定焦距。
- 記錄焦距套用狀態，供 UI 顯示或 debug。

### 4. 桌面設定頁

```text
app/src/valve_gui/pages/settings.py
```

修改：

- 每台相機新增焦距模式與焦距值控制。
- `refresh()` 載入設定。
- `current_enabled_camera_rows()` 帶出焦距設定給預覽。
- `apply()` 寫回 state。
- 預覽建立 `VideoSource` 時帶入焦距設定。

### 5. 桌面監視頁

```text
app/src/valve_gui/pages/monitor.py
```

修改：

- 建立 `VideoSource` 時帶入該 camera config 的焦距設定。

### 6. ROI 設定頁

```text
app/src/valve_gui/pages/regions.py
```

修改：

- `CameraRegionEditor.start()` 建立 `VideoSource` 時帶入焦距設定。

### 7. Web schema

```text
app/src/valve_web/schemas.py
```

修改：

- `CameraModel` 新增 `focus_mode`
- `CameraModel` 新增 `manual_focus_value`

### 8. Web config router

```text
app/src/valve_web/routers/config.py
```

修改：

- `_apply_cameras()` 建立 `CameraConfig` 時寫入焦距欄位。

### 9. Web camera manager

```text
app/src/valve_web/camera_manager.py
```

修改：

- `_SlotWorker` 接收焦距設定。
- 建立 `VideoSource` 時帶入焦距設定。
- `CameraManager.restart()` 從 camera config 傳入焦距設定。

### 10. Web settings page

```text
app/src/valve_web/static/js/pages/settings.js
```

修改：

- 相機設定表格新增焦距模式與固定焦距欄位。
- `buildCameraRow().read()` 回傳焦距設定。

## 建議欄位命名

建議使用：

```text
focus_mode
manual_focus_value
```

不要使用：

```text
zoom_mode
manual_zoom_value
```

原因：

1. `0.py` 使用的是 `CAP_PROP_FOCUS`。
2. OpenCV 中 focus 與 zoom 是不同相機屬性。
3. 未來如果真的要控制 zoom，保留獨立擴充空間。

## 建議設定檔格式

更新後的 `inspection_cameras` 範例：

```json
{
  "slot": 1,
  "device_index": 0,
  "enabled": true,
  "flip_horizontal": false,
  "flip_vertical": false,
  "rotation_degrees": 0,
  "assigned_model_name": "best",
  "assigned_model_names": ["best"],
  "region_detection_enabled": false,
  "detection_regions": [],
  "exclusion_regions": [],
  "barcode_read_enabled": false,
  "focus_mode": "manual",
  "manual_focus_value": 120
}
```

原廠自動模式範例：

```json
{
  "focus_mode": "auto",
  "manual_focus_value": 120
}
```

即使 auto 模式保留 `manual_focus_value`，也沒關係，因為 auto 時不使用該值。這樣使用者切回 manual 時可以保留上次設定。

## 相機啟動流程

### 手動固定焦距

流程：

1. 開啟 `cv2.VideoCapture`。
2. 確認 `capture.isOpened()`。
3. 呼叫 `capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)`。
4. 呼叫 `capture.set(cv2.CAP_PROP_FOCUS, manual_focus_value)`。
5. 讀取回傳值與 `capture.get(cv2.CAP_PROP_FOCUS)`。
6. 相機開始讀 frame。

### 原廠自動焦距

流程：

1. 開啟 `cv2.VideoCapture`。
2. 確認 `capture.isOpened()`。
3. 不呼叫任何 focus / autofocus 設定。
4. 相機開始讀 frame。

這是本功能最重要的行為差異。

## 焦距套用狀態

建議 `VideoSource` 增加狀態欄位：

```python
self.focus_status = ""
```

手動模式套用後可記錄：

```text
manual focus requested=120 set_auto=True set_focus=True readback=120.0
```

若失敗：

```text
manual focus requested=120 set_auto=False set_focus=False readback=-1
```

第一版可以只記錄在物件內，必要時顯示在相機狀態列。不要因焦距失敗中斷整個監視流程。

## 權限規劃

焦距設定屬於相機設定的一部分。

第一版建議沿用既有權限：

```text
PERMISSION_OPEN_SETTINGS
```

也就是目前能進入相機設定的人，就能設定焦距。

暫時不新增權限：

```text
manage_focus
```

理由：

1. 降低第一版改動範圍。
2. 焦距與相機 index、旋轉、模型指定同屬設備設定。
3. 後續若現場需要細分權限，再新增即可。

## 桌面與 Web 是否同步做

建議同步做。

原因：

1. 桌面與 Web 共用 `AppState` 與 `app_config.json`。
2. 若只做桌面，Web 儲存相機設定時可能覆蓋焦距欄位。
3. 若只做 Web，桌面設定頁無法顯示焦距欄位，也可能覆蓋設定。

因此只要新增 `CameraConfig` 欄位，就應同步讓桌面與 Web 的相機設定流程保留並寫回該欄位。

## 分階段實作建議

### 階段 1：資料結構與設定保存

目標：

讓系統能讀寫每台相機的焦距設定，但還不一定真的控制相機。

工作內容：

1. `CameraConfig` 新增 `focus_mode`。
2. `CameraConfig` 新增 `manual_focus_value`。
3. `load_app_config()` 支援舊設定檔 fallback。
4. `save_app_config()` 能保存新欄位。
5. Web schema 與 config router 同步支援新欄位。

驗證：

1. 啟動程式不因舊 `app_config.json` 缺欄位而錯。
2. 改設定後重新啟動，焦距設定仍存在。
3. 桌面與 Web 都不會把焦距設定洗掉。

### 階段 2：桌面相機設定頁 UI

目標：

使用者可以在桌面「相機設定」頁設定焦距模式與固定焦距值。

工作內容：

1. SettingsPage 每台相機新增 `QComboBox`。
2. SettingsPage 每台相機新增 `QSpinBox`。
3. auto 模式 disabled spinbox。
4. manual 模式 enabled spinbox。
5. `apply()` 寫回 state。

驗證：

1. 開啟相機設定頁能看到焦距模式。
2. 切換 auto/manual 時欄位狀態正確。
3. 按「儲存 / 套用設定」後寫入設定檔。
4. 重啟後設定仍存在。

### 階段 3：相機啟動時套用手動焦距

目標：

正式相機讀取流程依設定套用焦距。

工作內容：

1. `VideoSource` 接收焦距設定。
2. manual 模式套用 `CAP_PROP_AUTOFOCUS = 0` 與 `CAP_PROP_FOCUS`。
3. auto 模式完全不控制 focus。
4. MonitorPage 建立 VideoSource 時傳入設定。
5. Settings preview 建立 VideoSource 時傳入設定。
6. Region editor 建立 VideoSource 時傳入設定。
7. Web CameraManager 建立 VideoSource 時傳入設定。

驗證：

1. manual 模式下，畫面焦距有依設定變化。
2. auto 模式下，程式不呼叫 focus 控制。
3. 模擬相機模式不報錯。
4. 相機不支援手動焦距時，監視流程仍可運作。

### 階段 4：Web 相機設定頁 UI

目標：

Web UI 也能設定焦距模式與固定焦距值。

工作內容：

1. Web settings table 新增焦距模式欄位。
2. Web settings table 新增固定焦距值欄位。
3. 儲存時送出 `focus_mode` 與 `manual_focus_value`。
4. 後端重啟 camera worker 後套用新設定。

驗證：

1. Web 儲存後設定檔保留欄位。
2. 桌面再開啟時能看到 Web 儲存的設定。
3. 桌面儲存後 Web 也能看到相同設定。

### 階段 5：焦距狀態顯示與調機輔助

這是第二輪功能，不建議放第一版。

可做內容：

1. 顯示焦距套用結果。
2. 顯示回讀焦距值。
3. 加入「測試套用」按鈕。
4. 加入清晰度分數。
5. 加入最佳焦距建議。

## 建議第一版 MVP 範圍

第一版建議只做：

1. CameraConfig 新增焦距欄位。
2. app_config 可讀寫。
3. 桌面相機設定頁可設定。
4. Web 相機設定頁可保留與設定。
5. `VideoSource` 手動模式套用焦距。
6. 原廠自動模式完全不控制焦距。

第一版不做：

1. 清晰度評分。
2. 自動找最佳焦距。
3. ROI 校正。
4. 焦距範圍自動偵測。
5. 焦距操作紀錄。

## 驗證計畫

### 單元層級檢查

可用 Python 匯入檢查：

```powershell
python -m compileall app/src
```

目標：

1. 新增欄位不造成語法錯誤。
2. schema 與設定讀寫可正常載入。

### 設定檔相容性檢查

流程：

1. 使用沒有焦距欄位的舊 `app_config.json`。
2. 啟動系統。
3. 儲存相機設定。
4. 確認新設定檔出現 `focus_mode` 與 `manual_focus_value`。

預期：

```text
focus_mode = "auto"
manual_focus_value = 120
```

### 桌面 GUI 驗證

流程：

1. 啟動 `python main.py`。
2. 登入開發者或管理者。
3. 進入相機設定。
4. 將 Camera 1 設成手動固定焦距。
5. 設定不同焦距值。
6. 儲存 / 套用設定。
7. 進入監視頁確認畫面。
8. 切回原廠自動焦距，確認程式不再控制焦距。

### Web UI 驗證

流程：

1. 啟動 FastAPI Web UI。
2. 登入。
3. 進入相機設定。
4. 修改焦距設定。
5. 儲存。
6. 重新整理頁面確認設定存在。
7. 回桌面 GUI 確認設定同步。

### 實機焦距驗證

流程：

1. 固定相機與測試物距離。
2. 固定光源。
3. 手動模式測試焦距 0、60、120、180、240。
4. 觀察畫面是否變化。
5. 切回原廠自動模式，觀察設備是否恢復自身自動對焦行為。

判定：

1. 若 manual 有效，功能可保留。
2. 若 manual 無效，但 auto 正常，現場可使用原廠自動模式。
3. 若 manual 導致設備不穩，預設仍用 auto，並在文件中註明該相機不建議手動控制。

## 風險與對策

| 風險 | 影響 | 對策 |
| --- | --- | --- |
| 相機不支援 `CAP_PROP_FOCUS` | 手動模式無效 | 保留原廠自動模式，manual 失敗不阻斷監視 |
| 原廠自動模式被程式干擾 | 自動對焦失效 | auto 模式完全不呼叫 focus/autofocus |
| Web 或桌面覆蓋新欄位 | 設定遺失 | 桌面與 Web 同步修改 schema 與 read/write |
| 手動焦距值範圍不適用所有相機 | 部分設備無效 | 第一版固定 0-255，後續再做設備範圍設定 |
| 預覽頻繁重啟相機 | 相機被占用或卡住 | 第一版用儲存/套用後生效，不做即時滑桿 |
| 模擬模式呼叫焦距控制 | 無意義或錯誤 | simulate=True 時直接略過 |

## 建議不要改的地方

第一版不應改：

1. `inference_router.py`
2. `qc_db.py`
3. 歷史紀錄頁
4. 品管統計頁
5. YOLO 後處理
6. 條碼解碼邏輯

原因：

焦距設定只影響相機取像，不應混入推論、資料庫或歷史紀錄邏輯。

## Git commit 建議

若分階段 commit，建議：

```text
feat: 新增相機焦距設定欄位
feat: 在相機設定頁加入焦距模式控制
feat: 相機啟動時套用手動固定焦距
```

若要保持第一版一個 commit，也可以：

```text
feat: 新增相機手動固定焦距設定
```

## 建議下一步

若此方向確認，下一步應建立工作清單：

```text
codex_to_do/0706_2_list1.md
```

建議清單內容先聚焦第一版 MVP：

1. 新增 `CameraConfig.focus_mode`。
2. 新增 `CameraConfig.manual_focus_value`。
3. 更新 `config_store.py`。
4. 更新桌面 SettingsPage。
5. 更新 Web schema 與 settings page。
6. 更新 `VideoSource` 與所有建立 VideoSource 的地方。
7. 執行 compile 檢查。
8. 實機測試 auto/manual 兩種模式。

## 最終建議

本功能可以整合進系統，但應以「每台相機的焦距模式設定」方式導入，而不是把 `0.py` 直接搬進主程式。

最佳整合方向是：

```text
CameraConfig 增加 focus 設定
→ 相機設定頁提供 auto/manual 選項
→ auto 模式不控制設備
→ manual 模式開相機後套用固定 focus value
→ 桌面與 Web 共用同一份 app_config.json
```

這樣可以保留原廠自動對焦設備的原本行為，也能讓需要固定焦距的檢測站使用手動參數，符合目前系統架構且風險最小。
