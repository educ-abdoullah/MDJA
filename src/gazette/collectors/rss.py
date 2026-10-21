"""RSS/Atom : telechargement borne, dates UTC et archives JSON atomiques."""

import calendar
import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from contextlib import closing
import time
import socket
from urllib.error import URLError

import feedparser

from gazette.catalogue import read_catalogue

LOGGER = logging.getLogger(__name__)
MAX_FEED_BYTES = 5 * 1024 * 1024


def load_sources(path: Path) -> list[dict[str, str]]:
    """Valider la configuration avant de lancer des requetes."""
    sources = [{"source_id": row["source_id"], "name": row["name"], "url": row["url"]}
               for row in read_catalogue(path) if row["active"]]
    if not sources:
        raise ValueError("Aucune source active dans sources.csv")
    return sources


def fetch_feed(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "GazetteMDJA/0.1 (RSS educational project)"})
    with urlopen(request, timeout=30) as response:
        content = response.read(MAX_FEED_BYTES + 1)
    if len(content) > MAX_FEED_BYTES:
        raise ValueError("Flux RSS superieur a 5 Mio")
    return content



def fetch_feed_conditional(
    url: str, etag: str | None = None, last_modified: str | None = None,
) -> tuple[bytes | None, int, str | None, str | None]:
    """Lire le flux avec validation HTTP ; None signifie HTTP 304."""
    headers = {"User-Agent": "GazetteMDJA/0.1 (RSS educational project)"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read(MAX_FEED_BYTES + 1)
            if len(content) > MAX_FEED_BYTES:
                raise ValueError("Flux RSS superieur a 5 Mio")
            return content, response.status, response.headers.get("ETag"), response.headers.get("Last-Modified")
    except HTTPError as error:
        if error.code == 304:
            return None, 304, error.headers.get("ETag"), error.headers.get("Last-Modified")
        raise


def parse_articles(content: bytes, source: dict[str, str], as_of: datetime) -> list[dict]:
    """Ne garder que les titres/liens dates de moins de 24 h ; aucun corps d'article."""
    if as_of.tzinfo is None:
        raise ValueError("as_of doit contenir un fuseau horaire")
    feed = feedparser.parse(content)
    if not feed.version or feed.bozo:
        raise ValueError("Flux RSS/Atom invalide")
    articles = []
    seen = set()
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if not title or urlparse(link).scheme not in {"http", "https"} or not published:
            continue
        date = datetime.fromtimestamp(calendar.timegm(published), UTC)
        if not as_of - timedelta(hours=24) < date <= as_of or link in seen:
            continue
        seen.add(link)
        articles.append({
            "source_id": source["source_id"], "source": source["name"],
            "title": title, "url": link, "published_at": date.isoformat(),
        })
    return articles


def collect_source(source: dict[str, str], output_dir: Path, run_id: str) -> str:
    """Une archive par source/run ; une reprise remplace atomiquement le meme fichier."""
    collected_at = datetime.now(UTC)
    content = fetch_feed(source["url"])
    articles = parse_articles(content, source, collected_at)
    if not articles:
        raise ValueError(f"Aucun article recent exploitable : {source['source_id']}")
    run_key = hashlib.sha256(run_id.encode()).hexdigest()[:24]
    directory = output_dir / run_key
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{source['source_id']}.json"
    payload = {
        "run_id": run_id, "collected_at": collected_at.isoformat(),
        "source": source, "article_count": len(articles), "articles": articles,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    LOGGER.info(json.dumps({
        "event": "rss_collected", "run_id": run_id, "source_id": source["source_id"],
        "article_count": len(articles), "output": str(destination),
    }))
    return str(destination)

# --- Etape 3 : nouveau parcours vers la base metier et les JSON par article ---
# Les fonctions historiques restent disponibles pour l'ancien DAG, jusqu'a sa migration.


def load_sources_from_db(connection) -> list[dict[str, str]]:
    """Lire les sources actives dans la base metier, et non dans sources.csv."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, nom, url_flux, etag, last_modified
            FROM sources
            WHERE actif = TRUE AND sommeil_depuis IS NULL
            ORDER BY id
        """)
        return [
            {"source_id": source_id, "name": name, "url": url,
             "etag": etag, "last_modified": last_modified}
            for source_id, name, url, etag, last_modified in cursor.fetchall()
        ]


def collect_source_to_storage(connection, source: dict[str, str], output_dir: Path) -> dict:
    """Collecter un flux RSS et enregistrer les metadonnees et le suivi HTTP."""
    from gazette.storage.database import store_items
    from gazette.storage.raw import parse_raw_items

    started = time.monotonic()
    source_id = source["source_id"]
    try:
        content, status, etag, last_modified = fetch_feed_conditional(
            source["url"], source.get("etag"), source.get("last_modified")
        )
        if status == 304:
            counts = {"recus": 0, "ecrits": 0, "ignores": 0, "repares": 0}
        else:
            # 200 sans item est valide : aucun nouvel article exploitable.
            items = parse_raw_items(content, source_id, datetime.now(UTC))
            counts = store_items(connection, items, output_dir)

        # La transaction de store_items() est deja terminee avant cette mise a jour.
        with connection.cursor() as cursor:
            if status == 304:
                # Les validateurs absents sur un 304 ne remplacent pas ceux connus.
                cursor.execute("""UPDATE sources SET
                    derniere_reussite = CURRENT_TIMESTAMP,
                    etag = COALESCE(%s, etag),
                    last_modified = COALESCE(%s, last_modified),
                    derniere_erreur = NULL,
                    echecs_consecutifs = 0,
                    sommeil_depuis = NULL
                    WHERE id = %s""", (etag, last_modified, source_id))
            else:
                # Sur HTTP 200, les validateurs sont ceux de la nouvelle representation.
                cursor.execute("""UPDATE sources SET
                    derniere_reussite = CURRENT_TIMESTAMP,
                    etag = %s,
                    last_modified = %s,
                    derniere_erreur = NULL,
                    echecs_consecutifs = 0,
                    sommeil_depuis = NULL
                    WHERE id = %s""", (etag, last_modified, source_id))
            if cursor.rowcount != 1:
                raise ValueError(f"Source absente de PostgreSQL : {source_id}")
        connection.commit()

        result = {**counts, "http_status": status}
        LOGGER.info(json.dumps({
            "event": "rss_storage_success", "source_id": source_id,
            **result, "duration_seconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=False))
        return result
    except Exception as error:
        connection.rollback()
        LOGGER.error(json.dumps({
            "event": "rss_storage_error", "source_id": source_id,
            "error": str(error),
            "duration_seconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=False))
        raise


# Retry rules apply to one collection cycle, not to individual attempts in the DB.
RETRYABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3  # 1 initial request + 2 retries
BACKOFF_SECONDS = (1, 2)  # bounded exponential backoff
SLEEP_AFTER_FAILURES = 3


def is_transient_error(error: Exception) -> bool:
    """Retry only network problems and temporary HTTP responses."""
    if isinstance(error, HTTPError):
        return error.code in RETRYABLE_HTTP_STATUSES
    return isinstance(error, (URLError, TimeoutError, ConnectionError, socket.timeout))


def record_source_failure(connection, source_id: str, error: Exception) -> dict:
    """Count ONE failed cycle; sleep the source after 3 failed cycles."""
    with connection.cursor() as cursor:
        cursor.execute("""UPDATE sources SET
            echecs_consecutifs = echecs_consecutifs + 1,
            derniere_erreur = %s,
            sommeil_depuis = CASE
                WHEN echecs_consecutifs + 1 >= %s
                THEN COALESCE(sommeil_depuis, CURRENT_TIMESTAMP)
                ELSE sommeil_depuis
            END
            WHERE id = %s
            RETURNING echecs_consecutifs, sommeil_depuis
        """, (str(error)[:2000], SLEEP_AFTER_FAILURES, source_id))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Source absente de PostgreSQL : {source_id}")
    connection.commit()
    return {"error": str(error), "echecs_consecutifs": row[0],
            "en_sommeil": row[1] is not None}


def reactivate_source(database_url: str, source_id: str) -> None:
    """Explicitly reactivate a sleeping source and clear its failure state."""
    import psycopg2
    with closing(psycopg2.connect(database_url, connect_timeout=10)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE sources SET
                sommeil_depuis = NULL,
                echecs_consecutifs = 0,
                derniere_erreur = NULL
                WHERE id = %s
            """, (source_id,))
            if cursor.rowcount != 1:
                raise ValueError(f"Source absente de PostgreSQL : {source_id}")
        connection.commit()


def collect_active_sources(database_url: str, output_dir: Path) -> dict[str, dict]:
    """Attempt all awake sources, retry transient errors, isolate final failures."""
    import psycopg2
    with closing(psycopg2.connect(database_url, connect_timeout=10)) as connection:
        sources = load_sources_from_db(connection)

    results: dict[str, dict] = {}
    for source in sources:
        source_id = source["source_id"]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                # Fresh connection per attempt: store_items uses its own context.
                with closing(psycopg2.connect(database_url, connect_timeout=10)) as connection:
                    results[source_id] = collect_source_to_storage(connection, source, output_dir)
                break
            except Exception as error:
                transient = is_transient_error(error)
                if transient and attempt < MAX_ATTEMPTS:
                    wait = BACKOFF_SECONDS[attempt - 1]
                    LOGGER.warning(json.dumps({
                        "event": "rss_retry", "source_id": source_id,
                        "attempt": attempt, "wait_seconds": wait, "error": str(error),
                    }, ensure_ascii=False))
                    time.sleep(wait)
                    continue

                # A cycle contributes exactly one failure, not one per attempt.
                try:
                    with closing(psycopg2.connect(database_url, connect_timeout=10)) as connection:
                        outcome = record_source_failure(connection, source_id, error)
                    results[source_id] = {**outcome, "tentatives": attempt}
                    LOGGER.error(json.dumps({
                        "event": "rss_cycle_failed", "source_id": source_id,
                        **results[source_id],
                    }, ensure_ascii=False))
                except Exception:
                    LOGGER.exception("Echec de l'enregistrement de la panne pour %s", source_id)
                    results[source_id] = {
                        "error": str(error), "tentatives": attempt,
                        "suivi_echec_non_enregistre": True,
                    }
                break
    return results
