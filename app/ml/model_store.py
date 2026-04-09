from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib


def _base_path(model_name: str, model_dir: str = "models") -> Path:
    path = Path(model_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / model_name


def save_model(model: Any, metadata: dict[str, Any], model_name: str, model_dir: str = "models") -> dict[str, str]:
    base = _base_path(model_name, model_dir)
    model_path = base.with_suffix(".joblib")
    metadata_path = base.with_suffix(".json")
    joblib.dump(model, model_path)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"model_path": str(model_path), "metadata_path": str(metadata_path)}


def load_model(model_name: str, model_dir: str = "models") -> Any:
    base = _base_path(model_name, model_dir)
    model_path = base.with_suffix(".joblib")
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {model_path}")
    return joblib.load(model_path)


def load_metadata(model_name: str, model_dir: str = "models") -> dict[str, Any]:
    base = _base_path(model_name, model_dir)
    metadata_path = base.with_suffix(".json")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Model metadata not found: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))
