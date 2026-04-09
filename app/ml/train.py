from __future__ import annotations

from typing import Any

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score

from app.ml.features import FEATURE_COLUMNS, build_training_frame
from app.ml.model_store import save_model

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - optional fallback
    LGBMClassifier = None


def train_direction_model(
    market_data,
    model_name: str = "direction_filter",
    model_dir: str = "models",
) -> dict[str, Any]:
    frame = build_training_frame(market_data)
    if frame.empty:
        raise ValueError("Not enough data to train a model.")

    split_index = max(int(len(frame) * 0.8), 1)
    train = frame.iloc[:split_index]
    test = frame.iloc[split_index:]
    x_train = train[FEATURE_COLUMNS]
    y_train = train["target"]

    if LGBMClassifier is not None:
        model = LGBMClassifier(
            n_estimators=80,
            learning_rate=0.05,
            max_depth=3,
            random_state=42,
            verbosity=-1,
        )
        model_type = "lightgbm"
    else:  # pragma: no cover - only used if LightGBM is unavailable
        model = GradientBoostingClassifier(random_state=42)
        model_type = "gradient_boosting"

    model.fit(x_train, y_train)

    accuracy = 0.0
    if not test.empty:
        y_pred = model.predict(test[FEATURE_COLUMNS])
        accuracy = float(accuracy_score(test["target"], y_pred))

    metadata = {
        "model_name": model_name,
        "model_type": model_type,
        "feature_columns": FEATURE_COLUMNS,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "accuracy": accuracy,
    }
    paths = save_model(model=model, metadata=metadata, model_name=model_name, model_dir=model_dir)
    metadata.update(paths)
    return metadata
