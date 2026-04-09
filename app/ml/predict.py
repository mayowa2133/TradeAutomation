from __future__ import annotations

import pandas as pd

from app.ml.features import engineer_features
from app.ml.model_store import load_metadata, load_model


def predict_probabilities(
    market_data: pd.DataFrame,
    model_name: str = "direction_filter",
    model_dir: str = "models",
) -> pd.Series:
    features = engineer_features(market_data)
    metadata = load_metadata(model_name=model_name, model_dir=model_dir)
    model = load_model(model_name=model_name, model_dir=model_dir)
    feature_columns = metadata["feature_columns"]
    valid_features = features[feature_columns].dropna()
    if valid_features.empty:
        return pd.Series(dtype=float)
    probabilities = model.predict_proba(valid_features)[:, 1]
    return pd.Series(probabilities, index=valid_features.index, name="ml_probability")
