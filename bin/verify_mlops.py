"""Test réel de dix articles : modèle CPU puis cache sans second chargement."""

import json
import os
from contextlib import closing
from datetime import UTC, datetime

import numpy as np
import psycopg2

from gazette.mlops.embeddings import embed_cached
from gazette.mlops.pipeline import load_config, read_articles

config = load_config("config/clustering.yaml")
with closing(psycopg2.connect(os.environ["GAZETTE_DATABASE_URL"])) as conn:
    articles = read_articles(conn, datetime.now(UTC))[:10]
    assert len(articles) == 10, "Dix articles propres récents sont nécessaires"
    vectors, first = embed_cached(conn, articles, config["embedding"])

    def forbidden(_):
        raise AssertionError("Le second passage ne doit pas charger le modèle")

    again, second = embed_cached(conn, articles, config["embedding"], forbidden)
    assert vectors.shape == (10, 384)
    assert np.isfinite(vectors).all()
    np.testing.assert_array_equal(vectors, again)
    assert second["cache_hits"] == 10 and second["encoded_texts"] == 0
    print(
        json.dumps(
            {"articles": 10, "shape": list(vectors.shape), "first": first, "second": second},
            ensure_ascii=False,
        )
    )
