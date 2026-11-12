"""Démonstration pédagogique hors production sur les mêmes vecteurs réels d'un run."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans

from gazette.mlops.clustering import cluster, metrics, name_themes
from gazette.mlops.pipeline import load_config

parser = argparse.ArgumentParser()
parser.add_argument("run_directory", type=Path)
args = parser.parse_args()
folder = args.run_directory
articles = json.loads((folder / "input.json").read_text(encoding="utf-8"))
vectors = np.load(folder / "vectors.npy", allow_pickle=False)
config = load_config("config/clustering.yaml")
if len(vectors) < 3:
    raise SystemExit("Au moins trois articles pour la démonstration")
labels_by_method = {
    "kmeans_demo_k8": KMeans(
        n_clusters=min(8, len(vectors)), random_state=42, n_init=10
    ).fit_predict(vectors),
    "agglomeratif_demo_seuil045": AgglomerativeClustering(
        n_clusters=None, distance_threshold=0.45, metric="cosine", linkage="average"
    ).fit_predict(vectors),
    "hdbscan_production": cluster(vectors, config["clustering"]),
}
result = {}
for name, labels in labels_by_method.items():
    result[name] = {
        "metrics": metrics(vectors, labels),
        "themes": name_themes(articles, labels, config["naming"]),
    }
(folder / "comparison-demo.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
