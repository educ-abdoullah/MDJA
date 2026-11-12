"""Rapport qualité TD4 depuis PostgreSQL, sans toucher aux données brutes.

Le rapport décrit l'état courant des décisions qualité (tables reconstruites
par persist.py) et non l'historique de tous les cycles Airflow.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def collect_quality_snapshot(connection, *, generated_at: datetime | None = None) -> dict:
    """Lire la photographie courante du traitement qualité."""
    generated_at = generated_at or datetime.now(UTC)
    if generated_at.tzinfo is None:
        raise ValueError("generated_at doit contenir un fuseau")

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT s.id,
                   (SELECT count(*) FROM articles_bruts_index b WHERE b.source=s.id) AS bruts,
                   (SELECT count(*) FROM articles_propres p WHERE p.source=s.id) AS gardes,
                   (SELECT count(*) FROM rejets r WHERE r.source=s.id) AS rejetes
            FROM sources s ORDER BY s.id
        """)
        source_rows = cursor.fetchall()
        cursor.execute("""
            SELECT source, regle_id, COUNT(*)
            FROM rejets GROUP BY source, regle_id ORDER BY source, regle_id
        """)
        rule_rows = cursor.fetchall()

    by_source = []
    for name, raw_count, kept_count, rejected_count in source_rows:
        raw_count, kept_count, rejected_count = map(int, (raw_count, kept_count, rejected_count))
        by_source.append(
            {
                "source": name,
                "entres": raw_count,
                "gardes": kept_count,
                "rejetes": rejected_count,
                "taux_rejet_pct": round(100 * rejected_count / raw_count, 2) if raw_count else None,
                "non_classes": raw_count - kept_count - rejected_count,
            }
        )

    by_rule = Counter()
    by_source_rule = []
    for source, rule, amount in rule_rows:
        by_rule[rule] += int(amount)
        by_source_rule.append({"source": source, "regle": rule, "rejetes": int(amount)})

    totals = {
        "entres": sum(row["entres"] for row in by_source),
        "gardes": sum(row["gardes"] for row in by_source),
        "rejetes": sum(row["rejetes"] for row in by_source),
    }
    totals["non_classes"] = totals["entres"] - totals["gardes"] - totals["rejetes"]

    return {
        "genere_le": generated_at.astimezone(UTC).isoformat(),
        "portee": "instantane des tables qualite (pas un historique par cycle)",
        "totaux": totals,
        "par_source": by_source,
        "par_regle": dict(sorted(by_rule.items())),
        "par_source_et_regle": by_source_rule,
        "top_5_rejets": [
            {"regle": rule, "nombre": amount}
            for rule, amount in sorted(by_rule.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
        ],
    }


def render_markdown(snapshot: dict) -> str:
    """Construire un rapport Markdown lisible, sans contenu HTML non fiable."""
    totals = snapshot["totaux"]
    lines = [
        "# Rapport qualité — Gazette",
        "",
        f"Généré le : {snapshot['genere_le']} (UTC)",
        "",
        "**Périmètre :** état actuel des tables `articles_propres` et `rejets` ; "
        "les articles bruts correspondent à `articles_bruts_index`. "
        "Chaque traitement réexamine tous les bruts indexés (pas seulement les nouveaux).",
        f"Run Airflow : {snapshot.get('run_id') or 'exécution hors Airflow'}",
        "",
        "## Bilan global",
        "",
        "| Entrés (bruts indexés) | Conservés | Rejetés | Non classés |",
        "|---:|---:|---:|---:|",
        (
            f"| {totals['entres']} | {totals['gardes']} | "
            f"{totals['rejetes']} | {totals['non_classes']} |"
        ),
        "",
        "## Par source",
        "",
        "| Source | Entrés | Conservés | Rejetés | Taux de rejet | Non classés |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in snapshot["par_source"]:
        rate = "N/A" if row["taux_rejet_pct"] is None else f"{row['taux_rejet_pct']:.2f} %"
        lines.append(
            f"| {row['source']} | {row['entres']} | {row['gardes']} | "
            f"{row['rejetes']} | {rate} | {row['non_classes']} |"
        )

    lines += ["", "## Rejets par règle", "", "| Règle | Nombre |", "|---|---:|"]
    if snapshot["par_regle"]:
        lines += [f"| {rule} | {amount} |" for rule, amount in snapshot["par_regle"].items()]
    else:
        lines.append("| Aucun rejet | 0 |")

    lines += [
        "",
        "## Rejets par source et par règle",
        "",
        "| Source | Règle | Nombre |",
        "|---|---|---:|",
    ]
    if snapshot["par_source_et_regle"]:
        for item in snapshot["par_source_et_regle"]:
            lines.append(f"| {item['source']} | {item['regle']} | {item['rejetes']} |")
    else:
        lines.append("| Aucun | — | 0 |")

    lines += ["", "## Cinq principaux motifs de rejet", ""]
    if snapshot["top_5_rejets"]:
        for index, item in enumerate(snapshot["top_5_rejets"], 1):
            lines.append(f"{index}. `{item['regle']}` : {item['nombre']} rejet(s)")
    else:
        lines.append("Aucun rejet dans les décisions courantes.")

    lines += ["", "## Points de vigilance", ""]
    if totals["non_classes"]:
        lines.append(
            f"- **Attention :** {totals['non_classes']} article(s) brut(s) "
            "sans décision qualité. Relancer le traitement de l'étape 4."
        )
    else:
        lines.append("- Tous les articles bruts indexés disposent d'une décision qualité.")
    for row in snapshot["par_source"]:
        if row["taux_rejet_pct"] is not None and row["taux_rejet_pct"] > 80:
            lines.append(
                f"- **Seuil dépassé :** {row['source']} ({row['taux_rejet_pct']:.2f} % de rejets)."
            )
    lines += ["", "Les contrôles qualité suivent la génération du rapport dans le DAG.", ""]
    return "\n".join(lines)


def write_report(snapshot: dict, output_dir: Path) -> Path:
    """Un rapport quotidien stable + une archive horodatée par exécution."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.fromisoformat(snapshot["genere_le"]).astimezone(UTC)
    content = render_markdown(snapshot)
    daily = output_dir / f"qualite-{date:%Y-%m-%d}.md"
    archive = output_dir / f"qualite-{date:%Y-%m-%dT%H-%M-%S-%fZ}.md"
    daily.write_text(content, encoding="utf-8")
    archive.write_text(content, encoding="utf-8")
    return daily


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rapport qualité sur les décisions stockées en base"
    )
    parser.add_argument("--output-dir", default="rapports", type=Path)
    args = parser.parse_args()
    import psycopg2

    with closing(psycopg2.connect(os.environ["GAZETTE_DATABASE_URL"], connect_timeout=10)) as conn:
        snapshot = collect_quality_snapshot(conn)
    daily = write_report(snapshot, args.output_dir)
    print(
        json.dumps(
            {
                "rapport": str(daily),
                "totaux": snapshot["totaux"],
                "top_5_rejets": snapshot["top_5_rejets"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
