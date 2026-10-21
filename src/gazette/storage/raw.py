"""Metadonnees brutes bornees ; aucune regle de fraicheur ni de qualite editoriale."""

import calendar
import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

import feedparser


def article_id(source: str, link: str) -> str:
    return hashlib.sha256(f"{source}\0{link}".encode()).hexdigest()


def parse_raw_items(content: bytes, source: str, retrieved_at: datetime) -> list[dict]:
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", source):
        raise ValueError("Identifiant de source invalide")
    if retrieved_at.tzinfo is None:
        raise ValueError("recupere_le doit contenir un fuseau horaire")
    feed = feedparser.parse(content)
    if not feed.version or feed.bozo:
        raise ValueError("Flux RSS/Atom invalide")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise ValueError("XML invalide") from error
    raw_entries = [node for node in root.iter()
                   if node.tag in {"item", "{http://www.w3.org/2005/Atom}entry"}]
    if len(raw_entries) != len(feed.entries):
        raise ValueError("Correspondance entre items XML et parseur impossible")
    items = []
    for entry, raw_entry in zip(feed.entries, raw_entries, strict=True):
        link = entry.get("link", "").strip()
        parsed_link = urlparse(link)
        if parsed_link.scheme not in {"http", "https"} or not parsed_link.hostname:
            continue  # Sans lien, la cle naturelle source+lien ne peut pas etre construite.
        if len(link.encode("utf-8")) > 2048:
            continue
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        try:
            published_utc = (
                datetime.fromtimestamp(calendar.timegm(published), UTC).isoformat()
                if published else None
            )
        except (ValueError, OverflowError, OSError):
            published_utc = None
        # feedparser peut fabriquer summary a partir de content:encoded : on refuse ce repli.
        summary_node = next((child for child in raw_entry
                             if child.tag in {"description",
                                              "{http://www.w3.org/2005/Atom}summary"}), None)
        summary = "" if summary_node is None else "".join(summary_node.itertext())
        title = entry.get("title", "")
        categories = [tag.get("term", "")[:200] for tag in entry.get("tags", [])][:20]
        payload = {
            "guid_ou_id": str(entry.get("id", ""))[:4096],
            "date_publication_originale": entry.get("published"),
            "date_modification_originale": entry["updated"] if "updated" in entry else None,
            "format_resume": entry.get("summary_detail", {}).get("type"),
            "titre_tronque": len(title) > 1000,
            "resume_tronque": len(summary) > 2000,
        }
        items.append({
            "id": article_id(source, link), "source": source, "lien": link,
            "titre": title[:1000], "resume": summary[:2000], "publie_le": published_utc,
            "recupere_le": retrieved_at.astimezone(UTC).isoformat(), "rubrique": categories,
            "payload": payload,
        })
    return items
