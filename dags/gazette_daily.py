"""Premier palier : collecte RSS uniquement, sans publication d'edition."""

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, get_current_context, task


@dag(
    dag_id="gazette_daily",
    description="Collecte des titres RSS recents en JSON",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 10, 19, tz="Europe/Paris"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=3),
    },
    tags=["mdja", "rss"],
)
def gazette_daily():
    @task
    def read_sources():
        from gazette.collectors.rss import load_sources

        root = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
        return load_sources(root / "sources.csv")

    @task
    def collect_rss(source):
        from gazette.collectors.rss import collect_source

        root = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
        return collect_source(source, root / "data" / "raw", get_current_context()["run_id"])

    collect_rss.expand(source=read_sources())


gazette_daily()
