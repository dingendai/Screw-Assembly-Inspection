from pathlib import Path

from valve_gui.models import ModelConfig
from valve_gui.paths import MODEL_DIR


MODEL_EXTENSIONS = {".pt", ".onnx", ".engine", ".weights", ".bin", ".json"}


def discover_model_configs(model_dir: Path = MODEL_DIR) -> list[ModelConfig]:
    if not model_dir.exists():
        return []

    configs = []
    for path in sorted(model_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in MODEL_EXTENSIONS:
            continue
        name = path.parent.name if path.name.lower() == "last.pt" else path.stem
        configs.append(
            ModelConfig(
                name=name,
                modality="vision",
                file_path=str(path),
                enabled=True,
            )
        )
    return configs


def ensure_model_configs(state):
    discovered = discover_model_configs()
    if not state.model_configs:
        state.model_configs = discovered
    else:
        known_paths = {model.file_path for model in state.model_configs}
        state.model_configs.extend(model for model in discovered if model.file_path not in known_paths)

    enabled_names = [model.name for model in state.model_configs if model.enabled]
    fallback = enabled_names[0] if enabled_names else ""
    for camera in state.inspection_cameras:
        selected_names = camera_model_names(camera)
        valid_names = [name for name in selected_names if name in enabled_names]
        if not valid_names and fallback:
            valid_names = [fallback]
        set_camera_model_names(camera, valid_names)


def enabled_model_names(state) -> list[str]:
    return [model.name for model in state.model_configs if model.enabled]


def model_by_name(state, name: str) -> ModelConfig | None:
    for model in state.model_configs:
        if model.name == name:
            return model
    return None


def camera_model_names(camera) -> list[str]:
    names = []
    assigned_names = getattr(camera, "assigned_model_names", None)
    if isinstance(assigned_names, list):
        names.extend(str(name).strip() for name in assigned_names if str(name).strip())
    legacy_name = str(getattr(camera, "assigned_model_name", "")).strip()
    if legacy_name:
        names.append(legacy_name)
    return list(dict.fromkeys(names))


def set_camera_model_names(camera, names: list[str]):
    deduped = list(dict.fromkeys(str(name).strip() for name in names if str(name).strip()))
    camera.assigned_model_names = deduped
    camera.assigned_model_name = deduped[0] if deduped else ""


def format_camera_model_names(camera) -> str:
    names = camera_model_names(camera)
    return ", ".join(names) if names else "--"
