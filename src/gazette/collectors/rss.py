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
