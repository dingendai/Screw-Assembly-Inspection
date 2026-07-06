# Git 協作規範（3人專題版）

## 目標

* 保持主分支穩定可用
* 避免互相覆蓋程式
* 簡化流程，不增加負擔
* 聚焦推論、檢測與展示功能

---

## 分支策略

```text
main            # 穩定版本（可展示 / 可執行）
app/*           # 主程式（推論 / 檢測 / UI / API）
docs/*          # 文件與規格
chore/*         # 結構調整、設定、雜項維護
```

### 範例

```text
app/basic-inference
app/detection-ui
docs/detection-spec
chore/project-structure
```

模型訓練、dataset 整理與實驗管理不在本專案分支策略內，相關工作應在 YOLO-TrainKit 進行。

---

## 開發流程（標準）

每次開發請照這個流程：

```bash
# 1. 更新主線
git checkout main
git pull

# 2. 開新分支
git checkout -b app/xxx   # 或 docs/xxx、chore/xxx

# 3. 開發 + commit
git add .
git commit -m "feat: add xxx"

# 4. 推上 GitHub
git push origin app/xxx
```

---

## 合併流程（重要）

```text
一律透過 Pull Request（PR），不要直接 push main
```

流程：

1. 開 PR（branch → main）
2. 至少一人確認（review）
3. 確認沒衝突再 merge

---

## Commit 規範（簡單版）

```text
feat: 新功能
fix: 修 bug
docs: 文件
chore: 雜項（gitignore、結構）
refactor: 重構（不改功能）
```

### 範例

```text
feat: add image inference endpoint
fix: correct model path
docs: update detection spec
chore: update project structure
```

---

## 禁止事項

```text
不要直接 push main
不要上傳 dataset
不要上傳模型權重（*.pt）
不要將訓練實驗輸出納入 Git
不要覆蓋別人的檔案不討論
```

---

## Model 規則

```text
model 不走 Git
```

統一方式：

```text
由 YOLO-TrainKit 完成訓練、驗證、整理與封存
正式推論模型本地放在：
   models/
```

本專案只使用 `models/` 中的正式推論模型，不使用訓練實驗輸出作為模型載入來源。

---

## 分工建議

```text
A：app（推論 / 檢測）
B：app（UI / API / 展示）
C：docs / 檢測規格 / 測試
```

但：

```text
所有人都要能 pull + run
```

---

## 最重要原則

```text
main 永遠要能跑
```

也就是：

```text
不會 crash
至少能 demo
```

---

## 簡化版一句話流程

```text
開分支 → 做事 → commit → PR → merge
```
