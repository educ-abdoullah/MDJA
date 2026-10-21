"""Collecte RSS de la Gazette toutes les 30 minutes via PostgreSQL."""

import json
import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id="gazette_daily",
    description="Collecte RSS multi-sources vers PostgreSQL et articles_bruts",
    schedule="*/30 * * * *",
    start_date=pendulum.datetime(2026, 10, 21, tz="Europe/Paris"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=28),
    default_args={"retries": 0},
    tags=["mdja", "rss", "collecte"],
)
def gazette_daily():
    @task(execution_timeout=timedelta(minutes=25))
    def collect_rss():
        from gazette.collectors.rss import collect_active_sources

        database_url = os.environ["GAZETTE_DATABASE_URL"]
        root = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
        results = collect_active_sources(database_url, root / "articles_bruts")
        failures = {source: result for source, result in results.items() if "error" in result}
        totals = {
            key: sum(int(result.get(key, 0)) for result in results.values())
            for key in ("recus", "ecrits", "ignores", "repares")
        }
        print(json.dumps({
            "event": "gazette_cycle_summary",
            "sources_checked": len(results),
            "sources_failed": len(failures),
            "totals": totals,
            "failures": failures,
        }, ensure_ascii=False))
        # Les erreurs propres a une source sont comptabilisees et gerees par le collecteur.
        # Ne pas lever une exception ici : un retry Airflow compterait un autre cycle.
        # Seules les erreurs globales/infrastructure doivent faire echouer cette tache.
        return {"sources_checked": len(results), "sources_failed": len(failures), **totals}

    collect_rss()


gazette_daily()
