"""Initialiser le stockage, consulter le catalogue ou importer un flux enregistre."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg2

from gazette.storage.database import ensure_database, migrate, store_items, sync_sources
from gazette.storage.raw import parse_raw_items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--catalogue", type=Path, default=Path("sources.csv"))
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--input", type=Path, help="Flux RSS/Atom enregistre localement")
    parser.add_argument("--source")
    parser.add_argument("--output", type=Path, default=Path("articles_bruts"))
    args = parser.parse_args()
    database_url = os.environ.get("GAZETTE_DATABASE_URL")
    if not database_url:
        parser.error("GAZETTE_DATABASE_URL doit etre configuree")
    if args.init:
        ensure_database(database_url, os.environ["GAZETTE_ADMIN_DATABASE_URL"])
    connection = psycopg2.connect(database_url, connect_timeout=10)
    try:
        if args.init:
            print(json.dumps({"migrations": migrate(connection),
                              "sources_importees": sync_sources(connection, args.catalogue)}))
        if args.input:
            if not args.source:
                parser.error("--source est requis avec --input")
            content = args.input.read_bytes()
            if len(content) > 5 * 1024 * 1024:
                parser.error("Flux superieur a 5 Mio")
            items = parse_raw_items(content, args.source, datetime.now(UTC))
            print(json.dumps(store_items(connection, items, args.output)))
        if args.list_sources:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT id,nom,url_flux,actif,derniere_reussite,
                    echecs_consecutifs FROM sources ORDER BY id""")
                print(json.dumps(cursor.fetchall(), ensure_ascii=False, default=str, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
