"""Stage 5 - score the segmentation and export metrics, plots and profiles."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)

from common import ROOT, ensure_dir, get_logger, load_params, write_json  # noqa: E402
from preprocess import build_features  # noqa: E402

log = get_logger("evaluate")


def main() -> None:
    p = load_params("evaluate")
    data_p = load_params("data")
    X = pd.read_csv(ROOT / "data/processed/features.csv", index_col=0)
    labels = pd.read_csv(ROOT / "data/processed/assignments.csv", index_col=0)["cluster"].loc[X.index]
    raw = pd.read_csv(ROOT / data_p["raw_path"]).set_index(data_p["id_column"]).loc[X.index]

    sizes = labels.value_counts().sort_index()
    ref, _ = build_features(raw.reset_index(), p["reference"], data_p["id_column"])
    ref = ref.loc[X.index]
    scores = {
        "n_customers": int(len(X)),
        "n_clusters": int(labels.nunique()),
        "silhouette": round(float(silhouette_score(X, labels)), 5),
        "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 5),
        "calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 3),
        # Same labels scored in the fixed reference space -> comparable across preprocessing.
        "silhouette_ref": round(float(silhouette_score(ref, labels)), 5),
        "davies_bouldin_ref": round(float(davies_bouldin_score(ref, labels)), 5),
        "calinski_harabasz_ref": round(float(calinski_harabasz_score(ref, labels)), 3),
        "smallest_cluster_share": round(float(sizes.min() / len(X)), 5),
        "largest_cluster_share": round(float(sizes.max() / len(X)), 5),
    }
    write_json(scores, "metrics/scores.json")

    # Cluster sizes (bar chart in `dvc plots`).
    pd.DataFrame({"cluster": sizes.index, "customers": sizes.values}).to_csv(
        ensure_dir("plots/cluster_sizes.csv"), index=False)

    # 2-D PCA projection, sampled to keep the plot light.
    pca = PCA(n_components=2, random_state=p["random_state"])
    coords = pd.DataFrame(pca.fit_transform(X), index=X.index, columns=["pc1", "pc2"])
    coords["cluster"] = labels.astype(str)
    sample = coords.sample(n=min(p["scatter_sample"], len(coords)), random_state=p["random_state"])
    sample.round(4).to_csv(ensure_dir("plots/pca_scatter.csv"), index=False)

    fig, ax = plt.subplots(figsize=(7, 5))
    for c, grp in sample.groupby("cluster"):
        ax.scatter(grp.pc1, grp.pc2, s=8, alpha=0.6, label=f"cluster {c}")
    ax.set(title=f"Customer segments (PCA, silhouette={scores['silhouette']:.3f})",
           xlabel=f"PC1 ({pca.explained_variance_ratio_[0]:.0%} var)",
           ylabel=f"PC2 ({pca.explained_variance_ratio_[1]:.0%} var)")
    ax.legend(markerscale=2)
    fig.tight_layout()
    fig.savefig(ensure_dir("plots/pca_clusters.png"), dpi=110)
    plt.close(fig)

    # Business-readable profile: mean of the *raw* features per segment.
    profile = raw.assign(cluster=labels.values).groupby("cluster").mean(numeric_only=True)
    profile.insert(0, "customers", sizes)
    profile.round(2).to_csv(ensure_dir("reports/cluster_profiles.csv"))

    log.info("scores=%s", scores)


if __name__ == "__main__":
    main()
