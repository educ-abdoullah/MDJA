"""Gazette : collecte RSS et contrôle qualité toutes les 30 minutes (TD4)."""

import json
import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, get_current_context, task


@dag(
    dag_id="gazette_daily",
    description=(
        "RSS -> stockage brut -> articles propres/rejets -> rapport -> contrôles et alertes"
    ),
    schedule="*/30 * * * *",
    start_date=pendulum.datetime(2026, 10, 21, tz="Europe/Paris"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=40),
    default_args={"retries": 0},
    tags=["mdja", "rss", "qualite", "td4", "mlops", "td5"],
)
def gazette_daily():
    @task(execution_timeout=timedelta(minutes=19))
    def collect_rss():
        from gazette.collectors.rss import collect_active_sources

        root = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
        results = collect_active_sources(
            os.environ["GAZETTE_DATABASE_URL"], root / "articles_bruts"
        )
        failures = {source: data["error"] for source, data in results.items() if "error" in data}
        totals = {
            key: sum(int(data.get(key, 0)) for data in results.values())
            for key in ("recus", "ecrits", "ignores", "repares")
        }
        summary = {
            "event": "gazette_cycle_summary",
            "sources_checked": len(results),
            "sources_failed": len(failures),
            "totals": totals,
            "failures": failures,
        }
        print(json.dumps(summary, ensure_ascii=False))
        # Les erreurs individuelles sont gérées par le collecteur et comptées par cycle.
        # Ne pas les relancer avec Airflow : cela fausserait les échecs consécutifs.
        return {"sources_checked": len(results), "sources_failed": len(failures), **totals}

    @task(execution_timeout=timedelta(minutes=5))
    def process_quality():
        from gazette.processing.persist import rebuild_quality

        root = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
        result = rebuild_quality(os.environ["GAZETTE_DATABASE_URL"], root / "articles_bruts")
        print(json.dumps({"event": "gazette_quality_processed", **result}, ensure_ascii=False))
        return result

    @task(execution_timeout=timedelta(minutes=2))
    def generate_quality_report():
        from contextlib import closing

        import psycopg2

        from gazette.processing.report import collect_quality_snapshot, write_report

        root = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
        with closing(
            psycopg2.connect(os.environ["GAZETTE_DATABASE_URL"], connect_timeout=10)
        ) as connection:
            snapshot = collect_quality_snapshot(connection)
        snapshot["run_id"] = get_current_context()["run_id"]
        report_path = write_report(snapshot, root / "rapports")
        print(
            json.dumps(
                {
                    "event": "gazette_quality_report",
                    "path": str(report_path),
                    "totals": snapshot["totaux"],
                    "top_5_rejets": snapshot["top_5_rejets"],
                },
                ensure_ascii=False,
            )
        )
        return str(report_path)

    @task(execution_timeout=timedelta(minutes=2))
    def check_quality():
        from gazette.processing.quality_checks import run_checks

        result = run_checks(
            os.environ["GAZETTE_DATABASE_URL"],
            webhook_url=os.environ.get("GAZETTE_ALERT_WEBHOOK_URL") or None,
            provider=os.environ.get("GAZETTE_ALERT_PROVIDER", "discord"),
        )
        print(json.dumps({"event": "gazette_quality_check", **result}, ensure_ascii=False))
        # Un contrôle échoué doit apparaître comme un échec dans Airflow.
        # L'alerte webhook a déjà été envoyée par run_checks si elle était configurée.
        if result["alertes"]:
            raise ValueError(f"Contrôles qualité en échec : {len(result['alertes'])} alerte(s)")
        return {"statut": result["statut"], "alertes": 0}

    @task(execution_timeout=timedelta(minutes=10))
    def cluster_themes():
        from gazette.mlops.pipeline import run_pipeline

        root = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
        context = get_current_context()
        result = run_pipeline(
            os.environ["GAZETTE_DATABASE_URL"],
            root / "config/clustering.yaml",
            root / "data/mlops",
            cutoff=context["data_interval_end"],
            airflow_run_id=context["run_id"],
        )
        print(json.dumps({"event": "gazette_mlops_run", **result}, ensure_ascii=False))
        return {"run_id": result["run_id"], "metrics": result["metrics"]}

    collecte = collect_rss()
    qualite = process_quality()
    rapport = generate_quality_report()
    controle = check_quality()
    themes = cluster_themes()
    collecte >> qualite >> rapport >> controle >> themes


gazette_daily()
