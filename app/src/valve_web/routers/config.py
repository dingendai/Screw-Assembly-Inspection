"""Configuration endpoints (mirrors SettingsPage / Decision / Region / Display).

All writes reuse valve_gui.config_store normalisers and persist via
save_app_config to the shared app_config.json.
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from valve_gui.camera import detect_camera_indexes
from valve_gui.config_store import (
    normalise_color,
    normalise_color_map,
    normalise_decision_rules,
    normalise_regions,
    save_app_config,
)
from valve_gui.model_registry import discover_model_configs, ensure_model_configs, set_camera_model_names
from valve_gui.models import CameraConfig, DecisionConfig, DisplayConfig, ModelConfig, RegionOverlayConfig
from valve_gui.permissions import PERMISSION_OPEN_SETTINGS

from valve_web.deps import require_login, require_permission
from valve_web.schemas import CamerasUpdate, DecisionUpdate, DisplayUpdate, ModelsUpdate, RegionsUpdate
from valve_web.state import WebContext

router = APIRouter(prefix="/api/config", tags=["config"])

_settings_dep = require_permission(PERMISSION_OPEN_SETTINGS)


def _serialize(ctx: WebContext) -> dict:
    state = ctx.state
    return {
        "use_simulation": state.use_simulation,
        "operator_camera_index": state.operator_camera_index,
        "cameras": [asdict(c) for c in state.inspection_cameras],
        "models": [asdict(m) for m in state.model_configs],
        "decision": asdict(state.decision),
        "display": asdict(state.display),
        "region_overlay": asdict(state.region_overlay),
        "detected_cameras": state.detected_cameras,
    }


@router.get("")
def get_config(ctx: WebContext = Depends(_settings_dep)):
    return _serialize(ctx)


def _apply_cameras(ctx: WebContext, items, *, regions_only: bool):
    """Rebuild inspection_cameras from request items."""
    cameras = []
    for index, item in enumerate(items):
        cameras.append(
            CameraConfig(
                slot=int(item.slot or index + 1),
                device_index=int(item.device_index),
                enabled=bool(item.enabled),
                flip_horizontal=bool(item.flip_horizontal),
                flip_vertical=bool(item.flip_vertical),
                rotation_degrees=int(item.rotation_degrees),
                assigned_model_names=list(item.assigned_model_names),
                region_detection_enabled=bool(item.region_detection_enabled),
                detection_regions=normalise_regions([dict(r) for r in item.detection_regions]),
                exclusion_regions=normalise_regions([dict(r) for r in item.exclusion_regions]),
                barcode_read_enabled=bool(item.barcode_read_enabled),
            )
        )
    for camera in cameras:
        set_camera_model_names(camera, camera.assigned_model_names)
    ctx.state.inspection_cameras = cameras


@router.put("/cameras")
def update_cameras(req: CamerasUpdate, ctx: WebContext = Depends(_settings_dep)):
    if req.use_simulation is not None:
        ctx.state.use_simulation = bool(req.use_simulation)
    if req.operator_camera_index is not None:
        ctx.state.operator_camera_index = int(req.operator_camera_index)
    _apply_cameras(ctx, req.cameras, regions_only=False)
    ensure_model_configs(ctx.state)
    save_app_config(ctx.state)
    ctx.reload_cameras()
    return _serialize(ctx)


@router.put("/models")
def update_models(req: ModelsUpdate, ctx: WebContext = Depends(_settings_dep)):
    ctx.state.model_configs = [
        ModelConfig(name=m.name, modality=m.modality, file_path=m.file_path, enabled=m.enabled)
        for m in req.models
        if m.name
    ]
    ensure_model_configs(ctx.state)
    save_app_config(ctx.state)
    ctx.router.clear_model_cache()
    return _serialize(ctx)


@router.post("/models/rescan")
def rescan_models(ctx: WebContext = Depends(_settings_dep)):
    discovered = discover_model_configs()
    known = {m.file_path for m in ctx.state.model_configs}
    ctx.state.model_configs.extend(m for m in discovered if m.file_path not in known)
    ensure_model_configs(ctx.state)
    save_app_config(ctx.state)
    return _serialize(ctx)


@router.put("/decision")
def update_decision(req: DecisionUpdate, ctx: WebContext = Depends(_settings_dep)):
    rules = {key: rule.model_dump() for key, rule in req.model_rules.items()}
    ctx.state.decision = DecisionConfig(
        pass_confidence_threshold=max(0.0, min(1.0, float(req.pass_confidence_threshold))),
        model_rules=normalise_decision_rules(rules),
    )
    save_app_config(ctx.state)
    return _serialize(ctx)


@router.put("/regions")
def update_regions(req: RegionsUpdate, ctx: WebContext = Depends(_settings_dep)):
    _apply_cameras(ctx, req.cameras, regions_only=True)
    if req.region_overlay is not None:
        ov = req.region_overlay
        current = ctx.state.region_overlay
        ctx.state.region_overlay = RegionOverlayConfig(
            show_on_monitor=bool(ov.get("show_on_monitor", current.show_on_monitor)),
            detection_color=normalise_color(ov.get("detection_color", current.detection_color), current.detection_color),
            exclusion_color=normalise_color(ov.get("exclusion_color", current.exclusion_color), current.exclusion_color),
            yolo_color=normalise_color(ov.get("yolo_color", current.yolo_color), current.yolo_color),
            yolo_model_colors=normalise_color_map(ov.get("yolo_model_colors", current.yolo_model_colors)),
        )
    save_app_config(ctx.state)
    ctx.reload_cameras()
    return _serialize(ctx)


@router.put("/display")
def update_display(req: DisplayUpdate, ctx: WebContext = Depends(_settings_dep)):
    mode = req.mode if req.mode in {"auto", "custom", "fullscreen"} else "auto"
    theme = req.theme.strip().lower() if req.theme.strip().lower() in {"dark", "light"} else "dark"
    ctx.state.display = DisplayConfig(
        mode=mode,
        width=int(req.width),
        height=int(req.height),
        font_size=max(12, min(40, int(req.font_size))),
        theme=theme,
    )
    save_app_config(ctx.state)
    return _serialize(ctx)


@router.post("/theme")
def set_theme(theme: str, ctx: WebContext = Depends(require_login)):
    """Persist just the theme (any logged-in user); leaves font size etc intact."""
    value = theme.strip().lower()
    if value not in {"dark", "light"}:
        return {"theme": ctx.state.display.theme}
    ctx.state.display.theme = value
    save_app_config(ctx.state)
    return {"theme": value}


@router.post("/cameras/scan")
async def scan_cameras(ctx: WebContext = Depends(_settings_dep)):
    ctx.cameras.stop_all()
    found = await run_in_threadpool(detect_camera_indexes, 12)
    ctx.state.detected_cameras = found
    return {"detected_cameras": found}
