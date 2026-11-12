"""TD4 étape 6 : contrôles sur les tables qualité et alerte vers un webhook.

Aucune modification SQL. Les métriques sont émises en JSON dans les logs :
Airflow pourra les collecter lors de l'étape 7.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from contextlib import closing
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from gazette.processing.report import collect_quality_snapshot
from gazette.processing.rules import FUTURE_TOLERANCE

LOGGER = logging.getLogger(__name__)
REJECTION_THRESHOLD_PCT = 80.0


def read_integrity_counts(connection) -> dict[str, int]:
    """Vérifier les faits sur les données réelles, pas sur des fixtures."""
    checks = {
        "titres_vides": (
            "SELECT COUNT(*) FROM articles_propres WHERE titre IS NULL OR btrim(titre) = ''"
        ),
        "dates_futures": (
            "SELECT COUNT(*) FROM articles_propres "
            "WHERE publie_le > CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')"
        ),
        "doublons_exacts": """SELECT COUNT(*) FROM (
            SELECT source, empreinte_contenu FROM articles_propres
            GROUP BY source, empreinte_contenu HAVING COUNT(*) > 1
        ) AS doublons""",
        "references_brutes_invalides": """SELECT COUNT(*) FROM articles_propres p
            LEFT JOIN articles_bruts_index b ON b.id = p.article_brut_id
            WHERE b.id IS NULL OR p.source <> b.source OR p.lien <> b.lien""",
        "rejets_sans_brut": """SELECT COUNT(*) FROM rejets r
            LEFT JOIN articles_bruts_index b ON b.id = r.article_brut_id
            WHERE b.id IS NULL OR r.source <> b.source""",
        "decisions_contradictoires": """SELECT COUNT(*) FROM articles_propres p
            INNER JOIN rejets r ON r.article_brut_id = p.article_brut_id""",
    }
    out = {}
    with connection.cursor() as cursor:
        for name, sql in checks.items():
            cursor.execute(
                sql, (FUTURE_TOLERANCE.total_seconds(),) if name == "dates_futures" else None
            )
            out[name] = int(cursor.fetchone()[0])
    return out


def evaluate_quality(
    snapshot: dict, integrity: dict[str, int], *, threshold: float = REJECTION_THRESHOLD_PCT
) -> dict:
    """Contrôles purs. Attention : les taux portent sur l'instantané, pas sur un cycle."""
    if not 0 <= threshold <= 100:
        raise ValueError("Le seuil doit être entre 0 et 100")
    alerts = []
    for key, count in sorted(integrity.items()):
        if count:
            alerts.append({"code": key, "description": f"{count} anomalie(s) : {key}"})
    pending = int(snapshot["totaux"]["non_classes"])
    if pending != 0:
        alerts.append(
            {
                "code": "articles_non_classes",
                "description": f"{pending} article(s) brut(s) sans décision qualité",
            }
        )
    for source in snapshot["par_source"]:
        rate = source["taux_rejet_pct"]
        if rate is not None and rate > threshold:
            alerts.append(
                {
                    "code": "taux_rejet_excessif",
                    "source": source["source"],
                    "description": (
                        f"{source['source']} : {rate:.2f} % de rejets (seuil {threshold:g} %)"
                    ),
                }
            )
    # Les flux vides (0 article) ne déclenchent pas d'alerte de rejet.
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "perimetre": "instantane_courant",
        "statut": "ALERTE" if alerts else "OK",
        "totaux": snapshot["totaux"],
        "rejets_par_regle": snapshot["par_regle"],
        "taux_par_source": {s["source"]: s["taux_rejet_pct"] for s in snapshot["par_source"]},
        "integrite": integrity,
        "alertes": alerts,
    }


def make_webhook_payload(result: dict, provider: str) -> dict:
    """Format simple pour Discord ou Slack, sans données personnelles d'articles."""
    if provider not in {"discord", "slack"}:
        raise ValueError("provider doit être 'discord' ou 'slack'")
    summary = "; ".join(a["description"] for a in result["alertes"])
    message = "[Gazette TD4] Contrôle qualité : " + summary
    if len(message) > 1800:
        message = message[:1797] + "..."
    return {"content": message} if provider == "discord" else {"text": message}


def send_webhook(result: dict, url: str, provider: str) -> None:
    """Webhook optionnel : HTTPS requis, timeout borné. Ne journaliser jamais l'URL."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("L'URL webhook doit être une URL HTTPS valide")
    if provider == "discord" and parsed.hostname not in {"discord.com", "discordapp.com"}:
        raise ValueError("Webhook Discord : domaine discord.com requis")
    if provider == "slack" and parsed.hostname != "hooks.slack.com":
        raise ValueError("Webhook Slack : domaine hooks.slack.com requis")
    payload = json.dumps(make_webhook_payload(result, provider)).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "GazetteTD4/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        response.read(4096)


def run_checks(
    database_url: str,
    *,
    webhook_url: str | None = None,
    provider: str = "discord",
    threshold: float = REJECTION_THRESHOLD_PCT,
) -> dict:
    """Lire une photographie cohérente dans une transaction de lecture seule."""
    import psycopg2

    with closing(psycopg2.connect(database_url, connect_timeout=10)) as connection:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection:
            snapshot = collect_quality_snapshot(connection)
            integrity = read_integrity_counts(connection)
    result = evaluate_quality(snapshot, integrity, threshold=threshold)
    LOGGER.info(json.dumps({"event": "gazette_quality_metrics", **result}, ensure_ascii=False))
    if result["alertes"]:
        if webhook_url:
            send_webhook(result, webhook_url, provider)
            LOGGER.info(
                json.dumps(
                    {"event": "gazette_quality_alert_sent", "number": len(result["alertes"])}
                )
            )
        else:
            LOGGER.warning(
                "ALERTE détectée mais aucun webhook configuré : GAZETTE_ALERT_WEBHOOK_URL"
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Contrôles qualité Gazette et alerte webhook")
    parser.add_argument("--threshold", type=float, default=REJECTION_THRESHOLD_PCT)
    parser.add_argument(
        "--test-alert",
        action="store_true",
        help="Simuler UNE anomalie pour vérifier le webhook sans changer PostgreSQL",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    url = os.environ.get("GAZETTE_ALERT_WEBHOOK_URL")
    provider = os.environ.get("GAZETTE_ALERT_PROVIDER", "discord").lower()
    if args.test_alert:
        if not url:
            parser.error("Définir GAZETTE_ALERT_WEBHOOK_URL pour tester l'envoi réel")
        fake = {
            "alertes": [
                {
                    "code": "test_manuel",
                    "description": "Alerte de TEST TD4 (aucune donnée modifiée)",
                }
            ]
        }
        send_webhook(fake, url, provider)
        print(
            json.dumps(
                {"event": "gazette_quality_test_alert_sent", "provider": provider},
                ensure_ascii=False,
            )
        )
        return
    result = run_checks(
        os.environ["GAZETTE_DATABASE_URL"],
        webhook_url=url,
        provider=provider,
        threshold=args.threshold,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["alertes"]:
        raise SystemExit(2)  # Les anomalies restent visibles pour Airflow en étape 7.


if __name__ == "__main__":
    main()
