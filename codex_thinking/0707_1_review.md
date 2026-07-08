# 幾何規則法判斷鎖緊 / 分開方案

## 文件目的

本文件獨立整理「使用幾何方法計算鎖緊 / 分開狀態」的方案。

目標是先不訓練新模型，而是利用固定相機、固定 ROI、邊緣位置、縫隙距離與暗區比例，判斷零件是否鎖緊。

## 一句話結論

如果相機、光源、治具與產品位置都穩定，幾何規則法可以作為最快的 MVP。

核心判斷是：

```text
鎖緊：零件貼近基準面，縫隙小
分開：零件與基準面距離變大，縫隙或暗區明顯
```

## 適用條件

幾何方法適合以下情況：

1. 相機位置固定。
2. 產品放置位置固定。
3. 光源穩定。
4. 鎖緊位置固定。
5. ROI 可以固定。
6. 鎖緊與分開在像素位置上有穩定差異。

如果以上條件不穩，幾何規則會變得脆弱。

## 不適用情況

以下情況不建議只靠幾何規則：

1. 產品位置每次偏移很大。
2. 光線反光不固定。
3. 分開距離很小，接近相機解析度極限。
4. 鎖緊與分開的影像差異不穩定。
5. 需要適應多種產品外觀。
6. 相機角度會變。

## 判斷特徵

### 1. 間隙距離

找出：

```text
基準面位置
金屬件邊緣位置
```

計算兩者距離：

```text
gap_px = abs(metal_edge_y - base_line_y)
```

判斷：

```text
gap_px <= threshold → locked
gap_px > threshold  → separated
```

### 2. 黑色縫隙比例

在固定縫隙區域內計算暗色像素比例：

```text
dark_ratio = dark_pixels / total_pixels
```

判斷：

```text
dark_ratio <= threshold → locked
dark_ratio > threshold  → separated
```

### 3. 金屬件輪廓位置

透過二值化或邊緣偵測找出金屬件輪廓。

可量測：

1. 金屬件下緣 y 座標。
2. 金屬件左 / 右邊緣 x 座標。
3. 金屬件中心點位置。
4. 金屬件與座面重疊比例。

### 4. 與正常樣板差異

以鎖緊狀態作為 template，計算目前 ROI 與正常樣板差異。

可能方法：

```text
absdiff
template matching
SSIM
edge difference
```

第一版不建議太複雜，先用 gap 或 dark_ratio。

## 建議 MVP 流程

### 步驟 1：固定 ROI

先人工或透過現有 ROI 設定，框出該鎖緊位置。

ROI 應包含：

1. 金屬件。
2. 基準座面。
3. 鎖緊時會貼合的位置。
4. 分開時會出現縫隙的位置。

ROI 不應包含太多背景。

### 步驟 2：收集測試圖片

先收集：

```text
locked：20 張
separated：20 張
```

要求：

1. 同一相機。
2. 同一光源。
3. 同一產品位置。
4. 同一 ROI。
5. 包含少量正常反光變化。

### 步驟 3：計算幾何指標

對每張 ROI 計算：

```text
gap_px
dark_ratio
metal_center_y
metal_bottom_y
```

第一版建議先挑最穩定的一個指標。

### 步驟 4：找 threshold

把 locked 和 separated 的數值列出。

理想情況：

```text
locked gap_px:    0, 1, 2, 2, 3
separated gap_px: 9, 11, 13, 15
```

此時可設：

```text
threshold = 6
```

如果兩組重疊：

```text
locked gap_px:    3, 5, 7
separated gap_px: 6, 7, 8
```

表示單純 gap 不穩，需換特徵或改用分類模型。

### 步驟 5：輸出 locked / separated

判斷結果：

```text
locked → PASS 條件之一
separated → NG
```

## 可能程式流程

```python
def classify_lock_state_by_geometry(frame, roi, threshold_px):
    crop = crop_roi(frame, roi)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    base_line_y = find_base_line(edges)
    metal_edge_y = find_metal_edge(edges)
    gap_px = abs(metal_edge_y - base_line_y)

    if gap_px <= threshold_px:
        return "locked", gap_px
    return "separated", gap_px
```

實際實作時，`find_base_line()` 與 `find_metal_edge()` 要依照 ROI 影像特徵調整。

## 更簡單的暗縫版本

如果分開時一定會出現黑色縫隙，可先用暗區比例：

```python
def classify_lock_state_by_dark_gap(frame, gap_roi, threshold_ratio):
    crop = crop_roi(frame, gap_roi)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    dark = gray < 70
    dark_ratio = dark.sum() / dark.size

    if dark_ratio > threshold_ratio:
        return "separated", dark_ratio
    return "locked", dark_ratio
```

這個方法很快，但對光線敏感。

## 優點

1. 不需要訓練資料。
2. 開發速度快。
3. 結果可解釋。
4. 適合先做 MVP。
5. 可以快速確認影像差異是否足夠。

## 缺點

1. 對光線敏感。
2. 對產品位置偏移敏感。
3. 對相機角度敏感。
4. 需要人工調 threshold。
5. 如果零件反光強，可能誤判。
6. 對不同批次或不同外觀泛化能力差。

## 導入目前系統的方式

第一版建議不要直接大改 `InferenceRouter`。

可以先做獨立測試工具：

```text
tools/lock_state_geometry_test.py
```

或先在 `codex_to_do` 開工作清單後再決定檔案位置。

測試工具輸入：

```text
ROI 圖片資料夾
threshold
```

輸出：

```text
每張圖片 gap_px / dark_ratio / 判定結果
```

等幾何指標穩定後，再接進正式監視頁。

## 驗證標準

幾何方法可行的標準：

1. locked 與 separated 的指標分布明顯分開。
2. 使用固定 threshold，可在測試資料達到 95% 以上正確率。
3. 換幾組現場光線後仍可接受。
4. 同一狀態重複拍攝時結果穩定。

如果正確率不到 90%，不建議直接導入正式 PASS / NG。

## 建議資料記錄格式

```text
filename,state,gap_px,dark_ratio,prediction,correct
locked_0001.jpg,locked,2,0.12,locked,true
separated_0001.jpg,separated,13,0.42,separated,true
```

這樣方便後續判斷 threshold 是否合理。

## 風險與對策

| 風險 | 影響 | 對策 |
| --- | --- | --- |
| 光線變化 | dark_ratio 漂移 | 固定光源，改用邊緣距離 |
| 產品位置偏移 | gap 計算錯 | 加定位基準，或先做 ROI 對齊 |
| 金屬反光 | 二值化錯誤 | 使用邊緣、形態學、固定曝光 |
| threshold 不穩 | 誤判 | 收集更多樣本後再定 threshold |
| ROI 太小 | 特徵不足 | 包含金屬件與基準面 |

## 建議下一步

1. 從實際監視畫面裁切該鎖緊位置 ROI。
2. 收集 locked / separated 各 20 張。
3. 寫一個離線幾何測試腳本。
4. 輸出 gap_px 與 dark_ratio。
5. 看兩組數值是否分得開。
6. 若分得開，再建立正式工作清單。
7. 若分不開，改走 ROI 二分類模型方案。

## 最終判斷

幾何規則法適合先驗證可行性。

它的價值是：

```text
快、可解釋、資料需求低
```

但它的限制也很明確：

```text
現場條件一變，規則可能失效
```

因此建議把幾何方法當作第一階段 MVP，不要直接當作最終正式方案。
