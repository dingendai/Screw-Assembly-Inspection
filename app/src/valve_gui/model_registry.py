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
        if not camera.assigned_model_name or camera.assigned_model_name not in enabled_names:
            camera.assigned_model_name = fallback


def enabled_model_names(state) -> list[str]:
    return [model.name for model in state.model_configs if model.enabled]


def model_by_name(state, name: str) -> ModelConfig | None:
    for model in state.model_configs:
        if model.name == name:
            return model
    return None
