"""Stage 3 - sweep k for K-Means and locate the elbow with `kneed`."""
from __future__ import annotations

import pandas as pd
from kneed import KneeLocator
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from common import ROOT, ensure_dir, get_logger, load_params, write_json

log = get_logger("elbow")


def main() -> None:
    p = load_params("elbow")
    X = pd.read_csv(ROOT / "data/processed/features.csv", index_col=0)

    rows = []
    for k in range(p["k_min"], p["k_max"] + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=p["random_state"]).fit(X)
        sil = silhouette_score(X, km.labels_, sample_size=3000, random_state=p["random_state"])
        rows.append({"k": k, "inertia": round(float(km.inertia_), 3), "silhouette": round(float(sil), 5)})
        log.info("k=%d inertia=%.1f silhouette=%.4f", k, km.inertia_, sil)

    curve = pd.DataFrame(rows)
    curve.to_csv(ensure_dir("plots/elbow.csv"), index=False)

    knee = KneeLocator(curve["k"], curve["inertia"], curve="convex", direction="decreasing").knee
    best_sil = curve.loc[curve["silhouette"].idxmax()]
    write_json(
        {
            "knee_k": int(knee) if knee is not None else int(p["k_min"]),
            "best_silhouette_k": int(best_sil["k"]),
            "best_silhouette": float(best_sil["silhouette"]),
        },
        "metrics/elbow.json",
    )
    log.info("knee=%s best_silhouette_k=%d", knee, best_sil["k"])


if __name__ == "__main__":
    main()
