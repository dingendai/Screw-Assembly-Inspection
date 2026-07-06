# 基於影像識別技術之多緯度螺絲裝配檢測

## 專案簡介

本專案負責使用已訓練完成的 YOLO 模型，對產品四面影像進行推論、檢測與展示，判斷螺絲裝配狀態與相關元件是否正確安裝。

模型訓練、資料集整理、實驗管理、訓練成果整理與模型封存已獨立到 YOLO-TrainKit，本專案後續不再負責上述訓練流程。

本系統目標包含：

* 螺絲是否在位
* 螺絲是否鎖固到位
* 濾網是否存在
* 標籤是否存在（後續可擴充 OCR / 條碼辨識）

---

## 專案責任邊界

本專案負責：

* 載入正式推論模型
* 對輸入影像或影像串流執行推論
* 解析檢測結果（類別、信心分數、位置）
* 提供檢測流程、展示介面或 API
* 維護檢測類別、判定規格與展示文件

本專案不負責：

* 模型訓練
* 訓練資料集整理
* 標註資料轉換
* 實驗管理與訓練結果比較
* 訓練成果封存

---

## 專案結構

```text
screw_assembly_inspection/
├─ app/                # 主程式（推論 / 檢測 / UI / API）
├─ models/             # 正式推論模型權重（不納入版本控制）
├─ docs/               # 檢測規格、協作文件與展示文件
├─ training/           # 歷史訓練資料與成果；後續應移交 YOLO-TrainKit 管理
├─ .gitignore
└─ README.md
```

`training/` 目前保留既有資料，不在本次調整中刪除或移動；後續若要清理，應先確認資料已在 YOLO-TrainKit 或外部儲存完成交接。

---

## 模型來源

正式推論模型由 YOLO-TrainKit 負責訓練、驗證、整理與封存。

當模型確認可用後，將推論所需的正式權重檔放入：

```text
models/
```

本專案的推論流程應只從 `models/` 載入正式模型，不應依賴 `training/runs/` 中的實驗輸出。

---

## 開發環境

```text
Python 3.11
YOLOv8 (Ultralytics)
PyTorch (CUDA)
```

實際推論執行所需套件應以 `app/` 後續實作為準；訓練環境與訓練依賴由 YOLO-TrainKit 維護。

---

## 檢測類別（初版）

```text
screw_ok
screw_missing
screw_not_locked
filter_ok
filter_missing
label_ok
label_missing
```

類別與判定規格請見：

```text
docs/annotation_spec.md
```

該文件目前仍保留部分訓練標註規則，後續應遷移到 YOLO-TrainKit，或改寫為本專案使用的「檢測類別與判定規格」。

---

## 注意事項

以下內容不納入 Git 版本控制：

```text
- 模型權重（*.pt）
- dataset（影像與標註）
- training/runs（歷史訓練輸出）
```

---

## 開發狀態

目前專案責任已調整為：

* 推論流程
* 檢測結果解析
* UI / API / 展示
* 檢測規格文件維護

---

## 分工建議

```text
app/：推論、檢測、UI、API
models/：正式推論模型放置位置
docs/：檢測規格、協作文件、展示文件
YOLO-TrainKit：模型訓練、資料集、實驗管理、模型封存
```

---

## Git 協作規範

本專案採用簡化 Git Flow 進行多人協作開發。

詳細規範請參考：

```text
docs/git_workflow.md
```

Commit 規則（摘要）

```text
feat: 新功能
fix: 修 bug
docs: 文件
chore: 雜項（結構 / gitignore）
refactor: 重構（不改功能）
```

基本開發流程

```text
開分支 → 開發 → commit → PR → merge
```

---

## 未來擴充

* OCR / 條碼辨識
* 多模型融合（檢測 + 分類）
* 即時檢測系統（camera stream）
