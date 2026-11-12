"""TD5 : cache, fenêtres, bruit, traçabilité SQL et réexécution."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from gazette.mlops.clustering import cluster, metrics, name_themes
from gazette.mlops.embeddings import cache_identity, digest, embed_cached
from gazette.mlops.pipeline import load_config, read_articles, run_pipeline


@pytest.fixture
def database():
    from test_postgres_storage import database as storage_database

    yield from storage_database.__wrapped__()


def config():
    return load_config(Path("config/clustering.yaml"))


class Encoder:
    calls = 0

    def __init__(self, parameters):
        self.parameters = parameters

    def encode(self, texts):
        Encoder.calls += 1
        output = np.zeros((len(texts), self.parameters["dimension"]), dtype=np.float32)
        for index, text in enumerate(texts):
            output[index, int(digest(text)[:4], 16) % output.shape[1]] = 1
        return output


def test_hash_changes_with_text_and_model_revision():
    params = config()["embedding"]
    first = cache_identity("Titre\nRésumé", params)
    assert first != cache_identity("Autre titre\nRésumé", params)
    assert first != cache_identity("Titre\nRésumé", {**params, "revision": "a" * 40})


def test_noise_empty_single_and_metrics():
    params = config()["clustering"]
    vectors = np.zeros((0, 384))
    labels = cluster(vectors, params)
    assert metrics(vectors, labels)["silhouette"] is None
    assert list(cluster(np.eye(1, 384), params)) == [-1]
    assert name_themes([], labels, config()["naming"]) == []
    assert metrics(np.eye(3), np.array([-1, -1, -1]))["noise_ratio"] == 1


def test_two_dense_groups_and_naming():
    rng = np.random.default_rng(42)
    vectors = np.vstack(
        [
            [1, 0, 0] + rng.normal(0, 0.01, (5, 3)),
            [0, 1, 0] + rng.normal(0, 0.01, (5, 3)),
        ]
    )
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    labels = cluster(vectors, config()["clustering"])
    assert metrics(vectors, labels)["themes_count"] == 2
    assert metrics(vectors, labels)["silhouette"] > 0.9
    articles = [{"titre": "Football victoire championnat", "resume": "Équipe stade"}] * 5 + [
        {"titre": "Économie budget impôts", "resume": "Déficit fiscal"}
    ] * 5
    themes = name_themes(articles, labels, config()["naming"])
    assert len(themes) == 2 and all(t["mots_cles"] for t in themes)


def test_cache_ten_articles_twice(database):
    conn, _, _ = database
    articles = [{"titre": f"Article {i}", "resume": "Résumé"} for i in range(10)]
    params = config()["embedding"]
    vectors, first = embed_cached(conn, articles, params, Encoder)
    again, second = embed_cached(conn, articles, params, Encoder)
    assert vectors.shape == (10, 384)
    assert first["encoded_texts"] == 10
    assert second["encoded_texts"] == 0 and second["cache_hits"] == 10
    np.testing.assert_array_equal(vectors, again)
    changed = [*articles[:9], {"titre": "Nouveau texte", "resume": "Résumé"}]
    _, third = embed_cached(conn, changed, params, Encoder)
    assert third["encoded_texts"] == 1


def add_articles(conn, tmp_path):
    from gazette.processing.persist import rebuild_quality
    from gazette.storage.database import store_items
    from gazette.storage.raw import parse_raw_items

    now = datetime.now(UTC).replace(microsecond=0)
    xml = '<rss version="2.0"><channel><title>Test</title>'
    for i in range(10):
        xml += (
            f"<item><title>Actualité numéro {i}</title>"
            f"<description>Résumé numéro {i}</description>"
            f"<link>https://example.org/mlops/{i}</link></item>"
        )
    xml += "</channel></rss>"
    articles = parse_raw_items(xml.encode(), "lemonde", now)
    dates = [now - timedelta(hours=25), now + timedelta(minutes=2)] + [now] * 8
    for article, date in zip(articles, dates, strict=True):
        article["publie_le"] = date.isoformat()
    store_items(conn, articles, tmp_path)
    return now, rebuild_quality


def scoped_connect(monkeypatch, schema):
    import psycopg2

    original = psycopg2.connect

    def connect(*args, **kwargs):
        return original(*args, **kwargs, options=f"-c search_path={schema}")

    monkeypatch.setattr(psycopg2, "connect", connect)


def test_pipeline_snapshot_replay_and_quality_rebuild(database, tmp_path, monkeypatch):
    conn, schema, url = database
    now, rebuild = add_articles(conn, tmp_path / "raw")
    scoped_connect(monkeypatch, schema)
    rebuild(url, tmp_path / "raw", now=now)
    assert len(read_articles(conn, now)) == 8  # vieux et futur exclus
    result = run_pipeline(
        url,
        "config/clustering.yaml",
        tmp_path / "runs",
        cutoff=now,
        airflow_run_id="test",
        encoder_factory=Encoder,
    )
    assert result["input_count"] == 8
    rebuild(url, tmp_path / "raw", now=now)
    reused = run_pipeline(
        url,
        "config/clustering.yaml",
        tmp_path / "runs",
        cutoff=now,
        airflow_run_id="test",
        encoder_factory=Encoder,
    )
    assert reused["reused"] and result["run_id"] == reused["run_id"]
    with conn.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM articles_themes WHERE run_id=%s", (result["run_id"],))
        assert cursor.fetchone()[0] == 8
        cursor.execute("SELECT count(*) FROM run_articles WHERE run_id=%s", (result["run_id"],))
        assert cursor.fetchone()[0] == 8
    manifest = json.loads((Path(result["artifacts"]) / "manifest.json").read_text())
    assert manifest["input_hash"] == result["input_hash"]
    with conn.cursor() as cursor:
        cursor.execute("UPDATE articles_propres SET titre='Texte modifié après le run'")
    conn.commit()
    replay = run_pipeline(
        url,
        "config/clustering.yaml",
        tmp_path / "runs",
        replay_run_id=result["run_id"],
        encoder_factory=Encoder,
    )
    assert replay["input_hash"] == result["input_hash"]
    assert replay["metrics"]["cache_hits"] == 8
    import hashlib

    for name, metadata in manifest["files"].items():
        assert (
            hashlib.sha256((Path(result["artifacts"]) / name).read_bytes()).hexdigest()
            == metadata["sha256"]
        )


def test_failed_run_is_recorded(database, tmp_path, monkeypatch):
    conn, schema, url = database
    now, rebuild = add_articles(conn, tmp_path / "raw")
    scoped_connect(monkeypatch, schema)
    rebuild(url, tmp_path / "raw", now=now)

    def fail(_):
        raise RuntimeError("Panne modèle simulée")

    with pytest.raises(RuntimeError, match="Panne modèle"):
        run_pipeline(
            url, "config/clustering.yaml", tmp_path / "runs", cutoff=now, encoder_factory=fail
        )
    with conn.cursor() as cursor:
        cursor.execute("SELECT status,error FROM runs")
        status, error = cursor.fetchone()
        assert status == "failed" and "Panne modèle" in error
