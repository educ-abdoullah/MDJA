"""Un seul algorithme en production : HDBSCAN, noms par TF-IDF discriminant."""

from collections import Counter

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from gazette.mlops.embeddings import article_text


def cluster(vectors, parameters):
    if len(vectors) < max(parameters["min_cluster_size"], parameters["min_samples"]):
        return np.full(len(vectors), -1, dtype=int)
    return HDBSCAN(
        min_cluster_size=parameters["min_cluster_size"],
        min_samples=parameters["min_samples"],
        metric=parameters["metric"],
        algorithm=parameters["algorithm_backend"],
        cluster_selection_method=parameters["cluster_selection_method"],
        allow_single_cluster=parameters["allow_single_cluster"],
        n_jobs=1,
        copy=True,
    ).fit_predict(vectors.astype(np.float64))


def name_themes(articles, labels, config):
    groups = sorted(set(labels) - {-1})
    if not groups:
        return []
    vectorizer = TfidfVectorizer(
        stop_words=config["stop_words"],
        token_pattern=r"(?u)\b[^\W\d_]{3,}\b",
        ngram_range=(1, 2),
        max_features=10000,
    )
    try:
        matrix = vectorizer.fit_transform([article_text(a) for a in articles])
        terms = vectorizer.get_feature_names_out()
    except ValueError:
        matrix, terms = None, []
    themes = []
    for label in groups:
        members = np.flatnonzero(labels == label)
        keywords = []
        if matrix is not None:
            inside = np.asarray(matrix[members].mean(axis=0)).ravel()
            outside = np.flatnonzero(labels != label)
            contrast = inside.copy()
            if len(outside):
                contrast -= np.asarray(matrix[outside].mean(axis=0)).ravel()
            order = sorted(range(len(terms)), key=lambda i: (-float(contrast[i]), terms[i]))
            keywords = [str(terms[i]) for i in order if contrast[i] > 0][: config["keywords"]]
        themes.append(
            {
                "label": int(label),
                "nom": " / ".join(keywords[:3]) or f"Thème {label + 1}",
                "mots_cles": keywords,
                "taille": len(members),
            }
        )
    return themes


def metrics(vectors, labels):
    sizes = Counter(int(x) for x in labels if x >= 0)
    assigned = labels >= 0
    silhouette = None
    reason = "Au moins deux groupes et plus d'articles que de groupes sont nécessaires"
    if 2 <= len(sizes) < int(assigned.sum()):
        silhouette = float(silhouette_score(vectors[assigned], labels[assigned], metric="cosine"))
        reason = None
    return {
        "themes_count": len(sizes),
        "median_size": float(np.median(list(sizes.values()))) if sizes else 0,
        "noise_count": int((labels < 0).sum()),
        "noise_ratio": float((labels < 0).mean()) if len(labels) else 0,
        "silhouette": silhouette,
        "silhouette_reason": reason,
    }
