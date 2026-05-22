from dataclasses import dataclass, field

from valve_gui.permissions import default_role_labels, default_role_passwords, default_role_permissions


@dataclass
class CameraConfig:
    slot: int
    device_index: int
    enabled: bool = True
    flip_horizontal: bool = False
    flip_vertical: bool = False
    rotation_degrees: int = 0
    assigned_model_name: str = ""
    assigned_model_names: list[str] = field(default_factory=list)
    region_detection_enabled: bool = False
    detection_regions: list[dict] = field(default_factory=list)
    exclusion_regions: list[dict] = field(default_factory=list)


@dataclass
class ModelConfig:
    name: str
    modality: str = "vision"
    file_path: str = ""
    enabled: bool = True


@dataclass
class DisplayConfig:
    mode: str = "auto"
    width: int = 1440
    height: int = 900


@dataclass
class DecisionConfig:
    pass_confidence_threshold: float = 0.5
    model_rules: dict[str, dict] = field(default_factory=dict)


@dataclass
class RegionOverlayConfig:
    show_on_monitor: bool = True
    detection_color: str = "#22c55e"
    exclusion_color: str = "#ef4444"
    yolo_color: str = "#22c55e"
    yolo_model_colors: dict[str, str] = field(default_factory=dict)


@dataclass
class InspectionRecord:
    timestamp: str
    operator_name: str
    operator_role: str
    result: str
    part_id: str
    active_cameras: str
    confidence: str
    note: str


@dataclass
class OperatorSession:
    operator_name: str
    operator_role: str
    login_time: str
    logout_time: str = ""
    photo_path: str = ""


@dataclass
class UserAccount:
    username: str
    display_name: str
    role: str = "operator"
    password: str = ""
    enabled: bool = True


@dataclass
class AppState:
    operator_name: str = ""
    operator_role: str = "operator"
    operator_photo_path: str = ""
    login_time: str = ""
    is_logged_in: bool = False
    settings_applied: bool = False
    model_configs: list[ModelConfig] = field(default_factory=list)
    detected_cameras: list[int] = field(default_factory=list)
    inspection_cameras: list[CameraConfig] = field(
        default_factory=lambda: [CameraConfig(slot=i + 1, device_index=i, enabled=True) for i in range(4)]
    )
    operator_camera_index: int = 4
    use_simulation: bool = True
    display: DisplayConfig = field(default_factory=DisplayConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    region_overlay: RegionOverlayConfig = field(default_factory=RegionOverlayConfig)
    role_labels: dict[str, str] = field(default_factory=default_role_labels)
    role_passwords: dict[str, str] = field(default_factory=default_role_passwords)
    role_permissions: dict[str, set[str]] = field(default_factory=default_role_permissions)
    user_accounts: list[UserAccount] = field(default_factory=list)
    records: list[InspectionRecord] = field(default_factory=list)
    sessions: list[OperatorSession] = field(default_factory=list)
