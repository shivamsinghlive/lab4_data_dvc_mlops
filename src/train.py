"""Stage 4 - fit the segmentation model and assign every customer a cluster."""
from __future__ import annotations

import pickle

import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.mixture import GaussianMixture

from common import ROOT, ensure_dir, get_logger, load_params, read_json

log = get_logger("train")


def resolve_k(n_clusters) -> int:
    if str(n_clusters).lower() == "auto":
        k = read_json("metrics/elbow.json")["knee_k"]
        log.info("n_clusters=auto -> using elbow knee k=%d", k)
        return int(k)
    return int(n_clusters)


def fit(X: pd.DataFrame, p: dict, k: int):
    algo = p["algorithm"]
    if algo == "kmeans":
        model = KMeans(n_clusters=k, n_init=p["n_init"], random_state=p["random_state"])
        labels = model.fit_predict(X)
    elif algo == "gmm":
        model = GaussianMixture(n_components=k, n_init=p["n_init"], random_state=p["random_state"])
        labels = model.fit(X).predict(X)
    elif algo == "agglomerative":
        model = AgglomerativeClustering(n_clusters=k, linkage="ward")
        labels = model.fit_predict(X)
    else:
        raise ValueError(f"unknown algorithm {algo!r}")
    return model, labels


def main() -> None:
    p = load_params("train")
    X = pd.read_csv(ROOT / "data/processed/features.csv", index_col=0)
    k = resolve_k(p["n_clusters"])
    model, labels = fit(X, p, k)

    with open(ensure_dir("models/model.pkl"), "wb") as fh:
        pickle.dump(model, fh)
    pd.DataFrame({"cluster": labels}, index=X.index).to_csv(ensure_dir("data/processed/assignments.csv"))
    log.info("algorithm=%s k=%d cluster sizes=%s", p["algorithm"], k,
             pd.Series(labels).value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main()
