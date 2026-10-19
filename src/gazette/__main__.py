"""Interface de collecte utilisable sans Airflow : python -m gazette."""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from gazette.collectors.rss import collect_source, load_sources


def main():
    parser = argparse.ArgumentParser(description="Collecter une source RSS en JSON")
    parser.add_argument("--sources", type=Path, default=Path("sources.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--source", help="Identifiant de la source active a collecter")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sources = load_sources(args.sources)
    if args.source:
        sources = [source for source in sources if source["source_id"] == args.source]
    if len(sources) != 1:
        parser.error("Choisir exactement une source active avec --source")
    run_id = args.run_id or f"cli__{datetime.now(UTC).isoformat()}"
    path = collect_source(sources[0], args.output, run_id)
    print(json.dumps({"output": path, "run_id": run_id}))


if __name__ == "__main__":
    main()
