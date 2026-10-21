"""Migrations versionnees, import du catalogue et ecriture sans doublon."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg2
from psycopg2 import sql

from gazette.catalogue import read_catalogue
from gazette.storage.raw import article_id

MIGRATIONS = Path(__file__).resolve().parents[3] / "infra" / "migrations"


def ensure_database(database_url: str, admin_url: str):
    database = unquote(urlparse(database_url).path.lstrip("/"))
    if not database or database in {"postgres", "template0", "template1", "airflow"}:
        raise ValueError("Utiliser une base metier distincte, par exemple gazette")
    admin = psycopg2.connect(admin_url, connect_timeout=10)
    try:
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", ("gazette-init:" + database,))
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            if not cursor.fetchone():
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    finally:
        admin.close()


def migrate(connection):
    applied = []
    with connection, connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('gazette-migrations'))")
        cursor.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY, checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        paths = sorted(MIGRATIONS.glob("*.sql"))
        if not paths:
            raise ValueError("Aucune migration SQL trouvee")
        for path in paths:
            content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            checksum = hashlib.sha256(content.encode()).hexdigest()
            cursor.execute("SELECT checksum FROM schema_migrations WHERE version=%s", (path.name,))
            existing = cursor.fetchone()
            if existing:
                if existing[0] != checksum:
                    raise ValueError(f"Migration deja appliquee mais modifiee : {path.name}")
                continue
            cursor.execute(content)
            cursor.execute("INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)",
                           (path.name, checksum))
            applied.append(path.name)
    return applied


def sync_sources(connection, catalogue: Path):
    sources = read_catalogue(catalogue)
    with connection, connection.cursor() as cursor:
        for source in sources:
            cursor.execute("""INSERT INTO sources
                (id,nom,type,region,url_flux,acces,conditions,notes,actif)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                nom=EXCLUDED.nom, type=EXCLUDED.type, region=EXCLUDED.region,
                url_flux=EXCLUDED.url_flux, acces=EXCLUDED.acces,
                conditions=EXCLUDED.conditions, notes=EXCLUDED.notes""", (
                source["source_id"], source["name"], source["type"], source["region"],
                source["url"], source["access"], source["conditions"], source["notes"],
                source["active"],
            ))
    return len(sources)


def atomic_json(path: Path, item: dict):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(item, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def store_items(connection, items: list[dict], output_dir: Path) -> dict:
    counts = {"recus": len(items), "ecrits": 0, "ignores": 0, "repares": 0}
    # Un ordre stable de verrous evite les interblocages si plusieurs sources sont fournies.
    source_ids = sorted({item["source"] for item in items})
    with connection, connection.cursor() as cursor:
        for source_id in source_ids:
            if not re.fullmatch(r"[a-z0-9_-]{1,64}", source_id):
                raise ValueError("Identifiant de source invalide")
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                           ("gazette-source:" + source_id,))
            cursor.execute("SELECT 1 FROM sources WHERE id=%s", (source_id,))
            if not cursor.fetchone():
                raise ValueError(f"Source absente de PostgreSQL : {source_id}")
        for item in items:
            expected_id = article_id(item["source"], item["lien"])
            if item["id"] != expected_id:
                raise ValueError("Identifiant d'article incoherent")
            directory = output_dir / item["source"]
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{expected_id}.json"
            cursor.execute("SELECT id FROM articles_bruts_index WHERE source=%s AND lien=%s",
                           (item["source"], item["lien"]))
            indexed = cursor.fetchone() is not None
            existing = None
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, UnicodeError):
                    pass
            valid_file = (
                isinstance(existing, dict) and existing.get("id") == expected_id
                and existing.get("source") == item["source"]
                and existing.get("lien") == item["lien"]
                and existing.get("recupere_le")
            )
            if valid_file:
                counts["ignores"] += 1
                received = existing["recupere_le"]
            else:
                atomic_json(path, item)
                counts["repares" if indexed else "ecrits"] += 1
                received = item["recupere_le"]
            cursor.execute("""INSERT INTO articles_bruts_index(id,source,lien,chemin,recupere_le)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (source,lien) DO UPDATE SET
                chemin=EXCLUDED.chemin,recupere_le=EXCLUDED.recupere_le""",
                           (expected_id, item["source"], item["lien"],
                            path.relative_to(output_dir).as_posix(), received))
    return counts
