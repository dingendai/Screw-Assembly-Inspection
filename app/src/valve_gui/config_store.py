import json
from dataclasses import asdict

from valve_gui.models import CameraConfig, DecisionConfig, DisplayConfig, ModelConfig, RegionOverlayConfig, UserAccount
from valve_gui.paths import APP_CONFIG_PATH
from valve_gui.permissions import (
    CONFIGURABLE_PERMISSIONS,
    DEFAULT_ROLE_PASSWORDS,
    ROLE_DEVELOPER,
    default_role_labels,
    default_role_permissions,
)


def load_app_config(state):
    if not APP_CONFIG_PATH.exists():
        return
    with open(APP_CONFIG_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    state.operator_camera_index = int(data.get("operator_camera_index", state.operator_camera_index))
    state.use_simulation = bool(data.get("use_simulation", state.use_simulation))
    role_labels = data.get("role_labels", {})
    default_labels = default_role_labels()
    merged_labels = {ROLE_DEVELOPER: default_labels[ROLE_DEVELOPER]}
    if isinstance(role_labels, dict):
        for role, label in role_labels.items():
            role_key = str(role).strip()
            if role_key and role_key != ROLE_DEVELOPER:
                merged_labels[role_key] = str(label).strip() or role_key
        if ROLE_DEVELOPER in role_labels:
            developer_label = str(role_labels.get(ROLE_DEVELOPER, "")).strip()
            merged_labels[ROLE_DEVELOPER] = developer_label or default_labels[ROLE_DEVELOPER]
    for role, label in default_labels.items():
        if role not in merged_labels:
            merged_labels[role] = label
    state.role_labels = merged_labels

    role_passwords = data.get("role_passwords", {})
    if isinstance(role_passwords, dict):
        merged_passwords = dict(DEFAULT_ROLE_PASSWORDS)
        for role, password in role_passwords.items():
            if role in state.role_labels:
                merged_passwords[str(role)] = str(password)
        state.role_passwords = merged_passwords

    role_permissions = data.get("role_permissions", {})
    merged_permissions = default_role_permissions()
    if isinstance(role_permissions, dict):
        allowed_permissions = set(CONFIGURABLE_PERMISSIONS)
        for role, permissions in role_permissions.items():
            role_key = str(role)
            if role_key == ROLE_DEVELOPER or role_key not in state.role_labels:
                continue
            if isinstance(permissions, list):
                merged_permissions[role_key] = {item for item in permissions if item in allowed_permissions}
    state.role_permissions = merged_permissions

    users = data.get("user_accounts", [])
    if isinstance(users, list):
        state.user_accounts = [
            UserAccount(
                username=str(item.get("username", "")).strip(),
                display_name=str(item.get("display_name", "")).strip(),
                role=str(item.get("role", "operator")).strip() or "operator",
                password=str(item.get("password", "")),
                enabled=bool(item.get("enabled", True)),
            )
            for item in users
            if isinstance(item, dict) and str(item.get("username", "")).strip()
        ]

    display = data.get("display", {})
    if display:
        mode = str(display.get("mode", state.display.mode))
        if mode not in {"auto", "custom", "fullscreen"}:
            mode = "auto"
        state.display = DisplayConfig(
            mode=mode,
            width=int(display.get("width", state.display.width)),
            height=int(display.get("height", state.display.height)),
        )

    decision = data.get("decision", {})
    if isinstance(decision, dict):
        state.decision = DecisionConfig(
            pass_confidence_threshold=float(
                decision.get("pass_confidence_threshold", state.decision.pass_confidence_threshold)
            ),
            model_rules=normalise_decision_rules(decision.get("model_rules", {})),
        )

    region_overlay = data.get("region_overlay", {})
    if isinstance(region_overlay, dict):
        state.region_overlay = RegionOverlayConfig(
            show_on_monitor=bool(region_overlay.get("show_on_monitor", state.region_overlay.show_on_monitor)),
            detection_color=normalise_color(
                region_overlay.get("detection_color", state.region_overlay.detection_color),
                state.region_overlay.detection_color,
            ),
            exclusion_color=normalise_color(
                region_overlay.get("exclusion_color", state.region_overlay.exclusion_color),
                state.region_overlay.exclusion_color,
            ),
        )

    cameras = data.get("inspection_cameras", [])
    if cameras:
        state.inspection_cameras = [
            CameraConfig(
                slot=int(item.get("slot", index + 1)),
                device_index=int(item.get("device_index", index)),
                enabled=bool(item.get("enabled", True)),
                flip_horizontal=bool(item.get("flip_horizontal", False)),
                flip_vertical=bool(item.get("flip_vertical", False)),
                rotation_degrees=int(item.get("rotation_degrees", 0)),
                assigned_model_name=str(item.get("assigned_model_name", "")),
                assigned_model_names=normalise_model_names(item.get("assigned_model_names", [])),
                region_detection_enabled=bool(item.get("region_detection_enabled", False)),
                detection_regions=normalise_regions(item.get("detection_regions", [])),
                exclusion_regions=normalise_regions(item.get("exclusion_regions", [])),
            )
            for index, item in enumerate(cameras)
        ]

    models = data.get("model_configs", [])
    if models:
        state.model_configs = [
            ModelConfig(
                name=str(item.get("name", "")),
                modality=str(item.get("modality", "vision")),
                file_path=str(item.get("file_path", "")),
                enabled=bool(item.get("enabled", True)),
            )
            for item in models
            if item.get("name")
        ]


def save_app_config(state):
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "operator_camera_index": state.operator_camera_index,
        "use_simulation": state.use_simulation,
        "display": asdict(state.display),
        "decision": asdict(state.decision),
        "region_overlay": asdict(state.region_overlay),
        "role_labels": state.role_labels,
        "role_passwords": state.role_passwords,
        "role_permissions": {
            role: sorted(permissions)
            for role, permissions in state.role_permissions.items()
        },
        "user_accounts": [asdict(account) for account in state.user_accounts],
        "inspection_cameras": [asdict(config) for config in state.inspection_cameras],
        "model_configs": [asdict(config) for config in state.model_configs],
    }
    with open(APP_CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def normalise_model_names(value):
    if isinstance(value, list):
        return [str(name).strip() for name in value if str(name).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalise_decision_rules(value):
    if not isinstance(value, dict):
        return {}
    rules = {}
    for key, rule in value.items():
        if not isinstance(rule, dict):
            continue
        rule_key = str(key).strip()
        if not rule_key:
            continue
        try:
            confidence_threshold = float(rule.get("confidence_threshold", 0.5))
        except (TypeError, ValueError):
            confidence_threshold = 0.5
        try:
            required_object_count = int(rule.get("required_object_count", 1))
        except (TypeError, ValueError):
            required_object_count = 1
        rules[rule_key] = {
            "confidence_threshold": max(0.0, min(1.0, confidence_threshold)),
            "required_object_count": max(0, required_object_count),
        }
    return rules


def normalise_color(value, fallback):
    text = str(value).strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text
        except ValueError:
            pass
    return fallback


def normalise_regions(value):
    if not isinstance(value, list):
        return []
    regions = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            x = float(item.get("x", 0.0))
            y = float(item.get("y", 0.0))
            width = float(item.get("w", item.get("width", 0.0)))
            height = float(item.get("h", item.get("height", 0.0)))
        except (TypeError, ValueError):
            continue
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        width = max(0.0, min(1.0 - x, width))
        height = max(0.0, min(1.0 - y, height))
        if width <= 0.001 or height <= 0.001:
            continue
        regions.append({"x": x, "y": y, "w": width, "h": height})
    return regions
