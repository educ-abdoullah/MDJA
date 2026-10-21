"""Lecture du catalogue utilisateur ; identifiants stables sans changer son format."""

import csv
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse


def source_id_from_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return {"le-monde": "lemonde", "l-humanite": "humanite"}.get(slug, slug)


def read_catalogue(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header = stream.readline()
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=";" if ";" in header else ",")
        supplied = {"Nom", "type", "region", "source", "acces", "conditions", "notes"}
        legacy = {"source_id", "name", "url", "enabled"}
        fields = set(reader.fieldnames or [])
        french = supplied.issubset(fields)
        if not french and not legacy.issubset(fields):
            raise ValueError("Colonnes sources.csv manquantes")
        sources, seen = [], set()
        for row in reader:
            name = (row["Nom"] if french else row["name"]).strip()
            source_id = source_id_from_name(name) if french else row["source_id"].strip()
            url = (row["source"] if french else row["url"]).strip()
            active = True
            if not french:
                enabled = row["enabled"].strip().lower()
                if enabled not in {"true", "false"}:
                    raise ValueError("enabled doit valoir true ou false")
                active = enabled == "true"
            if not re.fullmatch(r"[a-z0-9_-]{1,64}", source_id) or source_id in seen:
                raise ValueError(f"Identifiant invalide ou duplique : {source_id}")
            if not name:
                raise ValueError(f"Nom manquant : {source_id}")
            if active and (urlparse(url).scheme not in {"http", "https"}
                           or not urlparse(url).hostname):
                raise ValueError(f"URL HTTP(S) requise : {source_id}")
            seen.add(source_id)
            sources.append({
                "source_id": source_id, "name": name, "url": url, "active": active,
                "type": row.get("type", ""), "region": row.get("region", ""),
                "access": row.get("acces", row.get("site_url", "")),
                "conditions": row.get("conditions", ""), "notes": row.get("notes", ""),
            })
    if not sources:
        raise ValueError("Catalogue vide")
    return sources
