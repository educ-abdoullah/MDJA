"""Premier palier : collecte RSS uniquement, sans publication d'edition."""

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, get_current_context, task
from airflow.sdk.definitions.retry_policy import RetryDecision, RetryPolicy

from gazette.retries import DELAYED_RETRY_DELAY, MAX_RETRIES, delay_after_failure


class GazetteRetryPolicy(RetryPolicy):
    """Trois reprises immediates, puis huit reprises espacees de 30 minutes."""

    def evaluate(self, exception, try_number, max_tries, context=None):
        if try_number > MAX_RETRIES:
            return RetryDecision.fail(reason="Les 11 reprises ont ete epuisees")
        delay = delay_after_failure(try_number)
        return RetryDecision.retry(
            delay=delay,
            reason=f"Reprise {try_number}/{MAX_RETRIES} apres {int(delay.total_seconds())} s",
        )


@dag(
    dag_id="gazette_daily",
    description="Collecte des titres RSS recents en JSON",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 10, 19, tz="Europe/Paris"),
    catchup=False,
    max_active_runs=1,
    # Deux etapes successives peuvent chacune attendre 4 h et executer 12 tentatives.
    dagrun_timeout=timedelta(hours=10),
    default_args={
        "retries": MAX_RETRIES,
        "retry_delay": DELAYED_RETRY_DELAY,
        "retry_exponential_backoff": False,
        "retry_policy": GazetteRetryPolicy(),
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
