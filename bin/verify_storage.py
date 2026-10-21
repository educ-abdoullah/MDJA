"""Demonstration du stockage sur les exemples reels, sans nouvelle requete aux medias."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-dir", type=Path, default=Path("fixtures"))
    parser.add_argument("--output", type=Path, default=Path("articles_bruts"))
    parser.add_argument("--report", type=Path,
                        default=Path("data/diagnostics/etape2-stockage.json"))
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import psycopg2

    from gazette.catalogue import read_catalogue
    from gazette.storage.database import store_items
    from gazette.storage.raw import parse_raw_items

    connection = psycopg2.connect(os.environ["GAZETTE_DATABASE_URL"], connect_timeout=10)
    report = {"observed_at": datetime.now(UTC).isoformat(), "samples": []}
    try:
        for source in read_catalogue(Path("sources.csv")):
            sample = args.fixtures_dir / f"{source['source_id']}_sample_rss.xml"
            entry = {"source": source["source_id"], "fixture": sample.exists()}
            if sample.exists():
                items = parse_raw_items(sample.read_bytes(), source["source_id"], datetime.now(UTC))
                entry["first_pass"] = store_items(connection, items, args.output)
                entry["second_pass"] = store_items(connection, items, args.output)
                assert entry["second_pass"]["ecrits"] == 0
                assert entry["second_pass"]["repares"] == 0
            report["samples"].append(entry)
        with connection.cursor() as cursor:
            cursor.execute("SELECT id,actif,echecs_consecutifs FROM sources ORDER BY id")
            report["registered_sources"] = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) FROM articles_bruts_index")
            report["indexed_articles"] = cursor.fetchone()[0]
    finally:
        connection.close()
    report["json_files"] = len(list(args.output.rglob("*.json")))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
