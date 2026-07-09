from dataclasses import dataclass, field

from valve_gui.permissions import default_role_labels, default_role_passwords, default_role_permissions


DEFAULT_INSPECTION_CAMERA_COUNT = 10
DEFAULT_ENABLED_INSPECTION_CAMERA_COUNT = 5


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
    lock_geometry_enabled: bool = False
    lock_geometry_regions: list[dict] = field(default_factory=list)
    focus_mode: str = "auto"
    manual_focus_value: int = 120


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
    font_size: int = 14
    theme: str = "dark"  # web UI only; desktop GUI ignores this


@dataclass
class DecisionConfig:
    pass_confidence_threshold: float = 0.5
    confidence_threshold_mode: str = "custom"
    model_rules: dict[str, dict] = field(default_factory=dict)
    group_rules: dict[str, dict] = field(default_factory=dict)


@dataclass
class RegionOverlayConfig:
    show_on_monitor: bool = True
    show_yolo_on_monitor: bool = True
    show_geometry_on_monitor: bool = True
    detection_color: str = "#22c55e"
    exclusion_color: str = "#ef4444"
    yolo_color: str = "#22c55e"
    yolo_model_colors: dict[str, str] = field(default_factory=dict)


@dataclass
class BarcodeRuleConfig:
    start_token: str = ""
    length: int = 0
    trim_leading_chars: int = 0
    trim_trailing_chars: int = 0
    prefix: str = ""
    suffix: str = ""
    enabled: bool = True


@dataclass
class BarcodeProcessingConfig:
    enabled: bool = False
    barcode_count: int = 1
    join_text: str = ""
    rules: list[BarcodeRuleConfig] = field(default_factory=list)
    trim_leading_chars: int = 0
    prefix: str = ""
    suffix: str = ""


@dataclass
class InspectionWorkflowConfig:
    mode: str = "delay"
    delay_seconds: int = 3


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
    # 序號來源：標籤類別名稱 / "manual" / "auto"（CSV 不含此欄，僅供 SQLite）。
    barcode_source: str = ""


@dataclass
class InspectionTransaction:
    transaction_id: str
    state: str = "idle"
    operator_name: str = ""
    operator_role: str = ""
    session_id: int | None = None
    primary_barcode: str = ""
    secondary_barcode: str = ""
    barcode_source: str = ""
    active_cameras: str = ""
    captured_at: str = ""
    raw_frames: dict[int, object] = field(default_factory=dict)
    inference_result: object | None = None
    save_policy: str = "defer"
    error_message: str = ""


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
    current_work_session_id: int | None = None
    model_configs: list[ModelConfig] = field(default_factory=list)
    model_scan_dir: str = ""
    detected_cameras: list[int] = field(default_factory=list)
    inspection_cameras: list[CameraConfig] = field(
        default_factory=lambda: [
            CameraConfig(
                slot=i + 1,
                device_index=i,
                enabled=i < DEFAULT_ENABLED_INSPECTION_CAMERA_COUNT,
            )
            for i in range(DEFAULT_INSPECTION_CAMERA_COUNT)
        ]
    )
    operator_camera_index: int = 4
    use_simulation: bool = False
    qc_output_dir: str = ""
    display: DisplayConfig = field(default_factory=DisplayConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    region_overlay: RegionOverlayConfig = field(default_factory=RegionOverlayConfig)
    barcode_processing: BarcodeProcessingConfig = field(default_factory=BarcodeProcessingConfig)
    inspection_workflow: InspectionWorkflowConfig = field(default_factory=InspectionWorkflowConfig)
    role_labels: dict[str, str] = field(default_factory=default_role_labels)
    role_passwords: dict[str, str] = field(default_factory=default_role_passwords)
    role_permissions: dict[str, set[str]] = field(default_factory=default_role_permissions)
    user_accounts: list[UserAccount] = field(default_factory=list)
    records: list[InspectionRecord] = field(default_factory=list)
    sessions: list[OperatorSession] = field(default_factory=list)
