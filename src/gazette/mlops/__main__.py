"""Commande reproductible : python -m gazette.mlops --cutoff DATE_UTC."""

import argparse
import json
import os
from datetime import datetime

from gazette.mlops.pipeline import run_pipeline

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="config/clustering.yaml")
parser.add_argument("--output", default="data/mlops")
parser.add_argument("--cutoff", type=datetime.fromisoformat)
parser.add_argument("--replay", help="UUID du run réussi à rejouer depuis ses instantanés")
args = parser.parse_args()
if args.replay and args.cutoff:
    parser.error("--replay reprend la fenêtre d'origine ; ne pas préciser --cutoff")
result = run_pipeline(
    os.environ["GAZETTE_DATABASE_URL"],
    args.config,
    args.output,
    cutoff=args.cutoff,
    replay_run_id=args.replay,
)
print(json.dumps(result, ensure_ascii=False, indent=2))
