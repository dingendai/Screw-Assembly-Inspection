"""Pydantic request models for the web API.

Responses are plain dicts built from the existing dataclasses (via
``dataclasses.asdict``) to avoid duplicating the schema.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    role: str
    password: str = ""
    name: str = ""
    photo_path: str = ""


class RegionModel(BaseModel):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    model_names: list[str] = Field(default_factory=list)
    roi_id: int | None = None


class CameraModel(BaseModel):
    slot: int
    device_index: int
    enabled: bool = True
    flip_horizontal: bool = False
    flip_vertical: bool = False
    rotation_degrees: int = 0
    assigned_model_names: list[str] = Field(default_factory=list)
    region_detection_enabled: bool = False
    detection_regions: list[dict] = Field(default_factory=list)
    exclusion_regions: list[dict] = Field(default_factory=list)
    lock_geometry_enabled: bool = False
    lock_geometry_regions: list[dict] = Field(default_factory=list)
    barcode_read_enabled: bool = False
    focus_mode: str = "auto"
    manual_focus_value: int = 120


class CamerasUpdate(BaseModel):
    use_simulation: bool | None = None
    operator_camera_index: int | None = None
    cameras: list[CameraModel]


class ModelItem(BaseModel):
    name: str
    modality: str = "vision"
    file_path: str = ""
    enabled: bool = True


class ModelsUpdate(BaseModel):
    models: list[ModelItem]


class DecisionRule(BaseModel):
    confidence_operator: str = ">="
    confidence_threshold: float = 0.5
    required_object_count_operator: str = "="
    required_object_count: int = 1


class DecisionUpdate(BaseModel):
    pass_confidence_threshold: float = 0.5
    confidence_threshold_mode: str = "custom"
    model_rules: dict[str, DecisionRule] = Field(default_factory=dict)


class DisplayUpdate(BaseModel):
    mode: str = "auto"
    width: int = 1440
    height: int = 900
    font_size: int = 14
    theme: str = "dark"


class RegionsUpdate(BaseModel):
    """Per-slot detection/exclusion regions plus the region toggle."""
    cameras: list[CameraModel]
    region_overlay: dict | None = None


class UserItem(BaseModel):
    username: str
    display_name: str = ""
    role: str = "operator"
    password: str = ""
    enabled: bool = True


class PermissionsUpdate(BaseModel):
    role_permissions: dict[str, list[str]] = Field(default_factory=dict)
    role_labels: dict[str, str] | None = None
    role_passwords: dict[str, str] | None = None


class QcOutputUpdate(BaseModel):
    qc_output_dir: str = ""


class InspectRequest(BaseModel):
    part_id: str = ""
