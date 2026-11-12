"""Exécution tracée, entrées figées, cache, thèmes et artefacts du TD5."""

import hashlib
import platform
import re
from contextlib import closing
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import numpy as np
import psycopg2
import yaml
from psycopg2.extras import Json, RealDictCursor

from gazette.mlops.clustering import cluster, metrics, name_themes
from gazette.mlops.embeddings import OnnxEncoder, article_text, digest, embed_cached
from gazette.storage.database import atomic_json


def load_config(path):
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return validate_config(config)


def validate_config(config):
    if config["schema_version"] != 1 or config["window_hours"] != 24:
        raise ValueError("Schéma 1 et fenêtre de 24 h obligatoires")
    embedding, clustering = config["embedding"], config["clustering"]
    if not re.fullmatch(r"[a-f0-9]{40}", embedding["revision"]):
        raise ValueError("Révision modèle non immuable")
    if embedding["preprocessing"] != "titre_resume_mean_l2_v1":
        raise ValueError("Prétraitement inconnu")
    if any(embedding[k] <= 0 for k in ("dimension", "max_length", "batch_size", "threads")):
        raise ValueError("Paramètres embeddings invalides")
    if (
        clustering["algorithm"] != "hdbscan"
        or clustering["metric"] != "cosine"
        or clustering["algorithm_backend"] != "brute"
        or clustering["min_cluster_size"] < 2
        or clustering["min_samples"] < 1
    ):
        raise ValueError("Paramètres HDBSCAN invalides")
    if config["naming"]["keywords"] < 1:
        raise ValueError("Nombre de mots-clés invalide")
    return config


def read_articles(connection, cutoff):
    if cutoff.tzinfo is None:
        raise ValueError("La fenêtre nécessite un fuseau horaire")
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """SELECT article_brut_id AS id,source,titre,resume,lien,publie_le,recupere_le,rubrique
            FROM articles_propres WHERE publie_le >= %s AND publie_le <= %s
            ORDER BY article_brut_id""",
            (cutoff - timedelta(hours=24), cutoff),
        )
        articles = [dict(row) for row in cursor.fetchall()]
    for article in articles:
        article["id"] = article["id"].strip()
        for key in ("publie_le", "recupere_le"):
            article[key] = article[key].astimezone(UTC).isoformat()
    return articles


def run_pipeline(
    database_url,
    config_path,
    output_dir,
    *,
    cutoff=None,
    airflow_run_id=None,
    replay_run_id=None,
    encoder_factory=OnnxEncoder,
):
    config = load_config(config_path)
    cutoff = cutoff or datetime.now(UTC)
    if cutoff.tzinfo is None:
        raise ValueError("cutoff doit avoir un fuseau")
    cutoff = cutoff.astimezone(UTC)
    run_id = str(uuid4())
    software = {
        p: version(p)
        for p in ("numpy", "scikit-learn", "onnxruntime", "tokenizers", "huggingface-hub", "PyYAML")
    }
    software["python"] = platform.python_version()
    software["pipeline_sha256"] = digest(
        {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(__file__).parent.glob("*.py"))
        }
    )
    # Session lock : sérialise les runs même entre CLI et scheduler.
    with closing(psycopg2.connect(database_url, connect_timeout=10)) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext('gazette-mlops'))")
            if replay_run_id:
                cursor.execute(
                    "SELECT parameters,window_end,input_hash FROM runs "
                    "WHERE id=%s AND status='success'",
                    (replay_run_id,),
                )
                original = cursor.fetchone()
                if original is None:
                    raise ValueError("Run à rejouer absent ou non réussi")
                config = validate_config({k: v for k, v in original[0].items() if k != "replay_of"})
                cutoff = original[1]
            if airflow_run_id:
                cursor.execute(
                    "SELECT id,metrics FROM runs WHERE airflow_run_id=%s AND status='success'",
                    (airflow_run_id,),
                )
                previous = cursor.fetchone()
                if previous:
                    return {"run_id": str(previous[0]), "reused": True, "metrics": previous[1]}
            cursor.execute(
                """INSERT INTO runs(id,airflow_run_id,status,window_start,window_end,
                model,model_revision,parameters,software)
                VALUES (%s,%s,'running',%s,%s,%s,%s,%s,%s)""",
                (
                    run_id,
                    airflow_run_id,
                    cutoff - timedelta(hours=24),
                    cutoff,
                    config["embedding"]["model"],
                    config["embedding"]["revision"],
                    Json({**config, **({"replay_of": replay_run_id} if replay_run_id else {})}),
                    Json(software),
                ),
            )
        conn.commit()
        try:
            # Le verrou est le même que le recalcul TD4 ; copier avant sa prochaine modification.
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('gazette-qualite-rebuild'))")
            if replay_run_id:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT snapshot FROM run_articles WHERE run_id=%s "
                        "ORDER BY article_brut_id",
                        (replay_run_id,),
                    )
                    articles = [row[0] for row in cursor.fetchall()]
                if digest(articles) != original[2].strip():
                    raise ValueError("Empreinte des instantanés du run incohérente")
            else:
                articles = read_articles(conn, cutoff)
            input_hash = digest(articles)
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE runs SET input_count=%s,input_hash=%s WHERE id=%s",
                    (len(articles), input_hash, run_id),
                )
                for article in articles:
                    cursor.execute(
                        """INSERT INTO run_articles(run_id,article_brut_id,snapshot,text_hash)
                        VALUES (%s,%s,%s,%s)""",
                        (run_id, article["id"], Json(article), digest(article_text(article))),
                    )
            conn.commit()
            vectors, cache = embed_cached(conn, articles, config["embedding"], encoder_factory)
            labels = cluster(vectors, config["clustering"])
            themes = name_themes(articles, labels, config["naming"])
            measurements = {**metrics(vectors, labels), **cache}
            folder = Path(output_dir) / run_id
            folder.mkdir(parents=True, exist_ok=False)
            assignments = [
                {"article_brut_id": a["id"], "label": int(label) if label >= 0 else None}
                for a, label in zip(articles, labels, strict=True)
            ]
            for name, value in {
                "input.json": articles,
                "themes.json": themes,
                "assignments.json": assignments,
                "parameters.json": config,
                "metrics.json": measurements,
                "software.json": software,
            }.items():
                atomic_json(folder / name, value)
            np.save(folder / "vectors.npy", vectors, allow_pickle=False)
            artifacts = {}
            for path in sorted(folder.iterdir()):
                with path.open("rb") as stream:
                    artifacts[path.name] = {
                        "sha256": hashlib.file_digest(stream, "sha256").hexdigest()
                    }
            manifest = {
                "run_id": run_id,
                "airflow_run_id": airflow_run_id,
                "replay_of": replay_run_id,
                "input_hash": input_hash,
                "artifact_directory": str(folder),
                "files": artifacts,
            }
            atomic_json(folder / "manifest.json", manifest)
            with conn.cursor() as cursor:
                for theme in themes:
                    cursor.execute(
                        """INSERT INTO themes(run_id,label,nom,mots_cles,taille)
                        VALUES (%s,%s,%s,%s,%s)""",
                        (
                            run_id,
                            theme["label"],
                            theme["nom"],
                            Json(theme["mots_cles"]),
                            theme["taille"],
                        ),
                    )
                for assignment in assignments:
                    cursor.execute(
                        "INSERT INTO articles_themes(run_id,article_brut_id,label) "
                        "VALUES (%s,%s,%s)",
                        (run_id, assignment["article_brut_id"], assignment["label"]),
                    )
                cursor.execute(
                    """UPDATE runs SET status='success',finished_at=CURRENT_TIMESTAMP,
                    metrics=%s,artifacts=%s WHERE id=%s""",
                    (Json(measurements), Json(manifest), run_id),
                )
            conn.commit()
            return {
                "run_id": run_id,
                "input_count": len(articles),
                "input_hash": input_hash,
                "metrics": measurements,
                "themes": themes,
                "artifacts": str(folder),
            }
        except Exception as error:
            conn.rollback()
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE runs SET status='failed',finished_at=CURRENT_TIMESTAMP,error=%s "
                    "WHERE id=%s",
                    (f"{type(error).__name__}: {str(error)[:1000]}", run_id),
                )
            conn.commit()
            raise
