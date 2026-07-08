# ROI 二分類模型判斷鎖緊 / 分開方案

## 文件目的

本文件獨立整理「使用 ROI 二分類模型判斷鎖緊 / 分開狀態」的方案。

它和 `codex_thinking/0707_1_review.md` 的幾何規則法不同：本方案不是人工設定 gap threshold，而是收集 ROI 圖片後訓練模型，讓模型學會 `locked` 與 `separated` 的影像差異。

## 一句話結論

如果目標是正式穩定上線，我會優先選 ROI 二分類模型。

原因是使用者要判斷的是固定位置上的狀態差異：

```text
locked / separated
```

這比「偵測物件有沒有出現」更像分類問題。

## 核心概念

流程：

```text
固定 ROI
→ 裁切鎖緊位置
→ 將 ROI 圖片丟入分類模型
→ 輸出 locked / separated
→ separated 視為 NG
```

輸入：

```text
小張 ROI 圖片
```

輸出：

```text
locked
separated
confidence
```

## 為什麼不是直接用目前 YOLO？

目前三個實際模型 class names 是：

```text
Screw_baseline20260507/best.pt  -> screw
Label_baseline20260507/best.pt  -> label_ok
Filter_baseline20260507/best.pt -> filter_ok
```

也就是說目前螺絲模型只會偵測：

```text
screw
```

它不會直接判斷：

```text
locked
separated
screw_ok
screw_not_locked
```

使用者提供的兩張圖都有金屬件，差異不是「有沒有物件」，而是「相對位置是否貼合」。

因此分類模型比單純偵測框更合適。

## 類別設計

建議第一版類別：

```text
locked
separated
```

也可以用中文概念：

```text
鎖緊
分開
```

但模型 class name 建議用英文，避免後續程式、檔名與訓練工具編碼問題。

不建議第一版使用太多類別，例如：

```text
locked
slightly_separated
separated
tilted
unknown
```

第一版先做二分類，資料才容易穩。

## 資料集結構

建議建立：

```text
training/data/lock_state/
├─ locked/
│  ├─ locked_0001.jpg
│  ├─ locked_0002.jpg
│  └─ ...
└─ separated/
   ├─ separated_0001.jpg
   ├─ separated_0002.jpg
   └─ ...
```

每張圖片應該是裁切後的 ROI，不是整張相機畫面。

## 建議資料量

### 最小測試

```text
locked：50 張
separated：50 張
```

用途：

```text
確認模型是否學得起來
```

### 初版可用

```text
locked：100 到 200 張
separated：100 到 200 張
```

用途：

```text
初步接近現場測試
```

### 比較穩定

```text
locked：300 張以上
separated：300 張以上
```

用途：

```text
降低光線、反光、批次差異造成的誤判
```

## 資料收集要求

每一類都要包含：

1. 正常光線。
2. 稍亮。
3. 稍暗。
4. 輕微反光。
5. 不同產品批次。
6. 同一狀態下的微小位置差。
7. 焦距固定後的清晰影像。
8. 可接受範圍內的輕微模糊。

不要只從同一張圖複製或截圖，否則模型容易背背景。

## ROI 設計

ROI 應包含：

1. 金屬件本體。
2. 基準座面。
3. 鎖緊時貼合的位置。
4. 分開時出現縫隙的位置。

ROI 不應過小，否則模型看不到分離特徵。

ROI 也不應過大，否則背景干擾變多。

建議第一版 ROI：

```text
比目標零件大一圈
包含接觸面與可能分離縫
```

## 模型選擇

可用幾種方式：

### 1. YOLO classification

Ultralytics YOLO 支援分類任務。

優點：

1. 與目前 YOLO 生態接近。
2. 訓練流程相對簡單。
3. 可輸出分類 confidence。

缺點：

1. 需要另外建立 classification 訓練流程。
2. 目前系統 `InferenceRouter` 還沒有正式支援 classifier modality。

### 2. 輕量 CNN

例如 MobileNet、ResNet18。

優點：

1. 適合小圖分類。
2. 速度快。
3. 可控性高。

缺點：

1. 需要寫訓練與推論程式。
2. 和目前 YOLO 系統整合成本稍高。

### 3. OpenCV + 傳統 ML

例如 HOG + SVM。

優點：

1. 模型小。
2. 訓練快。

缺點：

1. 對光線與角度泛化較差。
2. 後續擴充不如深度學習模型。

## 建議模型

第一版建議：

```text
YOLO classification 或輕量 CNN 二分類
```

如果希望最貼近目前專案，選 YOLO classification。

如果希望更乾淨地做 ROI 小圖分類，選 MobileNet / ResNet18 類型。

## 訓練流程

### 步驟 1：收集 ROI 圖片

從固定相機畫面裁切該位置 ROI。

資料夾：

```text
locked/
separated/
```

### 步驟 2：切分資料集

建議：

```text
train：70%
val：20%
test：10%
```

如果資料少，至少保留 val。

### 步驟 3：訓練分類模型

輸出：

```text
best.pt
```

或其他分類模型格式。

### 步驟 4：驗證

驗證指標：

1. accuracy。
2. confusion matrix。
3. separated 漏判率。
4. locked 誤判率。

其中最重要的是：

```text
separated 不可漏判
```

因為分開卻判成鎖緊，會造成 NG 放行。

## 判定門檻

分類結果不應只看 top1。

建議：

```text
如果 separated confidence >= threshold → NG
如果 locked confidence >= threshold → PASS 條件之一
如果兩者都不夠高 → NG 或人工確認
```

第一版門檻可先用：

```text
0.7
```

現場測試後再調整。

## 接入目前系統的設計

目前 `ModelConfig` 有：

```python
modality: str = "vision"
```

而設定頁已有選項：

```python
MODEL_MODALITIES = ["vision", "text", "multimodal", "ocr", "classifier"]
```

但目前 `InferenceRouter` 主要只處理 YOLO 偵測，還沒有真正分類器流程。

後續整合可新增：

```text
modality = "classifier"
```

流程：

```text
相機 frame
→ 套用翻轉 / 旋轉
→ 依 camera ROI 裁切
→ classifier 推論
→ 產生 camera_result
→ 回到 PASS / NG 判定
```

## 與 ROI 設定頁的關係

可以沿用目前指定範圍監視的 ROI 概念。

但需要注意：

目前 ROI 主要是給 YOLO detection mask 使用。

分類器 ROI 可能需要新增用途欄位，例如：

```text
region_type = "classifier"
classifier_model_name = "lock_state"
```

第一版可先簡化：

```text
每台相機指定一個 lock_state ROI
```

不要一開始做太複雜。

## 優點

1. 比幾何規則更能適應輕微光線變化。
2. 比 YOLO 偵測更適合細微狀態差異。
3. 標註成本低，只要分類資料夾。
4. 適合固定位置的工業檢測。
5. 可以輸出 confidence。
6. 未來可擴充更多狀態。

## 缺點

1. 需要收集資料。
2. 需要訓練模型。
3. 需要接入分類器推論流程。
4. 如果資料太少會 overfit。
5. ROI 若偏移太大，分類結果會變差。

## 風險與對策

| 風險 | 影響 | 對策 |
| --- | --- | --- |
| 資料量太少 | 模型背答案 | 每類至少 100 張以上 |
| 光線反光 | 誤判 | 固定光源，加入反光樣本 |
| ROI 偏移 | 模型看不到關鍵位置 | ROI 放大一點，或先定位 |
| 類別界線不清 | 標註不一致 | 先定義 locked / separated 標準 |
| separated 漏判 | NG 放行 | 提高 separated 優先權與門檻 |

## 驗證標準

初版模型至少應達到：

```text
val accuracy >= 95%
separated recall >= 98%
```

現場測試至少：

```text
連續 100 次測試中，separated 不可漏判
```

若 separated 漏判，不能進正式放行流程。

## 建議下一步

1. 先用幾何方法確認 ROI 差異是否穩定。
2. 開始收集 ROI 圖片。
3. 建立 `training/data/lock_state/locked`。
4. 建立 `training/data/lock_state/separated`。
5. 每類先收 50 到 100 張。
6. 訓練第一版 ROI 二分類模型。
7. 離線測試 confusion matrix。
8. 通過後再規劃接入 `InferenceRouter`。

## 最終判斷

ROI 二分類模型是比較適合正式系統的方向。

它不像幾何法那麼依賴單一 threshold，也不像 YOLO 偵測那樣只關心框的位置。

它最適合這種問題：

```text
固定位置
固定 ROI
狀態差異細微
需要判斷 locked / separated
```

因此建議：

```text
幾何規則法：先做 MVP 驗證
ROI 二分類模型：作為正式導入方向
```
