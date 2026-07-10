# NG / PASS 物件檔案紀錄流程現況整理

## 文件目的

本文件整理目前系統中「檢測結果為 PASS / NG 後，如何產生紀錄、寫入資料庫、寫入 CSV，以及保存每個受測物件影像快照」的實作流程。

本文件只描述現有程式行為，尚未提出修改方案。

## 相關主要檔案

| 類型 | 檔案 |
| --- | --- |
| 推論與 PASS / NG 判定 | `app/src/valve_gui/inference_router.py` |
| 桌面端監視頁檢測入口 | `app/src/valve_gui/pages/monitor.py` |
| 桌面端紀錄寫入入口 | `app/src/valve_gui/main_window.py` |
| Web 端檢測與紀錄入口 | `app/src/valve_web/routers/inspect.py` |
| SQLite 品管資料庫 | `app/src/valve_gui/qc_db.py` |
| CSV 與物件快照檔案儲存 | `app/src/valve_gui/storage.py` |
| 輸出路徑定義 | `app/src/valve_gui/paths.py` |
| 資料模型 | `app/src/valve_gui/models.py` |

## 輸出資料夾

所有品管紀錄預設寫在：

```text
app/src/inspection_data/
```

如果使用者在用戶管理設定了 `qc_output_dir`，則會改寫到指定資料夾。

主要輸出項目：

```text
inspection_data/
├── qc.db
├── inspection_records.csv
├── operator_sessions.csv
├── user_records/
└── qc_objects/
```

`paths.py` 透過 `RuntimePath` 動態解析目前使用的輸出資料夾，所以桌面端與 Web 端共用同一份資料位置。

## 判定結果來源

PASS / NG 由 `InferenceRouter.run()` 產生。

流程如下：

1. 收到目前啟用相機的 frame。
2. 逐台相機取得 assigned model。
3. 每個模型執行 YOLO 推論。
4. 取得：
   - 最高 confidence
   - 偵測框數量 object count
   - 偵測框座標與類別
   - annotated frame
5. 依照 `DecisionConfig.model_rules` 或全域門檻判斷模型是否 PASS。
6. 若任一模型不符合門檻，該相機加入 failed slots。
7. 若啟用 ROI 物件確認，會統計每個 ROI 是否有被偵測框命中。
8. 若啟用鎖緊幾何檢測，`separated` 或 `unknown` 會讓該相機 NG。
9. 最終結果：
   - 有 failed slot，或沒有任何 confidence，整體為 `NG`
   - 否則整體為 `PASS`

推論結果會包成 `InferenceResult`，主要欄位：

```text
result
confidence
note
annotated_frames
camera_results
roi_confirmations
barcode
barcode_sources
raw_frames
```

## 單次檢測流程

桌面端：

1. 使用者在監視頁按「單次檢測」。
2. `MonitorPage.inspect_once()` 收集 `last_frames`。
3. `_DetectionWorker` 呼叫 `InferenceRouter.run(frames)`。
4. `_on_single_detection_done()` 呼叫 `apply_detection_result(inference, record=True)`。
5. `apply_detection_result()` 更新畫面上的 PASS / NG、原因卡、ROI 確認狀態、annotated frame。
6. 因為 `record=True`，呼叫 `record_detection(inference)`。

Web 端：

1. API `POST /api/inspect` 進入 `_run_once(record=True, throttle=False)`。
2. 收集 camera frames。
3. 呼叫 `ctx.router.run(frames)`。
4. 產生 `InspectionRecord`。
5. 呼叫 `_add_record()` 寫入 CSV、SQLite 與物件快照。

## 連續檢測流程

桌面端：

1. 使用者啟用「連續檢測」。
2. `detection_timer` 每 500 ms 呼叫 `detect_current_frames()`。
3. 背景 executor 執行 `InferenceRouter.run(frames)`。
4. `apply_pending_detection_result()` 取得結果。
5. `apply_detection_result(inference, record=False)` 更新畫面。
6. 因為 `self.continuous_detection=True`，仍會呼叫 `record_detection(inference)`。

連續檢測節流規則：

```text
if inference.result != "NG" and now - last_record_time < 5.0:
    return
```

也就是：

- `PASS` 最多約 5 秒記一次。
- `NG` 不受 5 秒限制，每次偵測到 NG 都會嘗試記錄。

Web 端：

1. API `POST /api/inspect/continuous/start` 啟動背景 thread。
2. `_continuous_loop()` 每 0.5 秒呼叫 `_run_once(record=True, throttle=True)`。
3. `throttle=True` 時，非 NG 結果套用 5 秒節流。
4. NG 一樣不節流。

## InspectionRecord 內容

桌面端與 Web 端最後都會組成 `InspectionRecord`。

欄位如下：

```text
timestamp
operator_name
operator_role
result
part_id
active_cameras
confidence
note
barcode_source
```

其中 `part_id` 的來源優先序：

1. 推論中由標籤框解出的條碼。
2. 監視頁或 API 傳入的手動序號。
3. 自動產生 `PART-HHMMSS`。

`barcode_source` 用來標示序號來源：

| source | 來源 |
| --- | --- |
| YOLO 標籤類別名稱或模型名稱 | 推論框內解碼出的條碼 |
| `barcode` | 一般條碼解碼 |
| `manual` | 使用者手動輸入 |
| `auto` | 系統自動產生 |

## 桌面端寫入入口

桌面端紀錄由 `MainWindow.add_record()` 統一處理。

流程：

1. 先把 `InspectionRecord` 插入 `state.records`。
2. 建立輸出資料夾。
3. 寫入或更新 `inspection_records.csv`。
4. 若 result 是 `PASS` 或 `NG` 且 `part_id` 不空：
   - 寫入 SQLite `qc.db`
   - 保存 `qc_objects` 物件快照
5. 刷新歷史頁。

SQLite 與物件快照的寫入包在 `try/except` 中。

因此如果 SQLite 或影像快照保存失敗，檢測流程不會中斷；但錯誤目前會被吞掉，畫面不會明確提示。

## Web 端寫入入口

Web 端紀錄由 `valve_web/routers/inspect.py` 的 `_add_record()` 處理。

流程與桌面端一致：

1. 寫入 `state.records`。
2. 寫入或更新 `inspection_records.csv`。
3. 寫入 SQLite `qc.db`。
4. 保存 `qc_objects` 物件快照。

Web 端註解也明確寫出：

```text
SQLite 為品管查詢/統計的單一真相；CSV 暫時保留作過渡。
```

## SQLite 紀錄流程

SQLite 檔案：

```text
inspection_data/qc.db
```

資料表：

```text
products
work_sessions
inspections
```

`record_inspection()` 規則：

1. `barcode` 不可為空。
2. `result` 只能是 `PASS` 或 `NG`。
3. 若 products 沒有該 barcode，先自動建立品項。
4. 同一個 `barcode` 加同一天日期，只保留最後一次判定。
5. 若當天已有同 barcode 紀錄：
   - 更新既有 inspection
   - 刪除同 barcode 同日期的其他 inspection
6. 若沒有既有紀錄：
   - 新增一筆 inspection
7. 回傳 inspection id。

這代表 SQLite 不是保存同一條碼同一天的全部檢測歷程，而是保存該物件當天最新狀態。

## CSV 紀錄流程

主要 CSV：

```text
inspection_data/inspection_records.csv
```

由 `append_record_csv()` 寫入。

欄位：

```text
timestamp
operator_name
operator_role
result
part_id
active_cameras
confidence
note
```

CSV 寫入規則：

1. 先讀入既有 CSV。
2. 若本次 `part_id` 與日期存在，刪除同 `part_id` 同日期舊列。
3. 附加本次紀錄。
4. 整份 CSV 重寫。

因此 `inspection_records.csv` 也只保留同一物件同一天最後一次結果。

另外登出時會依操作者輸出一份使用者紀錄：

```text
inspection_data/user_records/<operator> <YYYYMMDDHHMM>.csv
```

這份資料來自記憶體中的 `state.records`，用途偏向該次工作時段的操作者紀錄。

## 物件快照 qc_objects 流程

物件快照由 `save_qc_object_snapshot()` 保存。

根目錄：

```text
inspection_data/qc_objects/
```

資料夾結構：

```text
qc_objects/
└── <operator_name>/
    └── <login_time>/
        └── <barcode_or_part_id>/
            ├── camera_<slot>_raw.jpg
            ├── camera_<slot>_annotated.jpg
            ├── result.json
            └── latest_result.csv
```

資料夾名稱會經過 `safe_path_part()` 清理，避免 Windows 不合法字元。

保存條件：

```text
barcode = record.part_id.strip()
if not barcode or record.barcode_source == "auto":
    return None
```

也就是：

- 條碼或手動序號存在才會保存物件快照。
- 自動產生的 `PART-HHMMSS` 不保存物件快照。
- 手動輸入的 part id 會保存，因為 source 是 `manual`。

保存前清理規則：

1. 先呼叫 `remove_previous_qc_object_snapshots()`。
2. 在整個 `qc_objects` 裡找同 barcode 且同日期的舊資料夾。
3. 除了本次要保留的資料夾外，其餘同 barcode 同日期資料夾會刪除。
4. 進入本次 object folder 後，先刪除舊的 `camera_*_*.jpg`。
5. 再寫入本次 raw / annotated jpg。

因此物件快照同樣只保留同一物件同一天最後一次結果。

## result.json 內容

每個物件資料夾會有：

```text
result.json
```

內容包含：

```text
inspection_id
updated_at
timestamp
operator_name
operator_role
login_time
barcode
result
source
active_cameras
confidence
note
camera_results
roi_confirmations
files.raw
files.annotated
```

用途：

- 保存該物件最新 PASS / NG 結果。
- 保存每台相機的判定原因。
- 保存 ROI 確認投票結果。
- 連結 raw / annotated 圖檔名稱。
- 連結 SQLite inspection id。

## latest_result.csv 內容

每個物件資料夾也會有：

```text
latest_result.csv
```

欄位：

```text
timestamp
barcode
result
operator_name
operator_role
confidence
note
```

這是一份簡化版最新結果，方便不用解析 JSON 時快速查看。

## 歷史與統計查詢

目前歷史頁與品管統計頁主要讀 SQLite。

相關函式：

```text
qc_db.get_history()
qc_db.get_stats()
qc_db.get_ng_ranking()
qc_db.get_session_inspections()
qc_db.get_orphan_inspections()
```

統計頁可依：

- 條碼
- 日期區間
- PASS / NG

查詢並匯出 CSV。

NG 排行使用 SQLite 中的 `inspections` 表計算。

## 工作時段關聯

登入時：

1. 建立 `work_sessions` 紀錄。
2. 回傳 `current_work_session_id`。

檢測紀錄寫入 SQLite 時會帶入：

```text
session_id = current_work_session_id
```

登出時：

1. 更新 `work_sessions.logout_time`。
2. 寫入 `operator_sessions.csv`。
3. 輸出本次操作者的 `user_records` CSV。

因此 SQLite 可依工作時段查詢檢測紀錄。

## 目前流程特性

### 1. SQLite 是單一真相

程式註解明確表示：

```text
SQLite 為歷史/品管查詢/統計的單一真相；CSV 暫時保留作過渡。
```

歷史頁、統計頁、NG 排行主要都讀 SQLite。

### 2. 同一物件同一天只保留最後一次結果

此規則同時存在於：

- SQLite `record_inspection()`
- CSV `append_record_csv()`
- 物件快照 `remove_previous_qc_object_snapshots()`

因此如果同一條碼今天先 NG 後 PASS，最後資料會顯示 PASS。

如果先 PASS 後 NG，最後資料會顯示 NG。

### 3. NG 在連續檢測中不節流

連續檢測時，非 NG 約 5 秒才記一次。

NG 每次都嘗試記錄，但因同 barcode 同日期只保留最後一次，所以資料庫與物件快照最終仍是該物件最後狀態。

### 4. 自動序號不保存物件快照

如果沒有條碼也沒有手動輸入，系統會產生 `PART-HHMMSS`。

這筆仍會寫入 `inspection_records.csv` 與 SQLite，但不會保存 `qc_objects` 影像快照。

原因是 `save_qc_object_snapshot()` 直接排除 `barcode_source == "auto"`。

### 5. SQLite / 快照寫入失敗不會阻斷檢測

桌面端與 Web 端對 SQLite 和快照保存都有 `try/except`。

好處是檢測不中斷。

風險是如果資料庫或影像保存失敗，操作員可能不知道。

## 現況流程總圖

```text
相機 frame
  ↓
InferenceRouter.run()
  ↓
InferenceResult
  ├── result: PASS / NG
  ├── confidence
  ├── camera_results
  ├── roi_confirmations
  ├── raw_frames
  └── annotated_frames
  ↓
MonitorPage.record_detection()
或 Web _record_from()
  ↓
InspectionRecord
  ↓
MainWindow.add_record()
或 Web _add_record()
  ↓
├── state.records
├── inspection_records.csv
├── qc.db
│   ├── products
│   ├── inspections
│   └── work_sessions
└── qc_objects/<operator>/<login_time>/<barcode>/
    ├── camera_*_raw.jpg
    ├── camera_*_annotated.jpg
    ├── result.json
    └── latest_result.csv
```

## 需要注意的問題點

1. 同一物件同一天只保留最後一次結果，不保留完整重測歷程。
2. NG 連續檢測不節流，若沒有 barcode 或手動序號，可能產生多筆不同 `PART-HHMMSS` SQLite 紀錄，但沒有物件影像快照。
3. SQLite 或物件快照失敗會被忽略，缺少錯誤提示與錯誤 log。
4. `inspection_records.csv` 是整檔讀寫，資料量大時效率會下降。
5. `qc_objects` 會刪除同 barcode 同日期舊資料夾，所以不能用它追溯該物件早期 NG / PASS 變化。
6. 目前 CSV 欄位沒有保存 `barcode_source`，只有 SQLite 與 `result.json` 有 source 資訊。

## 結論

目前 NG / PASS 物件紀錄流程是：

1. 推論產生 `InferenceResult`。
2. 桌面端或 Web 端轉成 `InspectionRecord`。
3. 同步寫入過渡用 CSV。
4. 寫入 SQLite 作為歷史與統計的主要資料來源。
5. 若序號不是自動產生，保存該物件的 raw / annotated 圖、`result.json` 與 `latest_result.csv`。
6. 同一物件同一天在 CSV、SQLite、物件快照三個層級都只保留最後一次判定。

