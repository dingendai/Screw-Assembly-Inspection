# 影像辨識讀取條碼 — 環境與配置參考

> 本檔只描述「用影像辨識（電腦視覺）即時讀取條碼」這一項功能所需的環境、套件與配置。
> 其餘整合細節另行討論。

---

## 1. 功能說明

用鏡頭擷取影像 → 對每一幀做影像辨識 → 解出畫面中的條碼文字與位置。
**不需要專用硬體掃描槍**，靠一般攝影機 + 軟體解碼即可。

核心兩步：

```
攝影機影像 (BGR frame)
   → 轉灰階 (OpenCV)
   → 條碼解碼 (zxing-cpp) → [(文字, 格式, 校驗是否通過, 四角座標), ...]
```

對應現有程式碼（`realtime_qc.py`）：

```python
import cv2
import zxingcpp

def decode_frame(frame):
    """輸入 BGR 影像，回傳本幀解到的條碼清單 [(text, format, valid, position), ...]"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    out = []
    for r in zxingcpp.read_barcodes(gray):
        if r.text:
            out.append((r.text, str(r.format), r.valid, r.position))
    return out
```

---

## 2. 軟體環境需求

### 2.1 執行環境

| 項目 | 需求 | 說明 |
|------|------|------|
| 作業系統 | Windows / macOS / Linux 皆可 | 本專案開發於 Windows 11 |
| Python | **3.10 以上** | 程式用到 `str \| None` 型別語法 |
| 架構 | x86-64 / ARM64 | zxing-cpp 有提供對應 wheel |

### 2.2 必要套件

| 套件 | 版本 | 用途 | 重點注意 |
|------|------|------|----------|
| `opencv-python` | 任意近版 | 鏡頭擷取、影像處理、（本機）視窗顯示 | 本機要顯示畫面請用 **GUI 版**，**不要** `opencv-python-headless`；若是純後端/伺服器無畫面，才用 headless |
| `zxing-cpp` | **3.0.0**（已驗證） | 條碼解碼核心引擎 | 即 ZXing 的 C++ 版 Python 綁定，C++ 實作、速度快 |
| `numpy` | 任意近版 | 影像陣列 | OpenCV 相依，通常自動裝上 |

安裝：

```bash
pip install opencv-python zxing-cpp numpy
```

> headless 取捨：
> - **要在本機開視窗看畫面** → `opencv-python`（含 `imshow`）。
> - **跑在無顯示的伺服器、只回傳辨識結果** → 可改 `opencv-python-headless`，省掉 GUI 相依。

---

## 3. 硬體 / 攝影機需求

| 項目 | 建議 | 說明 |
|------|------|------|
| 攝影機 | 一般 USB Webcam / 筆電內建鏡頭 / IP Cam | 任何 OpenCV 能開的來源皆可 |
| 解析度 | **建議 1280×720 以上** | 條碼稍遠就會糊掉解不到；解析度足夠才穩 |
| 對焦 | 自動對焦或定焦對準工作距離 | 條碼模糊是解不到的第一大主因 |
| 光源 | 均勻、避免反光/眩光 | 反光會讓條碼線條糊成一片 |

程式中設定解析度（`run_camera`）：

```python
cap = cv2.VideoCapture(cam_index)          # cam_index：0=預設鏡頭，1,2...=其他
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
```

> 攝影機若不支援指定解析度，OpenCV 會自動退回最接近的值。

---

## 4. 解碼引擎配置（zxing-cpp）

`zxingcpp.read_barcodes()` **預設已開啟**以下強化，多數情況直接用即可：

| 預設選項 | 作用 |
|----------|------|
| `try_rotate` | 條碼歪斜 / 旋轉也能讀 |
| `try_downscale` | 縮小再試，幫助讀到較大或較遠的碼 |
| `try_invert` | 黑白反相（深底白條）也能讀 |

可辨識常見一維 / 二維碼（EAN-13、Code128、QR Code 等，依 zxing-cpp 支援清單）。

每筆解碼結果可取得：

| 欄位 | 內容 |
|------|------|
| `.text` | 條碼內容字串 |
| `.format` | 條碼格式（如 `EAN13`、`QRCode`） |
| `.valid` | 校驗碼是否通過（例：EAN-13 檢查碼）；可用來過濾掃錯的髒碼 |
| `.position` | 四角座標物件（`top_left` / `top_right` / `bottom_right` / `bottom_left`），可用來在畫面框出條碼 |

> `.valid` 很重要：辨識時可能讀到印壞、反光或半遮的「髒碼」，`valid=False` 代表校驗沒過，建議當作不可信、不要採用。

---

## 5. 效能與調校建議

- **逐幀解碼有成本**：每一幀都跑一次 `read_barcodes` 會吃 CPU。若 FPS 不足，可考慮**隔幀解碼**（例如每 2~3 幀解一次）或縮小送進解碼的影像尺寸。
- **灰階即可**：解碼用灰階影像就夠，不需彩色，已可省一些運算。
- **解析度 vs 速度**：解析度越高越容易解到較遠的碼，但每幀運算越重，需依機器權衡。
- **純 CPU、不需 GPU**：zxing-cpp 是 CPU 解碼，不依賴顯示卡，一般筆電即可即時運作。

---

## 6. 快速驗證環境是否就緒

裝完套件後，用一張含條碼的圖測試解碼（不需鏡頭）：

```python
import cv2, zxingcpp
img = cv2.imread("test_product.png")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
for r in zxingcpp.read_barcodes(gray):
    print(r.text, r.format, r.valid)
```

能印出條碼內容，代表**影像辨識讀取條碼**的環境已正確配置。

---

## 7. 最小相依清單（requirements）

```
opencv-python      # 本機要顯示畫面用 GUI 版；純後端無畫面可改 opencv-python-headless
zxing-cpp          # 條碼解碼引擎（驗證於 3.0.0）
numpy              # 影像陣列（OpenCV 相依）
```
