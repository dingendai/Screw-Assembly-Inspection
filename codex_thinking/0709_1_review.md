# 掃碼倒數檢測流程動工方案

## 文件目的

本文件根據：

- `codex_thinking/0708_1_review.md`：現有 NG / PASS 紀錄架構整理
- `codex_thinking/step.md`：新的掃碼、倒數、拍照、辨識、結果 review 想法

整理接下來動工前需要注意的範圍與做法。

本文件只討論怎麼做，不修改程式。

## 0708_1_review.md 復盤結果

對照目前程式後，`0708_1_review.md` 的主體描述大致正確。

確認正確的部分：

1. PASS / NG 由 `InferenceRouter.run()` 產生，結果包成 `InferenceResult`。
2. 桌面端單次檢測流程是 `MonitorPage.inspect_once()` 收 frame，背景 worker 呼叫 router，完成後 `apply_detection_result(..., record=True)`。
3. 桌面端連續檢測每 500 ms 嘗試推論，非 NG 結果有 5 秒寫入節流，NG 不節流。
4. Web 端 `POST /api/inspect` 走 `_run_once(record=True, throttle=False)`，連續檢測走 `_continuous_loop()`。
5. 桌面端與 Web 端最後都會建立 `InspectionRecord`，再寫入 CSV、SQLite、qc_objects。
6. SQLite `record_inspection()` 以 `barcode + 日期` 保留最後一次結果。
7. CSV `append_record_csv()` 以 `part_id + 日期` 刪除舊列後重寫整份 CSV。
8. qc_objects 會刪除同 barcode 同日期的舊資料夾，只保留最新物件快照。
9. `barcode_source == "auto"` 時不保存 qc_objects 快照。
10. SQLite 與 qc_objects 寫入失敗目前被 `try/except` 吞掉，不會阻斷檢測，也不會明確提示操作員。

需要補充或特別小心的部分：

1. 目前預設輸出資料夾在 source mode 是 `app/src/inspection_data/`，但打包成 exe 時會改成 exe 旁邊的 `inspection_data/`。
2. `qc_output_dir` 已經透過 `RuntimePath` 動態切換，桌面與 Web 會共用路徑邏輯。
3. 目前 CSV 主紀錄沒有 `barcode_source` 欄位；SQLite 有 `source`，`result.json` 有 `source`。
4. 目前系統還沒有完整的「掃 1~2 個標籤後倒數」交易流程。
5. 目前桌面端是從 live preview 的 `last_frames` 直接取 frame 推論；Web 端是從 camera manager 取目前 frame。尚未有明確的「倒數結束當下固定快照交易」。
6. 目前條碼主要是取第一個有效 barcode 作為 `part_id`；還沒有主條碼、副條碼的結構化保存。
7. 目前照片保存策略不是獨立設定；程式是最後保存 qc_objects raw / annotated image，且 auto source 不保存。

## step.md 的新流程應該怎麼做

新的流程應整理成一條固定交易：

```text
等待掃碼
  -> 掃碼完成
  -> 倒數
  -> 倒數結束拍照
  -> 用固定照片做 YOLO
  -> 做螺絲邊緣 / 幾何檢測
  -> 合併 PASS / NG
  -> 結果 Review
  -> 依設定保存紀錄與照片
  -> 等待下一件
```

核心原則：

1. 掃碼是一次檢測交易的起點。
2. 倒數結束當下要固定每台相機的照片。
3. YOLO 和後續螺絲檢測都必須使用同一組固定照片，不要中途再抓 live frame。
4. 最終 PASS / NG 出來後，才決定哪些資料正式保存。
5. 結果畫面要讓使用者 review 哪個物件、哪台相機、哪個條件不合格。

## 動工前要先決定的規則

### 1. 條碼規則

必須先決定 1~2 個標籤的資料結構。

建議：

- 主條碼：作為 `part_id` / SQLite barcode / qc_objects folder key。
- 副條碼：作為附屬欄位保存，不要拿來當主要覆蓋 key。
- 條碼來源要全鏈路保存：scan、yolo_label、manual、auto。
- 如果沒有條碼，是否允許進入檢測要先決定；若仍允許 auto `PART-HHMMSS`，要注意 NG 連續檢測可能污染統計。

### 2. 倒數啟動規則

`step.md` 提到兩種方案：

1. 掃描最後一組條碼後自動倒數。
2. 掃描完成後按確認，才開始倒數。

建議把它做成設定值。這個設定只決定何時開始拍照，不應影響後面的推論、判定、保存流程。

### 3. 拍照與 RAM 緩存規則

拍照後應建立一個本次檢測交易物件，至少包含：

```text
transaction_id
operator
session_id
primary_barcode
secondary_barcode
barcode_source
active_cameras
captured_at
raw_frames
annotated_frames
final_result
save_policy
```

RAM 緩存要綁定 `transaction_id`，不能只依賴「目前畫面」或「最新 frame」。

新品進來時：

- 前一件若已保存，清掉 RAM frame。
- 前一件若依設定不保存，也要清掉 RAM frame。
- 若前一件尚未完成保存，不應允許直接覆蓋。

### 4. 照片保存策略

建議把保存策略明確定義成四種：

```text
只保存 NG
只保存 PASS
NG / PASS 都保存
NG / PASS 都不保存
```

保存判斷應在最終結果出來後做：

```text
if result 符合保存策略 and barcode_source != "auto":
    保存 qc_objects raw / annotated / result.json / latest_result.csv
else:
    不保存物件快照，只保留必要紀錄
```

如果未來要讓 auto source 也保存快照，必須明確改規格，因為現有架構是排除 auto。

### 5. 最後結果覆蓋規則

現有架構是同一物件同一天只保留最後一次結果。

動工前要確認是否維持這個規則：

- 維持：SQLite、CSV、qc_objects 繼續覆蓋最新結果。
- 不維持：要改資料庫 schema、CSV 規則、qc_objects 資料夾命名與歷史頁查詢。

建議第一版先維持現有規則，避免牽動歷史頁、統計頁、NG ranking。

## 建議動工範圍

### 第一階段：先做交易狀態與資料模型

目標是讓流程有固定狀態，不要讓 UI、推論、保存各自猜目前是哪一件。

可能動到：

- `app/src/valve_gui/models.py`
- `app/src/valve_gui/pages/monitor.py`
- Web 若也要同步，會動到 `app/src/valve_web/routers/inspect.py`

先新增或整理概念：

```text
InspectionTransaction
BarcodeInfo
PhotoSavePolicy
InspectionStepState
```

不一定要一開始就做成很大的抽象，但資料一定要能表示：

- 這一件物件是誰
- 掃到幾個條碼
- 目前走到哪個狀態
- 照片存在 RAM 還是已落地
- 最終結果是否已保存

### 第二階段：做掃碼與倒數狀態機

目標是把操作流程固定住。

UI 狀態建議：

```text
等待掃碼
掃碼完成
倒數中
拍照中
辨識中
結果 Review
等待下一件
錯誤
```

需要注意：

1. 掃碼未完成前不能倒數。
2. 倒數中不能重複開始檢測。
3. 倒數中要允許取消。
4. 相機未就緒時要中止倒數並提示。
5. 拍照完成後要凍結縮圖，後續推論都用這組照片。

### 第三階段：推論使用固定快照

現有 `InferenceRouter.run(frames_by_slot)` 已經可以吃指定 frames。

因此第一版不需要大改 router，重點是呼叫端要改成：

```text
倒數結束
  -> capture active camera frames
  -> copy into transaction.raw_frames
  -> router.run(transaction.raw_frames)
```

不要讓 YOLO 或螺絲檢測重新抓 live frame。

螺絲邊緣 / 幾何檢測目前已在 `InferenceRouter.run()` 內處理 `lock_geometry_enabled`，但如果新想法的「螺絲邊緣監測」不是同一套邏輯，就要先確認是延伸現有 lock geometry，還是新增另一個判定模組。

### 第四階段：結果 Review 畫面

結果畫面應該是使用者看的最終重點。

需要顯示：

- PASS / NG
- 主條碼 / 副條碼
- 操作員與時間
- 每台相機結果
- YOLO confidence、object count、ROI 命中狀態
- 螺絲邊緣 / 幾何檢測結果
- NG 原因
- raw / annotated 圖
- 紀錄保存狀態

建議按鈕：

```text
下一件
重測此物件
重拍
查看原圖 / 標註圖
```

如果同一物件同一天維持只保留最後結果，按重測此物件前要提示：本次結果會覆蓋今天此條碼的最新紀錄。

### 第五階段：保存策略接入現有紀錄流程

保存仍建議集中在最後一步。

現有可沿用：

- `MainWindow.add_record()`
- Web `_add_record()`
- `append_record_csv()`
- `qc_db.record_inspection()`
- `save_qc_object_snapshot()`

但需要補強：

1. 把照片保存策略傳進保存流程。
2. 只有符合策略時才保存 qc_objects。
3. CSV 若要追蹤來源，應新增 `barcode_source` 欄位或另存一份 metadata。
4. SQLite 寫入成功後，把 `inspection_id` 放入 `result.json`。
5. SQLite / CSV / qc_objects 任一保存失敗，都應回傳保存狀態給結果畫面。

## 最需要注意的風險

1. 不要讓「倒數結束拍到的照片」和「YOLO 實際辨識的照片」不是同一張。
2. 不要讓下一件產品進來時覆蓋上一件尚未完成的 RAM frame。
3. 不要讓 1~2 個條碼在 SQLite、CSV、qc_objects 使用不同 key。
4. 不要在還沒定義保存策略前就直接改 `save_qc_object_snapshot()`，否則會影響現有品管紀錄。
5. 不要讓 auto `PART-HHMMSS` 在連續 NG 中大量產生有效統計紀錄，這會污染 NG ranking。
6. 不要只在背景吞掉 SQLite 或快照錯誤；至少結果畫面要能看到保存失敗。
7. 不要一次改歷史頁、統計頁、匯出與檢測流程。第一版應盡量維持現有 latest-only 規則。
8. 桌面端和 Web 端目前有各自入口，若新流程兩邊都要支援，要避免兩邊寫出不同保存規則。

## 建議驗證案例

第一版動工完成後，至少驗證：

1. 只掃 1 個條碼。
2. 掃 2 個條碼。
3. 重複掃描與重新掃描。
4. 條碼含 Windows 不合法路徑字元。
5. 自動倒數。
6. 確認後倒數。
7. 倒數取消。
8. 相機未就緒時倒數中止。
9. 只存 NG。
10. 只存 PASS。
11. NG / PASS 都存。
12. NG / PASS 都不存。
13. NG 後 PASS，同 barcode 同日期最後結果是 PASS。
14. PASS 後 NG，同 barcode 同日期最後結果是 NG。
15. SQLite 寫入失敗。
16. CSV 被鎖定或無法寫入。
17. qc_objects 無權限或磁碟滿。
18. 新品進來後，上一件不需保存的 RAM frame 已清除。

## 結論

接下來不要先從改保存檔案開始。

建議先從「檢測交易狀態」動工，因為你的新想法本質上是把目前直接檢測流程，改成一個受控的交易流程：

```text
掃碼鎖定物件
  -> 倒數鎖定時機
  -> 拍照鎖定影像
  -> 推論鎖定判定
  -> Review 鎖定結果
  -> 保存鎖定紀錄
```

只要這條交易線先定清楚，後面照片保存策略、結果畫面、SQLite/CSV/qc_objects 一致性才不會互相打架。
