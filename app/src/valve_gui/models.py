from dataclasses import dataclass, field

from valve_gui.permissions import default_role_passwords


@dataclass
class CameraConfig:
    slot: int
    device_index: int
    enabled: bool = True
    flip_horizontal: bool = False
    flip_vertical: bool = False
    rotation_degrees: int = 0
    assigned_model_name: str = ""


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
class AppState:
    operator_name: str = ""
    operator_role: str = "operator"
    operator_photo_path: str = ""
    login_time: str = ""
    is_logged_in: bool = False
    settings_applied: bool = False
    yolo_model_path: str = ""
    model_configs: list[ModelConfig] = field(default_factory=list)
    detected_cameras: list[int] = field(default_factory=list)
    inspection_cameras: list[CameraConfig] = field(
        default_factory=lambda: [CameraConfig(slot=i + 1, device_index=i, enabled=True) for i in range(4)]
    )
    operator_camera_index: int = 4
    use_simulation: bool = True
    display: DisplayConfig = field(default_factory=DisplayConfig)
    role_passwords: dict[str, str] = field(default_factory=default_role_passwords)
    records: list[InspectionRecord] = field(default_factory=list)
    sessions: list[OperatorSession] = field(default_factory=list)
