# LGM_Web 專案規則

## Git Commit 規範

所有 commit 必須遵守以下 Conventional Commits 格式：

**格式：** `<type>: <描述>`

| 類型 | 用途 | 範例 |
| --- | --- | --- |
| `feat` | 新功能 | `feat: 新增YOLOv8螺絲偵測功能` |
| `fix` | 修 bug | `fix: 修正螺絲位置匹配漏判問題` |
| `docs` | 文件更新 | `docs: 更新螺絲檢測功能使用說明` |
| `chore` | 雜項（結構/gitignore） | `chore: 更新資料集與模型輸出忽略規則` |
| `refactor` | 重構（不改功能） | `refactor: 重構螺絲偵測後處理模組` |

### 規則

1. **每次 commit 必須帶上正確的 type 前綴**
2. **描述使用中文**，簡潔說明這次變更做了什麼
3. **一個 commit 只做一件事**，不要混合多種變更類型
4. 破壞性變動在 type 後加 `!`，例如 `feat!: 重寫 API 回傳格式`

## 版本號規則

格式：`v主版本.次版本.修正版本`

| Commit Type | 版號動作 |
|-------------|---------|
| `feat` | 次版本 +1（Minor） |
| `fix` | 修正版本 +1（Patch） |
| 含 `BREAKING CHANGE` 或 `!` | 主版本 +1（Major） |
| `docs` / `chore` / `refactor` | 不升版 |
