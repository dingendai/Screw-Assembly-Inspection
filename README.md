# 基於影像識別技術之多緯度螺絲裝配檢測

## 專案簡介

本專題透過影像識別技術（YOLOv8），對產品四面影像進行檢測，判斷螺絲裝配狀態與相關元件是否正確安裝。

本系統目標包含：

* 螺絲是否在位
* 螺絲是否鎖固到位
* 濾網是否存在
* 標籤是否存在（後續可擴充 OCR / 條碼辨識）

---

## 專案結構

```text
screw_assembly_inspection/
├─ main.py             # GUI 應用程式入口
├─ app/                # 主程式（推論 / UI / API）
├─ training/           # 資料處理與模型訓練
│  ├─ data/
│  ├─ scripts/
│  ├─ runs/
│  └─ requirements.txt
├─ models/             # 模型權重（不納入版本控制）
├─ docs/               # 規格與文件（標註規則 / dataset / 訓練計畫）
├─ .gitignore
└─ README.md
```

GUI 執行：

```powershell
pip install -r app/src/requirements.txt
python main.py
```

---

## 開發環境

```text
Python 3.11
YOLOv8 (Ultralytics)
PyTorch (CUDA)
```

---

## 安裝與執行（Training）

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r training/requirements.txt
```

測試 YOLO：

```bash
yolo predict model=yolov8n.pt source=bus.jpg
```

---

## 資料集規範

* 原始資料：`training/data/raw/`
* 標註資料：`training/data/labeled/`
* 訓練格式（YOLO）：`training/data/yolo_dataset/`

影像來源為四面：

* front
* back
* left
* right

---

## 標註類別（初版）

```text
screw_ok
screw_missing
screw_not_locked
filter_ok
filter_missing
label_ok
label_missing
```

詳細標註規則請見：

```text
docs/annotation_spec.md
```

---

## 注意事項

以下內容不納入 Git 版本控制：

```text
- dataset（影像與標註）
- 模型權重（*.pt）
- training/runs（訓練輸出）
```

---

## 開發狀態

目前進行中：

* 專案架構建立
* 環境建置（GPU / YOLO）
* 標註規則設計（進行中）

---

## 分工建議

```text
training/：模型訓練與資料處理
app/：推論與主程式
docs/：規格與文件
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

##  未來擴充

* OCR / 條碼辨識
* 多模型融合（檢測 + 分類）
* 即時檢測系統（camera stream）
