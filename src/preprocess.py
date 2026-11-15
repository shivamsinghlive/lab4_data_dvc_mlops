"""Stage 2 - turn the raw snapshot into a scaled feature matrix."""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler

from common import FREQUENCY_COLUMNS, ROOT, SKEWED_COLUMNS, ensure_dir, get_logger, load_params

log = get_logger("preprocess")

SCALERS = {"standard": StandardScaler, "robust": RobustScaler, "minmax": MinMaxScaler}


def build_features(df: pd.DataFrame, p: dict, id_column: str) -> tuple[pd.DataFrame, object]:
    X = df.set_index(id_column).astype(float)

    # 1. Impute nulls (MINIMUM_PAYMENTS / CREDIT_LIMIT in this dataset).
    if p["impute_strategy"] == "median":
        fill = X.median()
    elif p["impute_strategy"] == "mean":
        fill = X.mean()
    else:
        raise ValueError(f"unknown impute_strategy {p['impute_strategy']!r}")
    X = X.fillna(fill)

    # 2. Frequencies are ratios - force them back into [0, 1].
    freq = [c for c in FREQUENCY_COLUMNS if c in X]
    X[freq] = X[freq].clip(0, 1)

    # 3. Winsorize the long right tail of the monetary columns.
    skewed = [c for c in SKEWED_COLUMNS if c in X]
    if p["clip_quantile"] < 1.0:
        upper = X[skewed].quantile(p["clip_quantile"])
        X[skewed] = X[skewed].clip(upper=upper, axis=1)

    # 4. Compress skew.
    if p["log_transform"]:
        X[skewed] = np.log1p(X[skewed])

    # 5. Scale.
    if p["scaler"] not in SCALERS:
        raise ValueError(f"unknown scaler {p['scaler']!r}")
    scaler = SCALERS[p["scaler"]]()
    scaled = pd.DataFrame(scaler.fit_transform(X), index=X.index, columns=X.columns)
    return scaled, scaler


def main() -> None:
    data_p = load_params("data")
    p = load_params("preprocess")
    df = pd.read_csv(ROOT / data_p["raw_path"])
    features, scaler = build_features(df, p, data_p["id_column"])

    features.to_csv(ensure_dir("data/processed/features.csv"))
    with open(ensure_dir("models/scaler.pkl"), "wb") as fh:
        pickle.dump(scaler, fh)
    log.info("features shape=%s scaler=%s log=%s clip=%s",
             features.shape, p["scaler"], p["log_transform"], p["clip_quantile"])


if __name__ == "__main__":
    main()
