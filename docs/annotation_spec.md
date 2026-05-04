# Annotation Specification

## 專題名稱

基於影像識別技術之多緯度螺絲裝配檢測

---

## 檢測目標

本專題使用 YOLOv8 進行多目標檢測，目標包含：

* 螺絲狀態判定
* 濾網存在判定
* 標籤存在判定

---

## 影像來源（四面）

每個樣本包含：

```text
front / back / left / right
```

---

## 類別定義（初版）

```text
screw_ok
screw_missing
screw_not_locked

filter_ok
filter_missing

label_ok
label_missing
```

---

## 標註原則（最重要）

### 1️.Bounding Box 規則

```text
框住整個物件（螺絲 / 濾網 / 標籤）
邊界貼齊，不包含過多背景
不要框半顆螺絲（除非遮擋）
```

---

### 2️.螺絲判定規則（核心）

#### screw_ok

```text
螺絲存在 + 已鎖緊
```

#### screw_missing

```text
螺絲完全不存在
```

#### screw_not_locked

```text
螺絲存在但未鎖緊（突出 / 歪斜）
```

---

### 3️.濾網判定

```text
filter_ok       → 存在
filter_missing  → 不存在
```

---

### 4️.標籤判定

```text
label_ok       → 存在
label_missing  → 不存在
```

初版不做 OCR / 條碼辨識

---

## 不確定情況處理

```text
無法判斷狀態 → 不標註
模糊影像 → 不納入訓練
```

---

## 命名規則（重要）

```text
front_0001.jpg
back_0001.jpg
left_0001.jpg
right_0001.jpg
```

---

## 標註一致性要求

```text
同一類物件 → 框法一致
同一狀態 → 判定一致
```

---

## 禁止事項

```text
 同一物件使用不同類別
 框過大 / 過小
 把背景當物件
```

---

##  未來擴充（暫不實作）

```text
OCR / 條碼辨識
螺絲角度 / 精細分類
```
