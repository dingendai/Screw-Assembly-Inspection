"""品管條碼資料庫 — 查詢 / 統計 / 品項主檔 API。

讀寫一律走 valve_gui.qc_db（SQLite 單一真相），與桌面端共用同一個 qc.db。
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from valve_gui import qc_db
from valve_gui.permissions import PERMISSION_QC_PRODUCT_MANAGE, PERMISSION_QC_VIEW

from valve_web.deps import require_permission
from valve_web.state import WebContext

router = APIRouter(prefix="/api/qc", tags=["qc"])

_qc_dep = require_permission(PERMISSION_QC_VIEW)
_product_dep = require_permission(PERMISSION_QC_PRODUCT_MANAGE)


@router.get("/stats")
def stats(barcode: str = "", ctx: WebContext = Depends(_qc_dep)):
    return qc_db.get_stats(barcode.strip() or None)


@router.get("/history")
def history(
    barcode: str = "",
    start: str = "",
    end: str = "",
    result: str = "",
    limit: int = 200,
    ctx: WebContext = Depends(_qc_dep),
):
    return {
        "records": qc_db.get_history(
            barcode.strip() or None,
            start=start.strip() or None,
            end=end.strip() or None,
            result=result.strip() or None,
            limit=limit,
        )
    }


@router.get("/ranking")
def ranking(top: int = 10, ctx: WebContext = Depends(_qc_dep)):
    return {"ranking": qc_db.get_ng_ranking(top)}


@router.get("/products")
def products(ctx: WebContext = Depends(_qc_dep)):
    return {"products": qc_db.list_products()}


@router.put("/products/{barcode}")
def update_product(barcode: str, payload: dict, ctx: WebContext = Depends(_product_dep)):
    barcode = (barcode or "").strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="barcode 不可為空")
    name = str(payload.get("name", "")).strip() or None
    spec = str(payload.get("spec", "")).strip() or None
    qc_db.update_product(barcode, name=name, spec=spec)
    return {"products": qc_db.list_products()}


@router.get("/history/export")
def export_history(
    barcode: str = "",
    start: str = "",
    end: str = "",
    result: str = "",
    ctx: WebContext = Depends(_qc_dep),
):
    rows = qc_db.get_history(
        barcode.strip() or None,
        start=start.strip() or None,
        end=end.strip() or None,
        result=result.strip() or None,
        limit=100000,
    )
    fields = [
        "id", "barcode", "product_name", "result", "inspected_at",
        "operator", "confidence", "active_cameras", "note",
    ]
    buffer = io.StringIO()
    buffer.write("﻿")  # BOM for Excel
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    filename = f"qc_inspections_{datetime.now():%Y%m%d_%H%M%S}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
