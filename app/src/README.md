# 基於影像識別技術之多緯度螺絲裝配檢測 - GUI 子系統

本資料夾為「基於影像識別技術之多緯度螺絲裝配檢測」專題的 PyQt6 GUI 應用程式。

GUI 負責操作員登入、攝影機設定、即時影像預覽、YOLO 模型推論、檢測結果顯示、歷史紀錄與 CSV 匯出。整體專題、資料集、標註規則與 Git 協作規範請參考專案根目錄與 `docs/` 文件。

## 與專題文件的關係

```text
../../README.md                 # 整體專題說明、訓練環境、資料集與分工
../../docs/annotation_spec.md   # 螺絲、濾網、標籤的標註類別與標註規則
../../docs/git_workflow.md      # Git 分支、PR、commit 與協作規範
```

本 GUI 對應整體專題中的 `app/` 主程式部分，訓練與資料處理則由 `training/` 負責。

## 功能

- 操作員登入：輸入姓名並使用 Camera 5 拍攝操作員照片。
- 操作員登出：記錄登入與登出時間。
- 檢測攝影機設定：支援 Camera 1-4，自訂設備索引與啟用數量。
- 攝影機搜尋：可重新掃描新接上的攝影機。
- 四面影像檢測：Camera 1-4 可對應 `front / back / left / right` 四個檢測視角。
- 多模型設定：可依每台檢測攝影機指定不同 YOLO 模型。
- 模型自動搜尋：目前程式會搜尋 `modles/` 下的 YOLO 權重檔。
- 即時預覽：登入頁與設定頁可預覽攝影機畫面。
- 影像方向設定：支援水平鏡像、垂直翻轉，以及 0/90/180/270 度旋轉。
- 檢測模式：監控頁支援單次檢測與連續檢測。
- 檢測顯示：若已安裝 `ultralytics`，會顯示 YOLO 標註後的影像。
- 結果面板：顯示 PASS / NG / WAITING 狀態。
- 歷史紀錄：保留檢測紀錄與操作員登入紀錄。
- CSV 匯出：方便後續分析。
- 無攝影機測試：若沒有實體攝影機，仍可使用模擬影像測試 GUI 流程。

## 檢測目標與類別

本 GUI 使用的模型應與 `../../docs/annotation_spec.md` 的初版標註類別一致：

```text
screw_ok
screw_missing
screw_not_locked

filter_ok
filter_missing

label_ok
label_missing
```

初版目標為判斷：

- 螺絲是否存在
- 螺絲是否鎖固到位
- 濾網是否存在
- 標籤是否存在

OCR、條碼辨識、螺絲角度與更細分類屬於後續擴充項目。

## 操作流程

1. 啟動程式：Camera 5 操作員預覽與 Camera 1-4 檢測預覽啟動。
2. 操作員登入：輸入操作員姓名並拍攝操作員照片。
3. 攝影機設定：選擇設備索引、啟用數量、影像方向，以及各攝影機使用的模型。
4. 套用設定：設定會寫入 `inspection_data/app_config.json`。
5. 進入監控：可執行單次或連續檢測。
6. 查看歷史：檢視檢測紀錄與操作員登入紀錄。
7. 操作員登出：登出紀錄會寫入 `inspection_data/operator_sessions.csv`。

## 專案結構

```text
app/src/
├─ main.py                         # GUI 應用程式入口
├─ requirements.txt                # GUI 執行環境套件
├─ 0README.md                      # 本文件
├─ inspection_data/
│  ├─ app_config.json              # 攝影機與模型設定
│  ├─ operator_sessions.csv        # 操作員登入/登出紀錄
│  └─ operator_photos/             # 操作員照片
├─ modles/                         # 目前程式使用的模型搜尋資料夾
└─ valve_gui/
   ├─ camera.py                    # OpenCV 攝影機來源、模擬影像、攝影機搜尋
   ├─ inference_router.py          # 依攝影機分派模型並執行推論
   ├─ main_window.py               # 登入、設定、監控、歷史頁流程控制
   ├─ model_registry.py            # 搜尋模型權重檔
   ├─ config_store.py              # 儲存與讀取 camera/model 設定
   ├─ models.py                    # AppState 與資料類別
   ├─ paths.py                     # 共用路徑設定
   ├─ storage.py                   # CSV 儲存工具
   ├─ styles.py                    # Qt 樣式
   ├─ widgets.py                   # 共用 GUI 元件
   └─ pages/
      ├─ login.py                  # 操作員登入與 Camera 5 拍照
      ├─ settings.py               # 攝影機啟用、順序、預覽、模型指定
      ├─ monitor.py                # Camera 1-4 監控與檢測
      └─ history.py                # 檢測與操作員歷史紀錄
```

## 模型路徑注意事項

根目錄文件使用 `models/` 作為模型權重資料夾名稱，但目前 GUI 程式與已搬移資料使用 `modles/`。

為避免目前程式找不到既有模型，本文件暫時保留 `modles/` 的描述。後續若要統一命名，建議同步修改：

```text
app/src/modles/                  # 目前實際路徑
app/src/valve_gui/paths.py       # 共用路徑設定
app/src/valve_gui/model_registry.py
```

模型權重 `*.pt` 通常不建議納入 Git 版本控制；若是正式交付模型，請在團隊協作規範中明確註明保存方式。

## 推論流程

YOLO / multi-modal 推論入口位於：

```text
valve_gui/inference_router.py
```

程式會依 `AppState.inspection_cameras` 中的攝影機設定，把不同 Camera slot 的 frame 分派到對應模型。

若環境已安裝 `ultralytics`，會使用 YOLO 輸出繪製標註影像；若尚未安裝，GUI 會使用 placeholder annotation，讓畫面流程仍可測試。

## 安裝與執行

請在 `app/src` 目錄中執行：

```powershell
pip install -r requirements.txt
python main.py
```

建議 Python 版本以專案根目錄文件為準，目前為 Python 3.11。

## PyQt6 DLL 疑難排解

若 PyQt6 已安裝，但 Windows 顯示 `DLL load failed while importing QtCore`，可在目前 Python 環境中重新安裝 Qt wheels：

```powershell
python -m pip install --force-reinstall --no-cache-dir PyQt6 PyQt6-Qt6 PyQt6-sip
```

若問題發生在 Anaconda，建議建立乾淨環境：

```powershell
conda create -n screw-inspection-gui python=3.11
conda activate screw-inspection-gui
pip install -r requirements.txt
python main.py
```
