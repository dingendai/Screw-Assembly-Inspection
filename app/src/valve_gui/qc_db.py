"""品管條碼資料庫 — SQLite 資料存取層。

對應「品管條碼資料庫系統_規劃文件.md」第 4、7 節。這是整個系統唯一直接碰
資料庫的地方：辨識/記錄端與後台查詢都透過本模組的函式存取。

設計重點：
- 條碼視為當天受測的唯一物件；同一條碼同一天只保留最後一次判定。
- result 值域沿用本專案既有的 ``PASS`` / ``NG``（非文件示意的 OK/NG），
  以免與既有 YOLO 引擎與前端文案不一致。
- 用內建 ``sqlite3``，啟用外鍵與 WAL（同機多進程讀寫）。
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from valve_gui.paths import QC_DB_PATH

_VALID_RESULTS = ("PASS", "NG")
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    barcode    TEXT PRIMARY KEY,
    name       TEXT,
    spec       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 工作時段：操作者一次登入(開始工作)→登出(結束工作)。
CREATE TABLE IF NOT EXISTS work_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operator      TEXT,
    operator_role TEXT,
    login_time    TEXT NOT NULL,
    logout_time   TEXT
);

CREATE TABLE IF NOT EXISTS inspections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode       TEXT NOT NULL,
    result        TEXT NOT NULL CHECK (result IN ('PASS','NG')),
    inspected_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    note          TEXT,
    operator      TEXT,
    operator_role TEXT,
    confidence    TEXT,
    active_cameras TEXT,
    session_id    INTEGER,
    source        TEXT,
    FOREIGN KEY (barcode) REFERENCES products(barcode),
    FOREIGN KEY (session_id) REFERENCES work_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_insp_barcode ON inspections(barcode);
CREATE INDEX IF NOT EXISTS idx_insp_time    ON inspections(inspected_at);
"""


def _connect() -> sqlite3.Connection:
    QC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(QC_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def _session():
    """開一條連線：``with conn`` 提交/回滾交易，finally 確保關閉（sqlite3 的
    connection context manager 只提交不關閉，直接用會洩漏連線）。"""
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """建立資料表與索引（若不存在）。程式啟動時呼叫一次。

    同時做輕量遷移：舊版 qc.db 的 inspections 表可能缺少後來新增的欄位，
    用 ALTER TABLE 補上，確保歷史頁查得到完整欄位。
    """
    with _lock, _session() as conn:
        conn.executescript(_SCHEMA)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(inspections)")}
        for column in ("operator", "operator_role", "confidence", "active_cameras"):
            if column not in existing:
                conn.execute(f"ALTER TABLE inspections ADD COLUMN {column} TEXT")
        if "session_id" not in existing:
            conn.execute("ALTER TABLE inspections ADD COLUMN session_id INTEGER")
        if "source" not in existing:
            conn.execute("ALTER TABLE inspections ADD COLUMN source TEXT")
        # session_id 欄位確定存在後才建索引（舊表遷移時欄位是上面才補的）。
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insp_session ON inspections(session_id)")


def get_or_create_product(barcode: str, name: str | None = None, spec: str | None = None) -> None:
    """品項不存在則建檔；存在則略過（可選擇補上 name/spec，不覆蓋既有非空值）。"""
    barcode = (barcode or "").strip()
    if not barcode:
        return
    with _lock, _session() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO products (barcode, name, spec) VALUES (?, ?, ?)",
            (barcode, name, spec),
        )


def record_inspection(
    barcode: str,
    result: str,
    note: str | None = None,
    *,
    operator: str | None = None,
    operator_role: str | None = None,
    confidence: str | None = None,
    active_cameras: str | None = None,
    inspected_at: str | None = None,
    session_id: int | None = None,
    source: str | None = None,
) -> int:
    """寫入或更新一筆檢驗記錄，回傳流水號 id。

    result 僅接受 'PASS' / 'NG'；會先確保品項已建檔。
    session_id 關聯到當前工作時段（work_sessions）；source 記錄序號來源
    （標籤類別名稱 / manual / auto）。同一 barcode + 日期只保留最後一次判定。
    """
    barcode = (barcode or "").strip()
    if not barcode:
        raise ValueError("barcode 不可為空")
    if result not in _VALID_RESULTS:
        raise ValueError(f"result 必須是 {_VALID_RESULTS}，收到 {result!r}")
    inspected_at = inspected_at or f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    inspection_date = inspected_at[:10]
    with _lock, _session() as conn:
        conn.execute("INSERT OR IGNORE INTO products (barcode) VALUES (?)", (barcode,))
        existing = conn.execute(
            """
            SELECT id
            FROM inspections
            WHERE barcode = ? AND substr(inspected_at, 1, 10) = ?
            ORDER BY inspected_at DESC, id DESC
            LIMIT 1
            """,
            (barcode, inspection_date),
        ).fetchone()
        if existing:
            inspection_id = int(existing["id"])
            conn.execute(
                """
                UPDATE inspections
                SET result = ?, inspected_at = ?, note = ?, operator = ?, operator_role = ?,
                    confidence = ?, active_cameras = ?, session_id = ?, source = ?
                WHERE id = ?
                """,
                (
                    result,
                    inspected_at,
                    note,
                    operator,
                    operator_role,
                    confidence,
                    active_cameras,
                    session_id,
                    source,
                    inspection_id,
                ),
            )
            conn.execute(
                """
                DELETE FROM inspections
                WHERE barcode = ? AND substr(inspected_at, 1, 10) = ? AND id <> ?
                """,
                (barcode, inspection_date, inspection_id),
            )
            return inspection_id
        cur = conn.execute(
            """
            INSERT INTO inspections
                (barcode, result, inspected_at, note, operator, operator_role,
                 confidence, active_cameras, session_id, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (barcode, result, inspected_at, note, operator, operator_role,
             confidence, active_cameras, session_id, source),
        )
        return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# 工作時段（開始/結束工作 = 登入/登出）
# ---------------------------------------------------------------------------
def start_work_session(operator: str, operator_role: str | None = None, login_time: str | None = None) -> int:
    """開始一段工作時段，回傳 session id（登入時呼叫）。"""
    login_time = login_time or f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    with _lock, _session() as conn:
        cur = conn.execute(
            "INSERT INTO work_sessions (operator, operator_role, login_time) VALUES (?, ?, ?)",
            (operator, operator_role, login_time),
        )
        return int(cur.lastrowid)


def end_work_session(session_id: int | None, logout_time: str | None = None) -> None:
    """結束工作時段，填入登出時間（登出時呼叫）。"""
    if not session_id:
        return
    logout_time = logout_time or f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    with _lock, _session() as conn:
        conn.execute(
            "UPDATE work_sessions SET logout_time = ? WHERE id = ?",
            (logout_time, int(session_id)),
        )


def get_work_sessions(operator: str | None = None, limit: int = 500) -> list[dict]:
    """工作時段清單（新到舊），含每段的件數與 NG 數。"""
    clause, params = "", []
    if operator is not None:
        clause = "WHERE s.operator = ?"
        params.append(operator)
    params.append(max(1, int(limit)))
    with _lock, _session() as conn:
        rows = conn.execute(
            f"""
            SELECT s.id, s.operator, s.operator_role, s.login_time, s.logout_time,
                   COUNT(i.id) AS total,
                   SUM(CASE WHEN i.result = 'NG' THEN 1 ELSE 0 END) AS ng
            FROM work_sessions s
            LEFT JOIN inspections i ON i.session_id = s.id
            {clause}
            GROUP BY s.id
            ORDER BY s.login_time DESC, s.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_session_inspections(session_id: int) -> list[dict]:
    """某工作時段內的每件檢驗（序號 + OK/NG + 時間），由舊到新。"""
    with _lock, _session() as conn:
        rows = conn.execute(
            """
            SELECT id, barcode, result, inspected_at, confidence, note, source
            FROM inspections
            WHERE session_id = ?
            ORDER BY inspected_at ASC, id ASC
            """,
            (int(session_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def get_orphan_inspections(operator: str | None = None) -> list[dict]:
    """未綁定工作時段的檢驗（例如 web 端或舊資料），歸到「未指定工作時段」。"""
    clause, params = "", []
    if operator is not None:
        clause = "AND operator = ?"
        params.append(operator)
    with _lock, _session() as conn:
        rows = conn.execute(
            f"""
            SELECT id, barcode, result, inspected_at, confidence, note, source
            FROM inspections
            WHERE session_id IS NULL {clause}
            ORDER BY inspected_at ASC, id ASC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_history(
    barcode: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    result: str | None = None,
    operator: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """查詢檢驗歷史。

    給 barcode 則只查該品項；start/end 為 ISO 日期區間（含端點）；result 篩 PASS/NG；
    operator 限定操作者（供非管理者只看自己的紀錄）。依時間新到舊排序，最多 limit 筆。
    """
    clauses, params = [], []
    if barcode:
        clauses.append("i.barcode = ?")
        params.append(barcode.strip())
    if start:
        clauses.append("i.inspected_at >= ?")
        params.append(start)
    if end:
        clauses.append("i.inspected_at <= ?")
        params.append(f"{end} 23:59:59" if len(end) <= 10 else end)
    if result in _VALID_RESULTS:
        clauses.append("i.result = ?")
        params.append(result)
    if operator is not None:
        clauses.append("i.operator = ?")
        params.append(operator)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, int(limit)))
    with _lock, _session() as conn:
        rows = conn.execute(
            f"""
            SELECT i.id, i.barcode, p.name AS product_name, i.result, i.inspected_at,
                   i.note, i.operator, i.operator_role, i.confidence, i.active_cameras
            FROM inspections i
            LEFT JOIN products p ON p.barcode = i.barcode
            {where}
            ORDER BY i.inspected_at DESC, i.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_stats(barcode: str | None = None) -> dict:
    """回傳統計：總數、OK(PASS) 數、NG 數、不良率(%)。"""
    clause, params = "", []
    if barcode:
        clause = "WHERE barcode = ?"
        params.append(barcode.strip())
    with _lock, _session() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN result = 'PASS' THEN 1 ELSE 0 END) AS ok,
                SUM(CASE WHEN result = 'NG' THEN 1 ELSE 0 END) AS ng
            FROM inspections {clause}
            """,
            params,
        ).fetchone()
    total = row["total"] or 0
    ok = row["ok"] or 0
    ng = row["ng"] or 0
    ng_rate = round(ng / total * 100, 2) if total else 0.0
    return {"barcode": barcode, "total": total, "ok": ok, "ng": ng, "ng_rate": ng_rate}


def get_ng_ranking(top: int = 10) -> list[dict]:
    """回傳不良率最高的前 N 個品項（至少有一筆 NG 才列入），供儀表板呈現。"""
    with _lock, _session() as conn:
        rows = conn.execute(
            """
            SELECT i.barcode, p.name AS product_name,
                   COUNT(*) AS total,
                   SUM(CASE WHEN i.result = 'NG' THEN 1 ELSE 0 END) AS ng
            FROM inspections i
            LEFT JOIN products p ON p.barcode = i.barcode
            GROUP BY i.barcode
            HAVING ng > 0
            ORDER BY (CAST(ng AS REAL) / total) DESC, ng DESC
            LIMIT ?
            """,
            (max(1, int(top)),),
        ).fetchall()
    result = []
    for row in rows:
        total = row["total"] or 0
        ng = row["ng"] or 0
        result.append(
            {
                "barcode": row["barcode"],
                "product_name": row["product_name"],
                "total": total,
                "ng": ng,
                "ng_rate": round(ng / total * 100, 2) if total else 0.0,
            }
        )
    return result


def list_products() -> list[dict]:
    """列出品項主檔，附上各品項的檢驗筆數。"""
    with _lock, _session() as conn:
        rows = conn.execute(
            """
            SELECT p.barcode, p.name, p.spec, p.created_at,
                   COUNT(i.id) AS inspection_count
            FROM products p
            LEFT JOIN inspections i ON i.barcode = p.barcode
            GROUP BY p.barcode
            ORDER BY p.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def update_product(barcode: str, name: str | None = None, spec: str | None = None) -> None:
    """維護品項的品名 / 規格。"""
    barcode = (barcode or "").strip()
    if not barcode:
        return
    with _lock, _session() as conn:
        conn.execute("INSERT OR IGNORE INTO products (barcode) VALUES (?)", (barcode,))
        conn.execute(
            "UPDATE products SET name = ?, spec = ? WHERE barcode = ?",
            (name, spec, barcode),
        )
