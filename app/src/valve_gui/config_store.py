import json
from dataclasses import asdict

from valve_gui.models import CameraConfig, DisplayConfig, ModelConfig
from valve_gui.paths import APP_CONFIG_PATH
from valve_gui.permissions import CONFIGURABLE_PERMISSIONS, DEFAULT_ROLE_PASSWORDS, ROLE_DEVELOPER, default_role_permissions


def load_app_config(state):
    if not APP_CONFIG_PATH.exists():
        return
    with open(APP_CONFIG_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    state.operator_camera_index = int(data.get("operator_camera_index", state.operator_camera_index))
    state.use_simulation = bool(data.get("use_simulation", state.use_simulation))
    role_passwords = data.get("role_passwords", {})
    if isinstance(role_passwords, dict):
        merged_passwords = dict(DEFAULT_ROLE_PASSWORDS)
        for role, password in role_passwords.items():
            if role in merged_passwords:
                merged_passwords[role] = str(password)
        state.role_passwords = merged_passwords

    role_permissions = data.get("role_permissions", {})
    merged_permissions = default_role_permissions()
    if isinstance(role_permissions, dict):
        allowed_permissions = set(CONFIGURABLE_PERMISSIONS)
        for role, permissions in role_permissions.items():
            if role == ROLE_DEVELOPER or role not in merged_permissions:
                continue
            if isinstance(permissions, list):
                merged_permissions[role] = {item for item in permissions if item in allowed_permissions}
    state.role_permissions = merged_permissions

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
        "role_passwords": state.role_passwords,
        "role_permissions": {
            role: sorted(permissions)
            for role, permissions in state.role_permissions.items()
        },
        "inspection_cameras": [asdict(config) for config in state.inspection_cameras],
        "model_configs": [asdict(config) for config in state.model_configs],
    }
    with open(APP_CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
