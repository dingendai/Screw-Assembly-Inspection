# Git 協作規範（3人專題版）

## 目標

* 保持主分支穩定可用
* 避免互相覆蓋程式
* 簡化流程，不增加負擔

---

## 分支策略

```text
main            # 穩定版本（可展示 / 可執行）
training/*      # 模型訓練相關
app/*           # 主程式（推論 / UI / API）
docs/*          # 文件與規格
```

### 範例

```text
training/init-env
training/dataset-setup
app/basic-inference
docs/annotation-spec
```

---

## 開發流程（標準）

每次開發請照這個流程：

```bash
# 1. 更新主線
git checkout main
git pull

# 2. 開新分支
git checkout -b training/xxx   # 或 app/xxx

# 3. 開發 + commit
git add .
git commit -m "feat: add xxx"

# 4. 推上 GitHub
git push origin training/xxx
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
feat: add YOLO training script
fix: correct dataset path
docs: update annotation spec
chore: add .gitkeep files
```

---

## 禁止事項（避免爆炸）

```text
不要直接 push main
不要上傳 dataset
不要上傳模型權重（*.pt）
不要覆蓋別人的檔案不討論
```

---

## Dataset & Model 規則

```text
dataset / model 不走 Git
```

統一方式：

```text
Google Drive / 雲端共享
本地放在：
   training/data/
   models/
```

---

## 分工建議

```text
A：training（資料處理 / YOLO）
B：app（推論 / UI / API）
C：docs / 標註 / 測試
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
